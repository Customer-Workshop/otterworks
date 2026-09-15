#!/usr/bin/env python3
"""Emit the repo's machine-readable recon report from a harness result.

`run_degraded_recon.py` writes the harness's own `result.json`; the tech-partnerships gate
(`make tp-validate-recon`) reads a different, smaller shape: one `<unit>.recon.json` per unit
carrying the tier outcomes plus the four things a prose summary cannot be trusted for -
whether values came from the target platform, whether idempotency was actually rerun, the
declared anomaly set compared as a set, and the paths nobody verified.

This script derives that report from the harness result and recounts each declared anomaly
class on the target warehouse, so the anomaly numbers in the report are measured, never
copied from the load's own output.

    python3 emit_recon_report.py --result .migration/recon/<unit>/result.json \
      --anomaly orphan_invoice_lines --expect orphan_invoice_lines=37 \
      --idempotency-digest .migration/recon/<unit>/idempotency/run1.json \
      --idempotency-digest .migration/recon/<unit>/idempotency/run2.json \
      --unverified 'source-side constraint/index parity (tiers 5-7)'

Idempotency is read off two target-state digests the loader wrote, one per run (row count
plus an order-independent content hash per table). `performed` and `result` are derived
from them: two digests of the same unit from two distinct runs, identical table sets and
identical hashes. A caller cannot assert a rerun that did not happen.

Probes are not taken from the command line: each declared anomaly class is a named query
in PROBES below, reviewed with the rest of this file. The caller picks a name, so no SQL
the reviewer has not seen ever reaches the warehouse.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from databricks import sql as dbsql

WAREHOUSE = "565cd2fd713738c4"

# The declared anomaly classes of pipeline 1, one recount each, per unit. Legacy behaviour
# that the migration reproduces on purpose: orphan lines (D8-01), `f_str2dt` returning NULL
# on a malformed DD-MON-YY string, and the empty CHAR(1) flag read as NULL.
PROBES = {
    "p1-invoice-header": {
        "unparseable_invoice_dt_null":
            "SELECT count(*) FROM ow_tp.silver.invoice_header"
            " WHERE invoice_dt IS NOT NULL AND invoice_dt_parsed IS NULL",
        "unparseable_due_dt_null":
            "SELECT count(*) FROM ow_tp.silver.invoice_header"
            " WHERE due_dt IS NOT NULL AND due_dt_parsed IS NULL",
    },
    "p1-invoice-line": {
        "orphan_invoice_lines":
            "SELECT count(*) FROM ow_tp.silver.invoice_line l"
            " LEFT JOIN ow_tp.silver.invoice_header h ON l.invoice_id = h.invoice_id"
            " WHERE h.invoice_id IS NULL",
        "empty_posted_yn_as_null":
            "SELECT count(*) FROM ow_tp.silver.invoice_line WHERE posted_yn IS NULL",
        "unparseable_invoice_dt_null":
            "SELECT count(*) FROM ow_tp.silver.invoice_line"
            " WHERE invoice_dt IS NOT NULL AND invoice_dt_parsed IS NULL",
    },
}


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def idempotency(unit: str, paths: list[str]) -> dict:
    """Two target-state digests of one unit, compared: the rerun proof, not an assertion."""
    if len(paths) != 2:
        raise SystemExit(
            "idempotency needs two --idempotency-digest files, one per loader run")
    runs = []
    for path in paths:
        run = json.loads(Path(path).read_text())
        if run.get("kind") != "target-state-digest":
            raise SystemExit(f"{path} is not a target-state digest")
        if run.get("unit") != unit:
            raise SystemExit(f"{path} digests unit {run.get('unit')!r}, not {unit!r}")
        if not run.get("tables"):
            raise SystemExit(f"{path} digests no table")
        runs.append(run)
    first, second = runs
    if first["finished_at"] == second["finished_at"]:
        raise SystemExit(
            "both idempotency digests finished at the same instant: one run, not a rerun")

    def state(run: dict) -> list[tuple]:
        return sorted((t["table"], t["rows"], t["content_hash"]) for t in run["tables"])

    unchanged = state(first) == state(second)
    tables = "; ".join(f"{t} {r} rows, xxhash64 xor {h}" for t, r, h in state(second))
    return {"performed": True,
            "result": "pass" if unchanged else "fail",
            "evidence": (f"loader run at {first['finished_at']} and rerun at "
                         f"{second['finished_at']}; target state "
                         f"{'identical' if unchanged else 'CHANGED'}: {tables}")}


def measure(unit: str, names: list[str]) -> list[dict]:
    """Each named probe recounted on the target; the count is the anomaly-set member."""
    if not names:
        return []
    known = PROBES.get(unit, {})
    probes = []
    for name in names:
        if name not in known:
            raise SystemExit(
                f"no anomaly probe {name!r} declared for unit {unit!r}; "
                f"known: {', '.join(sorted(known)) or 'none'}")
        probes.append((name, known[name]))
    out = []
    with sql_conn() as conn, conn.cursor() as cur:
        for name, query in probes:
            cur.execute(query)
            out.append({"anomaly": name, "count": cur.fetchone()[0]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--namespace", default="demo")
    ap.add_argument("--anomaly", action="append", default=[],
                    help="name of a declared anomaly class in PROBES, recounted on the target")
    ap.add_argument("--expect", action="append", default=[],
                    help="expected anomaly class as name=count")
    ap.add_argument("--idempotency-digest", action="append", default=[], required=True,
                    help="target-state digest written by a loader run; pass it twice")
    ap.add_argument("--unverified", action="append", default=[])
    ap.add_argument("--out")
    args = ap.parse_args()

    result_path = Path(args.result)
    result = json.loads(result_path.read_text())

    checks = [{"id": f"tier{t['tier']}_{t['name']}",
               "expected": "pass",
               "actual": "pass" if t["passed"] else "fail",
               "result": "pass" if t["passed"] else "fail",
               "source_of_truth": "dbx recon harness engine, degraded Oracle JDBC source",
               "checks_run": t["checks_run"]}
              for t in result["tiers"]]

    rerun = idempotency(result["unit"], args.idempotency_digest)
    actual = measure(result["unit"], args.anomaly)
    expected = [{"anomaly": n, "count": int(c)}
                for n, _, c in (p.partition("=") for p in args.expect)]

    def key(a: dict) -> tuple:
        return a["anomaly"], a["count"]

    missing = [a for a in expected if key(a) not in {key(b) for b in actual}]
    unexpected = [a for a in actual if key(a) not in {key(b) for b in expected}]

    # The harness verdict covers the harness's own tiers; the anomaly set and the rerun are
    # extra gates emitted here, so a failure in either has to survive into the artifact.
    verdict = result["verdict"]
    if missing or unexpected or rerun["result"] != "pass":
        verdict = "FAIL"

    report = {
        "kind": "recon-report",
        "unit": result["unit"],
        "namespace": args.namespace,
        "generated_at": result["generated_at"],
        "run_mode": result["mode"],
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": rerun,
        "planted_anomaly_detections": {"expected_set": expected,
                                       "actual_set": actual,
                                       "missing": missing,
                                       "unexpected": unexpected},
        "unverified_paths": args.unverified,
        "verdict": verdict,
        "degraded": result["degraded"],
    }
    out = Path(args.out) if args.out else result_path.with_name(f"{result['unit']}.recon.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{out} verdict={verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
