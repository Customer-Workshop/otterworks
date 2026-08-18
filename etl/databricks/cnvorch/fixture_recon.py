#!/usr/bin/env python3
"""Fixture-mode recon for the run_all_orchestration -> ow_tp_orchestrate_cnvorch unit.

Development/self-verification only (run_mode: fixture). Runs the converted
workflow's task chain — ingest -> parse -> publish_psv -> finance — as a local
orchestrator over a landing layout under the repo .tp-preflight sandbox
(mirroring /Volumes/ow_tp/bronze/landing/cnvorch/), composing the merged
sibling units' code verbatim:

  * ingest:  etl/databricks/cnvingest/ingest_core.py (imported, unmodified)
  * parse:   etl/databricks/cnvparse/fixture_recon.py's pipeline mirror
             (imported, unmodified — the same functions that unit's own
             recon proved 1:1 against its committed SQL)
  * publish: this unit's handoff rendering (render_psv imported from the
             cnvparse module; file order = line order, replace-not-append)
  * finance: etl/databricks/cnvfinance/finance_core.py (imported, unmodified
             — merged via PR #1196; the same parse/aggregate/render functions
             that unit's own recon proved against the golden report CSV)

Every check value is recomputed from the fixture target after the run; live
SQL/Delta/UC/Jobs behaviour is disclosed as unverified (parent-owned live
validation window).

Prereqs (deterministic seed, byte-identical per NS):
    export OTTERWORKS_LEGACY_ROOT=<isolated dir>
    make legacy-etl-gen-data NS=cnvorch

Usage:
    python3 etl/databricks/cnvorch/fixture_recon.py \
        --out docs/tech-partnerships/recon/run_all_orchestration-cnvorch.recon.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.append(str(REPO_ROOT / "etl/databricks/cnvingest"))
from ingest_core import StagedFile, ingest_batch  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass resolution needs the module registered
    spec.loader.exec_module(mod)
    return mod


cnvparse = _load_module("cnvparse_fixture", REPO_ROOT / "etl/databricks/cnvparse/fixture_recon.py")

NS = "cnvorch"
UNIT = "run_all_orchestration"
BASELINE = REPO_ROOT / "docs/tech-partnerships/baselines/run_all_orchestration-cnvorch.baseline.json"
JOB_SPEC = HERE / "job_ow_tp_orchestrate_cnvorch.json"
FIXTURE_ROOT = REPO_ROOT / ".tp-preflight/databricks-fixture/landing" / NS
# Pinned to the run-branch cut time (tp-run/databricks-20260818T210550Z) so the
# artifact carries no wall-clock timestamp and reruns are byte-identical.
GENERATED_AT = "2026-08-18T21:05:50Z"
STALE_ARTIFACT = "CUSTBILL_STALE_FROM_PRIOR_RUN.psv"


class JsonBronze:
    """Local stand-in for the ingest notebook's DeltaBronze (same merge keys)."""

    def __init__(self, root: Path, ns: str):
        self.ns = ns
        self.files_path = root / "bronze_custbill_ingest_files.json"
        self.raw_path = root / "bronze_custbill_raw.json"
        self.files = json.loads(self.files_path.read_text()) if self.files_path.exists() else {}
        self.raw = json.loads(self.raw_path.read_text()) if self.raw_path.exists() else {}

    def register(self, staged: StagedFile, raw_lines: list[str]) -> None:
        key = f"{self.ns}|{staged.file_name}|{staged.sha256}"
        self.files.setdefault(key, {
            "ns": self.ns, "file_name": staged.file_name, "sha256": staged.sha256,
            "bytes": staged.bytes, "lines": staged.lines, "ingest_id": staged.ingest_id,
        })
        for i, line in enumerate(raw_lines):
            self.raw.setdefault(f"{key}|{i + 1}", {
                "ns": self.ns, "file_name": staged.file_name, "sha256": staged.sha256,
                "line_no": i + 1, "line": line,
            })
        self.files_path.write_text(json.dumps(self.files, indent=1, sort_keys=True) + "\n")
        self.raw_path.write_text(json.dumps(self.raw, indent=1, sort_keys=True) + "\n")


class ChaosParseFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_dir(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {p.name: sha256_file(p) for p in sorted(directory.iterdir()) if p.is_file()}


def publish_psv(silver: list[dict], parsed_dir: Path) -> dict[str, bytes]:
    """The publish_psv task's handoff semantics (mirrors the committed
    orchestrate_publish_psv notebook): render silver back into legacy record
    bytes in line order, replace the artifact set, byte-verify after write."""
    parsed_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, list[str]] = {}
    for row in sorted(silver, key=lambda r: (r["source_file"], r["line_no"])):
        name = row["source_file"]
        if name.endswith(".dat"):
            name = name[: -len(".dat")]
        artifacts.setdefault(f"{name}.psv", []).append(cnvparse.render_psv(row))
    for name in list(os.listdir(parsed_dir)):
        if name.startswith("CUSTBILL") and name.endswith(".psv") and name not in artifacts:
            os.remove(parsed_dir / name)
    out: dict[str, bytes] = {}
    for name, lines in sorted(artifacts.items()):
        data = ("\n".join(lines) + "\n").encode("ascii")
        (parsed_dir / name).write_bytes(data)
        if (parsed_dir / name).read_bytes() != data:
            raise IOError(f"post-write verification failed for {parsed_dir / name}")
        out[name] = data
    return out


def load_finance():
    """The cnvfinance unit's composed logic (finance_core, verbatim)."""
    path = REPO_ROOT / "etl/databricks/cnvfinance/finance_core.py"
    if not path.exists():
        return None
    return _load_module("cnvfinance_finance_core", path)


def run_workflow(root: Path, chaos: str = "") -> dict:
    """One workflow run over the fixture root; returns task statuses + state."""
    ingest_root = root / "sftp_ingest_poll"
    parsed_dir = root / "finance_report" / "parsed"
    statuses: dict[str, str] = {}
    state: dict = {}
    try:
        staged = ingest_batch(str(ingest_root), NS, JsonBronze(root, NS))
        statuses["ingest"] = "SUCCESS"
        state["staged"] = [s.file_name for s in staged]
    except Exception:
        statuses["ingest"] = "FAILED"
        for t in ("parse", "publish_psv", "finance"):
            statuses[t] = "UPSTREAM_FAILED"
        raise
    try:
        if chaos == "parse_failure":
            raise ChaosParseFailure("chaos-parse-failure injected before any write")
        targets = cnvparse.run_pipeline(ingest_root / "incoming")
        statuses["parse"] = "SUCCESS"
        state["targets"] = targets
    except ChaosParseFailure:
        statuses["parse"] = "FAILED"
        statuses["publish_psv"] = "UPSTREAM_FAILED"
        statuses["finance"] = "UPSTREAM_FAILED"
        return {"statuses": statuses, "state": state, "result": "FAILED"}
    artifacts = publish_psv(targets["silver"], parsed_dir)
    statuses["publish_psv"] = "SUCCESS"
    state["published"] = {n: hashlib.sha256(b).hexdigest() for n, b in artifacts.items()}
    finance = load_finance()
    if finance is None:
        statuses["finance"] = "SKIPPED_PENDING_CNVFINANCE_MERGE"
    else:
        state["finance"] = compose_finance(finance, parsed_dir, root / "finance_report" / "reports")
        statuses["finance"] = "SUCCESS"
    return {"statuses": statuses, "state": state, "result": "SUCCESS"}


REPORT_DATE = "2026-01-15"


def compose_finance(finance, parsed_dir: Path, reports_dir: Path) -> dict:
    """The finance task, composed from the cnvfinance unit's finance_core
    verbatim (mirrors its committed notebook's file-level flow: filter inputs
    with is_report_input, parse_psv_bytes into a ParsedBatch, aggregate,
    render_report_csv, write the truthful .csv artifact, read-back verify)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    batch = finance.ParsedBatch()
    input_digests: dict[str, str] = {}
    for name in sorted(n for n in os.listdir(parsed_dir) if finance.is_report_input(n)):
        data = (parsed_dir / name).read_bytes()
        input_digests[name] = finance.sha256_hex(data)
        finance.parse_psv_bytes(data, name, batch)
    artifact_bytes = finance.render_report_csv(finance.aggregate(batch.rows))
    artifact = reports_dir / f"finance_billing_{REPORT_DATE.replace('-', '')}.csv"
    artifact.write_bytes(artifact_bytes)
    if artifact.read_bytes() != artifact_bytes:
        raise IOError(f"artifact read-back verification failed for {artifact}")
    return {
        "run_id": finance.deterministic_run_id(NS, REPORT_DATE, input_digests),
        "artifact": artifact.name,
        "artifact_sha256": finance.sha256_hex(artifact_bytes),
        "rows_input": batch.rows_input,
        "rows_aggregated": len(batch.rows),
        "rows_skipped_empty_cust": batch.rows_skipped_empty_cust,
        "rows_attributed_malformed": batch.rows_attributed_malformed,
    }


def full_state(root: Path) -> dict:
    ingest_root = root / "sftp_ingest_poll"
    return {
        "incoming": snapshot_dir(ingest_root / "incoming"),
        "archive": snapshot_dir(ingest_root / "archive"),
        "parsed": snapshot_dir(root / "finance_report" / "parsed"),
        "reports": snapshot_dir(root / "finance_report" / "reports"),
        "bronze_files": json.loads((root / "bronze_custbill_ingest_files.json").read_text()) if (root / "bronze_custbill_ingest_files.json").exists() else {},
        "bronze_raw": json.loads((root / "bronze_custbill_raw.json").read_text()) if (root / "bronze_custbill_raw.json").exists() else {},
    }


def check(checks: list, cid: str, expected, actual, source: str, result: str | None = None) -> None:
    checks.append({
        "id": cid,
        "expected": expected,
        "actual": actual,
        "source_of_truth": source,
        "result": result if result else ("pass" if expected == actual else "fail"),
    })


def static_job_checks(checks: list) -> None:
    spec = json.loads(JOB_SPEC.read_text())
    edges = {
        t["task_key"]: sorted(d["task_key"] for d in t.get("depends_on", []))
        for t in spec["tasks"]
    }
    check(
        checks, "orch-01-explicit-dependencies",
        {"ingest": [], "parse": ["ingest"], "publish_psv": ["parse"], "finance": ["publish_psv"]},
        edges,
        "depends_on edges read from etl/databricks/cnvorch/job_ow_tp_orchestrate_cnvorch.json",
    )
    check(
        checks, "orch-03-no-silent-retries",
        {"max_retries": [0, 0, 0, 0], "max_concurrent_runs": 1, "queue_enabled": True},
        {
            "max_retries": [t.get("max_retries") for t in spec["tasks"]],
            "max_concurrent_runs": spec["max_concurrent_runs"],
            "queue_enabled": spec.get("queue", {}).get("enabled", False),
        },
        "task and job settings read from the committed job spec",
    )
    check(
        checks, "orch-07-paused-schedule",
        {"quartz": "0 0 6 ? * SUN", "timezone": "UTC", "pause_status": "PAUSED", "per_stage_schedules": 0},
        {
            "quartz": spec["schedule"]["quartz_cron_expression"],
            "timezone": spec["schedule"]["timezone_id"],
            "pause_status": spec["schedule"]["pause_status"],
            "per_stage_schedules": sum(1 for t in spec["tasks"] if "schedule" in t),
        },
        "schedule block read from the committed job spec; the retired per-stage cron offsets have no schedule anywhere",
    )
    sources = "".join(
        p.read_text()
        for p in sorted(HERE.glob("*.py")) + [JOB_SPEC]
        if p.name != "fixture_recon.py"
    )
    import re as _re
    foreign_tables = _re.findall(r"ow_tp\.(?:bronze|silver|gold|ops)\.\w*?(?:cnvingest|cnvparse|cnvfinance|demo)\b", sources)
    foreign_volumes = _re.findall(r"/Volumes/ow_tp/bronze/landing/(?:cnvingest|cnvparse|cnvfinance|demo)\b", sources)
    check(
        checks, "orch-08-namespace-isolation",
        {"foreign_table_refs": [], "foreign_volume_refs": []},
        {"foreign_table_refs": foreign_tables, "foreign_volume_refs": foreign_volumes},
        "regex scan of the committed cnvorch sources: every table/volume reference is ns-parameterized; sibling names appear only as verbatim workspace source paths under /Shared/ow_tp/cnvorch/",
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args()

    legacy_root = os.environ.get("OTTERWORKS_LEGACY_ROOT", "")
    if not legacy_root:
        raise SystemExit("set OTTERWORKS_LEGACY_ROOT and run: make legacy-etl-gen-data NS=cnvorch")
    seed_drop = Path(legacy_root) / "sftp-drop" / "upload"
    baseline = json.loads(BASELINE.read_text())
    golden_files = {f["file_name"]: f for f in baseline["drop_files"]}
    for name, meta in golden_files.items():
        seeded = seed_drop / name
        if not seeded.exists():
            raise SystemExit(f"missing seeded drop file {seeded}; run make legacy-etl-gen-data NS=cnvorch")
        if sha256_file(seeded) != meta["sha256"]:
            raise SystemExit(f"seeded {name} does not match the golden baseline sha256; refusing to recon")

    finance_available = load_finance() is not None
    checks: list = []
    static_job_checks(checks)

    # ---- full run over the deterministic input -----------------------------
    shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
    drop = FIXTURE_ROOT / "sftp_ingest_poll" / "drop"
    incoming = FIXTURE_ROOT / "sftp_ingest_poll" / "incoming"
    parsed_dir = FIXTURE_ROOT / "finance_report" / "parsed"
    drop.mkdir(parents=True)
    for name in golden_files:
        shutil.copyfile(seed_drop / name, drop / name)
    # Plant a stale handoff artifact from a "previous run" (orch-05).
    parsed_dir.mkdir(parents=True)
    (parsed_dir / STALE_ARTIFACT).write_bytes(b"dead|data|from|a|prior|run\n")

    run1 = run_workflow(FIXTURE_ROOT)

    check(
        checks, "orch-04-staged-bytes-identical",
        {n: m["sha256"] for n, m in sorted(golden_files.items())},
        dict(sorted(snapshot_dir(incoming).items())),
        "sha256 recomputed from fixture incoming/ vs golden baseline drop_files",
    )
    psv_actual = {}
    for name, data in sorted((n, (parsed_dir / n).read_bytes()) for n in os.listdir(parsed_dir)):
        lines = data.decode("ascii").splitlines()
        psv_actual[name] = {"rows": len(lines), "sha256_sorted": cnvparse.sorted_set_sha256(lines)}
    check(
        checks, "orch-04-silver-psv-parity",
        {n: {"rows": m["rows"], "sha256_sorted": m["sha256_sorted"]} for n, m in sorted(baseline["psv_files"].items())},
        psv_actual,
        "published handoff artifacts re-read from finance_report/parsed/ and compared to the golden baseline per-PSV sorted-set sha256 and row counts",
    )
    legacy_parsed = Path(legacy_root) / "parsed"
    if legacy_parsed.is_dir() and list(legacy_parsed.glob("CUSTBILL*.psv")):
        check(
            checks, "orch-04-publish-bytes-identical-to-legacy",
            {p.name: sha256_file(p) for p in sorted(legacy_parsed.glob("CUSTBILL*.psv"))},
            dict(sorted(snapshot_dir(parsed_dir).items())),
            "published artifact bytes vs the deterministic legacy chain's parsed/*.psv (full-file sha256, order-sensitive)",
        )
    check(
        checks, "orch-05-explicit-handoff-replaces-artifact-set",
        {"stale_artifact_removed": True, "published": sorted(baseline["psv_files"])},
        {
            "stale_artifact_removed": not (parsed_dir / STALE_ARTIFACT).exists(),
            "published": sorted(n for n in os.listdir(parsed_dir)),
        },
        "finance input directory listing after publish_psv: planted stale CUSTBILL*.psv must be gone, artifact set replaced",
    )
    reports_dir = FIXTURE_ROOT / "finance_report" / "reports"
    finance_state = run1["state"].get("finance") or {}
    report_artifact = reports_dir / f"finance_billing_{REPORT_DATE.replace('-', '')}.csv"
    check(
        checks, "orch-04-finance-report-parity",
        {"sha256": baseline["report_csv_sha256"], "malformed": 0, "skipped_empty_cust": 0},
        {
            "sha256": sha256_file(report_artifact) if report_artifact.exists() else None,
            "malformed": finance_state.get("rows_attributed_malformed"),
            "skipped_empty_cust": finance_state.get("rows_skipped_empty_cust"),
        },
        "emitted finance CSV artifact re-read from finance_report/reports/ (sha256) vs golden baseline report_csv_sha256; composed cnvfinance finance_core ran verbatim",
    )

    # ---- chaos-injected parse failure (orch-02, must-detect) ---------------
    before_chaos = full_state(FIXTURE_ROOT)
    chaos_run = run_workflow(FIXTURE_ROOT, chaos="parse_failure")
    after_chaos = full_state(FIXTURE_ROOT)
    check(
        checks, "orch-02-failure-blocks-downstream",
        {
            "run_result": "FAILED",
            "parse": "FAILED",
            "publish_psv": "UPSTREAM_FAILED",
            "finance": "UPSTREAM_FAILED",
            "state_unchanged": True,
        },
        {
            "run_result": chaos_run["result"],
            "parse": chaos_run["statuses"].get("parse"),
            "publish_psv": chaos_run["statuses"].get("publish_psv"),
            "finance": chaos_run["statuses"].get("finance"),
            "state_unchanged": before_chaos == after_chaos,
        },
        "chaos-injected parse failure: task statuses from the orchestrated run, state sha256 snapshots recomputed before and after",
    )

    # ---- idempotent full-workflow rerun over processed state (orch-06) -----
    before_rerun = full_state(FIXTURE_ROOT)
    rerun = run_workflow(FIXTURE_ROOT)
    after_rerun = full_state(FIXTURE_ROOT)
    rerun_pass = (
        rerun["result"] == "SUCCESS"
        and rerun["state"].get("staged") == []
        and before_rerun == after_rerun
    )
    check(
        checks, "orch-06-idempotent-rerun",
        {"result": "SUCCESS", "repoll_staged": [], "state_unchanged": True},
        {
            "result": rerun["result"],
            "repoll_staged": rerun["state"].get("staged"),
            "state_unchanged": before_rerun == after_rerun,
        },
        "actual full-workflow rerun over the already-processed state (empty drop); every dir/registry snapshot recomputed before and after",
    )

    # ---- empty-input end-to-end (write-empty-result) ------------------------
    empty_root = FIXTURE_ROOT.parent / f"{NS}-empty"
    shutil.rmtree(empty_root, ignore_errors=True)
    (empty_root / "sftp_ingest_poll" / "drop").mkdir(parents=True)
    empty_run = run_workflow(empty_root)
    empty_parsed = empty_root / "finance_report" / "parsed"
    empty_expected = {
        "result": "SUCCESS",
        "staged": [],
        "silver_rows": 0,
        "parsed_dir_present": True,
        "parsed_artifacts": [],
    }
    check(
        checks, "empty-input-write-empty-result",
        empty_expected,
        {
            "result": empty_run["result"],
            "staged": empty_run["state"].get("staged"),
            "silver_rows": len(empty_run["state"].get("targets", {}).get("silver", [])),
            "parsed_dir_present": empty_parsed.is_dir(),
            "parsed_artifacts": sorted(n for n in os.listdir(empty_parsed) if n.endswith(".psv")) if empty_parsed.is_dir() else None,
        },
        "fresh empty root run end-to-end; state recomputed from the fixture target",
    )
    empty_report = empty_root / "finance_report" / "reports" / f"finance_billing_{REPORT_DATE.replace('-', '')}.csv"
    check(
        checks, "empty-input-header-only-csv",
        baseline["empty_report_csv_sha256"],
        sha256_file(empty_report) if empty_report.exists() else None,
        "header-only CSV artifact re-read from the empty-input run's reports/ dir vs golden baseline empty_report_csv_sha256",
    )

    detected = ["chaos-parse-failure"] if (
        chaos_run["result"] == "FAILED" and chaos_run["statuses"].get("publish_psv") == "UPSTREAM_FAILED"
    ) else []
    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": NS,
        "generated_at": GENERATED_AT,
        "run_mode": "fixture",
        "golden_baseline": str(BASELINE.relative_to(REPO_ROOT)),
        "fixture": "local landing layout under .tp-preflight/databricks-fixture mirroring /Volumes/ow_tp/bronze/landing/cnvorch/; JSON registry standing in for the ingest Delta MERGE; the parse step runs the cnvparse unit's fixture mirror (proved 1:1 against its committed SQL by that unit's recon); the task chain is driven by a local orchestrator honoring the same depends_on edges as the committed job spec",
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if rerun_pass else "fail",
            "evidence": "an actual full-workflow rerun over the already-processed state (empty drop) succeeded, re-poll staged nothing, and every incoming/archive/parsed/reports/bronze snapshot was byte-identical before and after",
        },
        "planted_anomaly_detections": {
            "expected_set": ["chaos-parse-failure"],
            "actual_set": detected,
            "missing": sorted({"chaos-parse-failure"} - set(detected)),
            "unexpected": sorted(set(detected) - {"chaos-parse-failure"}),
            "coverage_gap": {
                "content_level_anomalies": "owned by the parse unit's contract (parse_custbill_fixedwidth-cnvparse), whose logic this workflow runs verbatim; this unit's deterministic input is clean and quarantine stayed empty",
                "transport_level_anomalies": "owned by the ingest unit's contract (sftp_ingest_poll-cnvingest), whose code this workflow runs verbatim; this unit plants none",
            },
        },
        "unverified_paths": [
            "live Jobs service semantics: depends_on blocking, UPSTREAM_FAILED propagation, max_retries=0, max_concurrent_runs=1 queueing, paused quartz schedule (verified only against the committed job spec + local orchestrator)",
            "live Spark SQL execution of the composed cnvparse pipeline (read_files, temp views, INSERT OVERWRITE) on Databricks",
            "Delta table semantics (DDL, INSERT OVERWRITE isolation) in ow_tp.bronze/silver/gold/ops",
            "Unity Catalog behavior and permissions for the ow_tp catalog objects",
            "serverless notebook-task execution and job-parameter passing (ns, chaos)",
            "Files API / Volumes FUSE I-O behaviour for the publish_psv artifact replacement on /Volumes paths",
            "dbutils.notebook.run composition of the vendored cnvingest notebook",
            "live end-to-end run of job ow_tp_orchestrate_cnvorch (parent-owned live validation window)",
        ],
        "notes": "generated_at is pinned to the run-branch cut time for artifact determinism; the finance task composes the merged cnvfinance unit's finance_core verbatim (PR #1196).",
    }
    failed = [c["id"] for c in checks if c["result"] == "fail"]
    skipped = [c["id"] for c in checks if c["result"] == "skipped"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out} ({len(checks)} checks, {len(failed)} failed, {len(skipped)} skipped{': ' + ', '.join(failed + skipped) if failed or skipped else ''})")
    return 1 if failed or not rerun_pass else 0


if __name__ == "__main__":
    raise SystemExit(main())
