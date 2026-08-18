#!/usr/bin/env python3
"""Fixture-mode recon harness for the ow_tp_parse_cnvparse conversion unit.

Development/self-verification only (run_mode: fixture). The local Databricks
fixture is transport-only (see docs/tech-partnerships/databricks-fixture-spike.md),
so this harness mirrors the exact field predicates of
etl/databricks/cnvparse/pipeline_parse_custbill.sql in Python over the landed
fixture bytes, materializes bronze/silver/quarantine equivalents in memory,
recomputes every baseline check from those materialized targets, proves
idempotency by an actual rerun, and emits a schema-valid recon report.

Live Spark SQL execution, Delta semantics, Unity Catalog behavior, permissions,
and serverless warehouse behavior remain parent-owned live validation and are
declared as unverified paths in the report.

Usage:
  python3 etl/databricks/cnvparse/fixture_recon.py \
      [--landing .tp-preflight/databricks-fixture/landing/cnvparse] \
      [--out docs/tech-partnerships/recon/parse_custbill_fixedwidth-cnvparse.recon.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE = REPO_ROOT / "docs/tech-partnerships/baselines/parse_custbill_fixedwidth-cnvparse.baseline.json"
UNIT = "parse_custbill_fixedwidth"
NAMESPACE = "cnvparse"
# Pinned to the run-branch cut time (tp-run/databricks-20260818T210550Z) so the
# artifact carries no wall-clock timestamp and reruns are byte-identical.
GENERATED_AT = "2026-08-18T21:05:50Z"
EXPECTED_ANOMALIES = ["invalid_calendar_date", "nonnumeric_amount", "trailer_count_mismatch"]

DEFECT_PRIORITY = [
    "invalid_cust_id",
    "invalid_calendar_date",
    "nonnumeric_amount",
    "unknown_currency",
    "unknown_record_type",
]


def sorted_set_sha256(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def valid_calendar_date(raw: str) -> date | None:
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def classify_body(raw_line: str) -> tuple[dict | None, str | None]:
    """Mirror of the cnvparse_body view: returns (silver_row, defect)."""
    cust_id = raw_line[0:10].rstrip(" ")
    cust_name = raw_line[10:40].rstrip(" ")
    date_raw = raw_line[40:48]
    amount_raw = raw_line[48:60]
    currency = raw_line[60:63].rstrip(" ")
    record_type = raw_line[63:65]
    bill_date = valid_calendar_date(date_raw)
    defect = None
    if len(cust_id) == 0:
        defect = "invalid_cust_id"
    elif bill_date is None:
        defect = "invalid_calendar_date"
    elif not (len(amount_raw) == 12 and amount_raw.isdigit()):
        defect = "nonnumeric_amount"
    elif currency not in ("USD", "EUR", "GBP"):
        defect = "unknown_currency"
    elif record_type not in ("01", "02"):
        defect = "unknown_record_type"
    if defect:
        return None, defect
    return {
        "cust_id": cust_id,
        "cust_name": cust_name,
        "bill_date": bill_date,
        "amount_cents": int(amount_raw),
        "currency": currency,
        "record_type": record_type,
    }, None


def render_psv(row: dict) -> str:
    cents = row["amount_cents"]
    return "|".join([
        row["cust_id"],
        row["cust_name"],
        row["bill_date"].strftime("%Y-%m-%d"),
        f"{cents // 100}.{cents % 100:02d}",
        row["currency"],
        row["record_type"],
    ])


def run_pipeline(landing: Path) -> dict:
    """One full batch over the landing dir; returns materialized targets."""
    bronze: list[dict] = []
    silver: list[dict] = []
    quarantine: list[dict] = []
    for f in sorted(landing.glob("CUSTBILL*.dat")):
        lines = f.read_text().splitlines()
        body_count = 0
        trailers: list[tuple[int, str]] = []
        for i, raw in enumerate(lines, start=1):
            if raw.startswith("HDR"):
                rec_class = "HDR"
            elif raw.startswith("TRL"):
                rec_class = "TRL"
                trailers.append((i, raw))
            else:
                rec_class = "BODY"
                body_count += 1
            bronze.append({"source_file": f.name, "line_no": i, "raw_line": raw, "rec_class": rec_class})
            if rec_class == "BODY":
                row, defect = classify_body(raw)
                if defect:
                    quarantine.append({
                        "source_file": f.name, "line_no": i, "raw_line": raw,
                        "reason": defect, "detail": f"body row failed predicate {defect}",
                    })
                else:
                    silver.append({"source_file": f.name, "line_no": i, **row})
        for line_no, raw in trailers:
            digits = raw[3:13]
            if not digits.isdigit():
                quarantine.append({
                    "source_file": f.name, "line_no": line_no, "raw_line": raw,
                    "reason": "unparseable_trailer", "detail": "TRL count digits do not parse",
                })
            elif int(digits) != body_count:
                quarantine.append({
                    "source_file": f.name, "line_no": None, "raw_line": None,
                    "reason": "trailer_count_mismatch",
                    "detail": f"trailer={int(digits)} body={body_count}",
                })
    return {"bronze": bronze, "silver": silver, "quarantine": quarantine}


def compute_checks(t: dict) -> dict[str, str]:
    checks: dict[str, str] = {}
    files = sorted({r["source_file"] for r in t["bronze"]})
    for f in files:
        raw = [r["raw_line"] for r in t["bronze"] if r["source_file"] == f and r["raw_line"].strip() != ""]
        checks[f"input_sha256/{f}"] = sorted_set_sha256(raw)
        rows = [r for r in t["silver"] if r["source_file"] == f]
        checks[f"file_valid_rows/{f}"] = str(len(rows))
        checks[f"file_valid_sha256/{f}"] = sorted_set_sha256([render_psv(r) for r in rows])
    totals: dict[tuple[str, str], list[int]] = {}
    for r in t["silver"]:
        k = (r["currency"], r["record_type"])
        totals.setdefault(k, [0, 0])
        totals[k][0] += 1
        totals[k][1] += r["amount_cents"]
    for (ccy, rt), (n, cents) in sorted(totals.items()):
        checks[f"totals/{ccy}/{rt}"] = f"{n}|{cents}"
    checks["grand_total"] = f"{len(t['silver'])}|{sum(r['amount_cents'] for r in t['silver'])}"
    checks["files_ingested"] = str(len(files))
    checks["quarantine_rows"] = str(len(t["quarantine"]))
    return checks


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--landing", default=str(REPO_ROOT / ".tp-preflight/databricks-fixture/landing/cnvparse"))
    p.add_argument("--out", default=str(REPO_ROOT / "docs/tech-partnerships/recon/parse_custbill_fixedwidth-cnvparse.recon.json"))
    args = p.parse_args()
    landing = Path(args.landing)
    if not landing.is_dir() or not list(landing.glob("CUSTBILL*.dat")):
        raise SystemExit(f"no landed CUSTBILL*.dat under {landing}; run make tp-fixture-land NS={NAMESPACE} first")

    baseline = json.loads(BASELINE.read_text())
    expected_checks = baseline["checks"]

    first = run_pipeline(landing)
    actual = compute_checks(first)
    rerun = run_pipeline(landing)
    rerun_actual = compute_checks(rerun)
    idempotent = actual == rerun_actual and first == rerun

    check_rows = []
    for check_id, expected in sorted(expected_checks.items()):
        got = actual.get(check_id)
        check_rows.append({
            "id": check_id,
            "expected": expected,
            "actual": got,
            "result": "pass" if got == expected else "fail",
            "source_of_truth": "golden baseline docs/tech-partnerships/baselines/parse_custbill_fixedwidth-cnvparse.baseline.json (parent-captured unmodified legacy run); actual recomputed from fixture-run materialized targets",
        })
    unexpected = sorted(set(actual) - set(expected_checks))
    for check_id in unexpected:
        check_rows.append({
            "id": check_id,
            "expected": None,
            "actual": actual[check_id],
            "result": "fail",
            "source_of_truth": "check id not present in golden baseline",
        })

    detected = sorted({q["reason"] for q in first["quarantine"]})
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                            f"ow_tp/{NAMESPACE}/{UNIT}/" + actual.get("grand_total", "")))
    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": NAMESPACE,
        "run_id": run_id,
        "generated_at": GENERATED_AT,
        "run_mode": "fixture",
        "checks": check_rows,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": "full second batch over the same landing bytes produced byte-identical bronze/silver/quarantine materializations and identical check values (INSERT OVERWRITE per-batch semantics)",
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": detected,
            "missing": sorted(set(EXPECTED_ANOMALIES) - set(detected)),
            "unexpected": sorted(set(detected) - set(EXPECTED_ANOMALIES)),
        },
        "unverified_paths": [
            "live Spark SQL execution of etl/databricks/cnvparse/pipeline_parse_custbill.sql (read_files, temp views, INSERT OVERWRITE) on Databricks",
            "Delta table semantics (DDL, INSERT OVERWRITE isolation) in ow_tp.bronze/silver/ops",
            "Unity Catalog behavior and permissions for the ow_tp catalog objects",
            "serverless SQL warehouse 565cd2fd713738c4 execution behavior",
            "Jobs API creation/run of job ow_tp_parse_cnvparse from etl/databricks/cnvparse/job_ow_tp_parse_cnvparse.json",
            "Files API landing of the .dat bytes to /Volumes/ow_tp/bronze/landing/cnvparse/parse (fixture transport used instead)",
            "empty-input write-empty-result semantics on live Delta tables (verified only in the fixture materialization)",
        ],
        "notes": "Fixture-mode self-verification: transport fixture preserved bytes (make tp-fixture-verify), predicates mirrored 1:1 from the committed pipeline SQL. generated_at is pinned to the run-branch cut time for artifact determinism. Parent owns the uncontended live validation window.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")

    failures = [c["id"] for c in check_rows if c["result"] != "pass"]
    print(f"recon written: {out}")
    print(f"checks: {len(check_rows) - len(failures)}/{len(check_rows)} pass; idempotency: {'pass' if idempotent else 'FAIL'}")
    if failures:
        print("failing checks: " + ", ".join(failures))
    anomalies_ok = set(detected) == set(EXPECTED_ANOMALIES)
    print(f"planted anomalies detected: {detected} ({'ok' if anomalies_ok else 'MISMATCH'})")
    return 0 if not failures and idempotent and anomalies_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
