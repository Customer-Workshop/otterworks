#!/usr/bin/env python3
"""Fixture-mode recon for the sftp_ingest_poll -> ow_tp_ingest_cnvingest conversion.

Runs the exact transport core the Databricks notebook uses against a local
landing layout under the repo .tp-preflight sandbox (mirroring
/Volumes/ow_tp/bronze/landing/cnvingest/sftp_ingest_poll/{drop,incoming,archive}),
with a JSON-file bronze registry standing in for the Delta MERGE. Every check
value is recomputed from the fixture target after the run; live SQL/Delta/UC
behaviour is disclosed as unverified (the parent session's live validation).

Prereqs (deterministic seed, byte-identical per NS):
    export OTTERWORKS_LEGACY_ROOT=<isolated dir>
    make legacy-etl-gen-data NS=cnvingest

Usage:
    python3 etl/databricks/cnvingest/recon_fixture.py \
        --out docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.recon.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.append(str(HERE))
from ingest_core import StagedFile, deterministic_ingest_id, ingest_batch  # noqa: E402

NS = "cnvingest"
UNIT = "sftp_ingest_poll"
GOLDEN = REPO_ROOT / "docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.golden.json"
FIXTURE_ROOT = REPO_ROOT / ".tp-preflight/databricks-fixture/landing" / NS / UNIT
ANOMALY_NONMATCH = "NOTCUSTBILL_x.txt"
ANOMALY_FILEPART = "CUSTBILL_CNVINGEST_003.dat.filepart"


class JsonBronze:
    """Local stand-in for the notebook's DeltaBronze: same keys, same
    no-duplicate MERGE semantics, persisted as JSON files."""

    def __init__(self, root: Path):
        self.files_path = root / "bronze_custbill_ingest_files.json"
        self.raw_path = root / "bronze_custbill_raw.json"
        self.files = self._load(self.files_path)
        self.raw = self._load(self.raw_path)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text()) if path.exists() else {}

    def register(self, staged: StagedFile, raw_lines: list[str]) -> None:
        key = f"{NS}|{staged.file_name}|{staged.sha256}"
        self.files.setdefault(
            key,
            {
                "ns": NS,
                "file_name": staged.file_name,
                "sha256": staged.sha256,
                "bytes": staged.bytes,
                "lines": staged.lines,
                "ingest_id": staged.ingest_id,
            },
        )
        for i, line in enumerate(raw_lines):
            self.raw.setdefault(
                f"{key}|{i + 1}",
                {"ns": NS, "file_name": staged.file_name, "sha256": staged.sha256, "line_no": i + 1, "line": line},
            )
        self.files_path.write_text(json.dumps(self.files, indent=1, sort_keys=True) + "\n")
        self.raw_path.write_text(json.dumps(self.raw, indent=1, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {p.name: sha256_file(p) for p in sorted(directory.iterdir()) if p.is_file()}


def check(checks: list, cid: str, expected, actual, source: str) -> None:
    checks.append(
        {
            "id": cid,
            "expected": expected,
            "actual": actual,
            "source_of_truth": source,
            "result": "pass" if expected == actual else "fail",
        }
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args()

    legacy_root = os.environ.get("OTTERWORKS_LEGACY_ROOT", "")
    if not legacy_root:
        raise SystemExit("set OTTERWORKS_LEGACY_ROOT and run: make legacy-etl-gen-data NS=cnvingest")
    seed_drop = Path(legacy_root) / "sftp-drop" / "upload"
    golden = json.loads(GOLDEN.read_text())
    golden_files = {f["file_name"]: f for f in golden["drop_files"]}
    for name, meta in golden_files.items():
        seeded = seed_drop / name
        if not seeded.exists():
            raise SystemExit(f"missing seeded drop file {seeded}; run make legacy-etl-gen-data NS=cnvingest")
        if sha256_file(seeded) != meta["sha256"]:
            raise SystemExit(f"seeded {name} does not match the golden baseline sha256; refusing to recon")

    shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
    drop = FIXTURE_ROOT / "drop"
    incoming = FIXTURE_ROOT / "incoming"
    archive = FIXTURE_ROOT / "archive"
    drop.mkdir(parents=True)
    for name in golden_files:
        shutil.copyfile(seed_drop / name, drop / name)
    # Plant the contract's transport anomalies.
    (drop / ANOMALY_NONMATCH).write_bytes(b"not a custbill feed\n")
    (drop / ANOMALY_FILEPART).write_bytes(b"HDR partial transfer in flight\n")

    checks: list = []
    bronze = JsonBronze(FIXTURE_ROOT)
    staged = ingest_batch(str(FIXTURE_ROOT), NS, bronze)

    # staged_bytes_identical — recomputed from incoming/ on the fixture target.
    incoming_shas = snapshot(incoming)
    check(
        checks,
        "staged_bytes_identical",
        {n: m["sha256"] for n, m in sorted(golden_files.items())},
        dict(sorted(incoming_shas.items())),
        "sha256 recomputed from fixture incoming/ vs golden baseline drop_files",
    )

    # atomic_visibility — no staging artifact remains visible anywhere.
    leftovers = [
        name
        for d in (incoming, archive, drop)
        for name in (os.listdir(d) if d.is_dir() else [])
        if name.startswith(".staging.")
    ]
    check(
        checks,
        "atomic_visibility",
        [],
        leftovers,
        "directory listings of drop/incoming/archive after the run; files written via hidden staging + os.replace",
    )

    # drop_deleted_after_stage — matching files removed from drop after success.
    check(
        checks,
        "drop_deleted_after_stage",
        [],
        sorted(n for n in os.listdir(drop) if n.startswith("CUSTBILL") and n.endswith(".dat")),
        "drop/ listing recomputed after the run",
    )

    # archive_copy — deterministic archive names <name>.<sha256[:16]>, bytes identical.
    expected_archive = {
        f"{n}.{m['sha256'][:16]}": m["sha256"] for n, m in sorted(golden_files.items())
    }
    check(
        checks,
        "archive_copy",
        expected_archive,
        dict(sorted(snapshot(archive).items())),
        "sha256 recomputed from fixture archive/",
    )

    # bronze_registration — counts recomputed from the fixture registry files.
    registry = json.loads(bronze.files_path.read_text())
    raw_registry = json.loads(bronze.raw_path.read_text())
    check(
        checks,
        "bronze_registration",
        {
            "file_rows": [
                {
                    "file_name": n,
                    "sha256": m["sha256"],
                    "bytes": m["bytes"],
                    # golden "records" counts body records; raw lines add HDR + TRL framing
                    "lines": m["records"] + 2,
                    "ingest_id": deterministic_ingest_id(NS, n, m["sha256"]),
                }
                for n, m in sorted(golden_files.items())
            ],
            "raw_line_rows": sum(m["records"] + 2 for m in golden_files.values()),
        },
        {
            "file_rows": [
                {k: row[k] for k in ("file_name", "sha256", "bytes", "lines", "ingest_id")}
                for _, row in sorted(registry.items())
            ],
            "raw_line_rows": len(raw_registry),
        },
        "bronze registry JSON recomputed from the fixture target after the run",
    )

    # non_matching_ignored — anomalies left untouched in drop.
    check(
        checks,
        "non_matching_ignored",
        sorted([ANOMALY_NONMATCH, ANOMALY_FILEPART]),
        sorted(os.listdir(drop)),
        "drop/ listing after the run: planted non-matching files must remain, untouched",
    )

    anomalies_detected = sorted(
        a
        for a, present in (
            (
                "non_custbill_file_in_drop",
                (drop / ANOMALY_NONMATCH).exists()
                and not (incoming / ANOMALY_NONMATCH).exists(),
            ),
            (
                "partial_transfer_suffix",
                (drop / ANOMALY_FILEPART).exists()
                and not (incoming / ANOMALY_FILEPART).exists(),
            ),
        )
        if present
    )

    # idempotent_repoll — rerun 1: empty drop is a no-op; rerun 2: re-landed
    # byte-identical file re-stages without duplicating bronze rows.
    before = {
        "incoming": snapshot(incoming),
        "archive": snapshot(archive),
        "files_rows": len(registry),
        "raw_rows": len(raw_registry),
    }
    rerun_staged = ingest_batch(str(FIXTURE_ROOT), NS, bronze)
    relanded = sorted(golden_files)[0]
    shutil.copyfile(seed_drop / relanded, drop / relanded)
    reland_staged = ingest_batch(str(FIXTURE_ROOT), NS, bronze)
    after = {
        "incoming": snapshot(incoming),
        "archive": snapshot(archive),
        "files_rows": len(json.loads(bronze.files_path.read_text())),
        "raw_rows": len(json.loads(bronze.raw_path.read_text())),
    }
    rerun_pass = (
        not rerun_staged
        and [s.file_name for s in reland_staged] == [relanded]
        and before == after
    )
    check(
        checks,
        "idempotent_repoll",
        {"empty_drop_staged": 0, "reland_staged": [relanded], "state_unchanged": True},
        {
            "empty_drop_staged": len(rerun_staged),
            "reland_staged": [s.file_name for s in reland_staged],
            "state_unchanged": before == after,
        },
        "incoming/archive sha256 snapshots and bronze registry row counts recomputed before and after both reruns",
    )

    # no_hostname_branching — static property of the conversion source.
    source = (HERE / "ingest_core.py").read_text() + (HERE / "sftp_ingest_poll_notebook.py").read_text()
    check(
        checks,
        "no_hostname_branching",
        {"hostname_references": 0, "lock_files": 0, "suppression": 0},
        {
            "hostname_references": source.count("gethostname") + source.count("os.uname"),
            "lock_files": source.lower().count("lockfile"),
            "suppression": source.count("|| true") + source.count("2>/dev/null"),
        },
        "grep of the committed conversion source; mutual exclusion is max_concurrent_runs=1 in job_ow_tp_ingest_cnvingest.json",
    )

    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": NS,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_mode": "fixture",
        "golden_baseline": str(GOLDEN.relative_to(REPO_ROOT)),
        "fixture": "local landing layout under .tp-preflight/databricks-fixture mirroring /Volumes/ow_tp/bronze/landing/cnvingest/sftp_ingest_poll; JSON registry standing in for Delta MERGE with identical keys",
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if rerun_pass else "fail",
            "evidence": "empty-drop rerun staged 0 files and left incoming/archive/bronze byte-identical; re-landing a byte-identical CUSTBILL file re-staged it with zero new bronze rows",
        },
        "planted_anomaly_detections": {
            "expected_set": ["non_custbill_file_in_drop", "partial_transfer_suffix"],
            "actual_set": anomalies_detected,
            "missing": sorted(set(["non_custbill_file_in_drop", "partial_transfer_suffix"]) - set(anomalies_detected)),
            "unexpected": sorted(set(anomalies_detected) - {"non_custbill_file_in_drop", "partial_transfer_suffix"}),
            "coverage_gap": {
                "content_level_anomalies": "owned by the parse_custbill_fixedwidth unit per contract; this unit only guarantees byte-identical transport of content anomalies into bronze raw"
            },
        },
        "unverified_paths": [
            "live SQL execution and Delta MERGE semantics on ow_tp.bronze.custbill_ingest_files_cnvingest / custbill_raw_cnvingest (fixture uses a JSON registry with identical merge keys)",
            "Unity Catalog behaviour, table grants, and permissions in the shared workspace",
            "serverless notebook-task execution, job parameter passing, and max_concurrent_runs enforcement by the Jobs service",
            "Files API / Volumes FUSE I-O behaviour, including atomicity of os.replace on /Volumes paths",
            "workspace sys.path import of ingest_core.py next to the deployed notebook",
            "serverless SQL warehouse behaviour (id 565cd2fd713738c4) under the parent's live validation window",
        ],
    }
    failed = [c["id"] for c in checks if c["result"] != "pass"]
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out} ({len(checks)} checks, {len(failed)} failed{': ' + ', '.join(failed) if failed else ''})")
    return 1 if failed or not rerun_pass else 0


if __name__ == "__main__":
    raise SystemExit(main())
