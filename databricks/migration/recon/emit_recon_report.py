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
      --anomaly 'orphan_invoice_lines=SELECT count(*) FROM ...' \
      --idempotency-evidence 'loader rerun 2026-..., counts unchanged' \
      --unverified 'source-side constraint/index parity (tiers 5-7)'
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from databricks import sql as dbsql

WAREHOUSE = "565cd2fd713738c4"
CATALOG = "ow_tp"

# An anomaly probe is a read, run with the migration service principal: one statement,
# starting at `SELECT count(`, naming every table it reads as a bare three-part name inside
# the migration catalog. Quoting is refused rather than parsed, so an identifier cannot hide
# a catalog behind a backtick.
PROBE = re.compile(r"^\s*SELECT\s+count\s*\(", re.IGNORECASE)
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COPY|SET)\b",
    re.IGNORECASE)
SOURCE = re.compile(r"\b(?:FROM|JOIN)\s+(\(|[^\s,(]+)", re.IGNORECASE)
QUOTES = re.compile(r"[`\"\[\]]")
TABLE = re.compile(rf"^{CATALOG}\.[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$", re.IGNORECASE)


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def check_probe(name: str, query: str) -> str:
    query = query.strip().rstrip(";").strip()
    if ";" in query:
        raise SystemExit(f"anomaly probe {name!r} must be a single statement")
    if not PROBE.match(query) or FORBIDDEN.search(query):
        raise SystemExit(f"anomaly probe {name!r} must be a read-only SELECT count(...)")
    if QUOTES.search(query):
        raise SystemExit(f"anomaly probe {name!r} must name its tables unquoted")
    refs = SOURCE.findall(query)
    if not refs:
        raise SystemExit(f"anomaly probe {name!r} names no table")
    for ref in refs:
        if not TABLE.match(ref):
            raise SystemExit(
                f"anomaly probe {name!r} reads {ref}: every source must be a bare "
                f"{CATALOG}.<schema>.<table> name")
    return query


def measure(pairs: list[str]) -> list[dict]:
    """Each `name=SQL` recounted on the target; the count is the anomaly-set member."""
    if not pairs:
        return []
    probes = [(n, check_probe(n, q)) for n, _, q in (p.partition("=") for p in pairs)]
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
                    help="declared anomaly class as name=SQL, recounted on the target")
    ap.add_argument("--expect", action="append", default=[],
                    help="expected anomaly class as name=count")
    ap.add_argument("--idempotency-result", required=True, choices=["pass", "fail"],
                    help="outcome of the actual loader rerun")
    ap.add_argument("--idempotency-evidence", required=True)
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

    actual = measure(args.anomaly)
    expected = [{"anomaly": n, "count": int(c)}
                for n, _, c in (p.partition("=") for p in args.expect)]

    def key(a: dict) -> tuple:
        return a["anomaly"], a["count"]

    missing = [a for a in expected if key(a) not in {key(b) for b in actual}]
    unexpected = [a for a in actual if key(a) not in {key(b) for b in expected}]

    # The harness verdict covers the harness's own tiers; the anomaly set and the rerun are
    # extra gates emitted here, so a failure in either has to survive into the artifact.
    verdict = result["verdict"]
    if missing or unexpected or args.idempotency_result != "pass":
        verdict = "FAIL"

    report = {
        "kind": "recon-report",
        "unit": result["unit"],
        "namespace": args.namespace,
        "generated_at": result["generated_at"],
        "run_mode": result["mode"],
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {"performed": True,
                              "result": args.idempotency_result,
                              "evidence": args.idempotency_evidence},
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
