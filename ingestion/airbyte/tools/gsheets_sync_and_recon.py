#!/usr/bin/env python3
"""Run the Google Sheets -> Databricks connection twice and reconcile it.

The spreadsheet is the source of truth: each tab is read back through Google's
CSV export of the shared link (no Google credentials needed for a link-shared
sheet), data rows are counted, and the count is compared with a fresh
COUNT(*) on the landed Databricks table after each sync.

Writes docs/tech-partnerships/recon/airbyte-gsheets-<ns>.recon.json
(kind: recon-report) for `make tp-validate-recon`.

Environment: same as sync_and_recon.py (AIRBYTE_*, DATABRICKS_DEMO_HOST,
DATABRICKS_DEMO_TOKEN), plus AIRBYTE_CONNECTION_ID or --connection-id.

Usage:
  gsheets_sync_and_recon.py --ns demo --connection-id <uuid> [--tabs customers invoices] [--no-sync]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_and_recon import ROOT, Airbyte, Databricks, qualified

DEFAULT_SHEET = "https://docs.google.com/spreadsheets/d/1OiNyOfHhBBDy0xyTBWduyo8kSnjMQOjPFSmJEfToF80"


def sheet_rows(sheet_url: str, tab: str) -> tuple[int, list[str]]:
    """(data-row count, header) of one tab via the gviz CSV export of a link-shared sheet."""
    sheet_id = sheet_url.rstrip("/").split("/d/")[1].split("/")[0]
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?"
        + urllib.parse.urlencode({"tqx": "out:csv", "headers": "1", "sheet": tab})
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        rows = list(csv.reader(io.StringIO(response.read().decode("utf-8"))))
    header, data = rows[0], [r for r in rows[1:] if any(cell.strip() for cell in r)]
    return len(data), header


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ns", required=True)
    parser.add_argument("--connection-id", default=os.getenv("AIRBYTE_CONNECTION_ID"))
    parser.add_argument("--sheet-url", default=DEFAULT_SHEET)
    parser.add_argument("--tabs", nargs="+", default=["customers", "invoices"])
    parser.add_argument("--warehouse-id", default=os.getenv("DATABRICKS_WAREHOUSE_ID", "565cd2fd713738c4"))
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--no-sync", action="store_true", help="only recount; do not trigger jobs")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/tech-partnerships/recon")
    args = parser.parse_args()
    if not args.connection_id:
        parser.error("--connection-id or AIRBYTE_CONNECTION_ID is required")

    schema = f"airbyte_{args.ns.replace('-', '_')}"
    dbx = Databricks(args.warehouse_id)
    expected = {tab: sheet_rows(args.sheet_url, tab) for tab in args.tabs}

    def count_all() -> dict[str, int | None]:
        out: dict[str, int | None] = {}
        for tab in args.tabs:
            try:
                out[tab] = int(dbx.scalar(f"SELECT COUNT(*) FROM {qualified(args.catalog, schema, tab)}"))
            except SystemExit as exc:  # table absent: the stream did not land
                print(f"{tab}: {exc}", file=sys.stderr)
                out[tab] = None
        return out

    started = time.monotonic()
    jobs: list[dict] = []
    counts_per_run: list[dict[str, int | None]] = []
    if args.no_sync:
        counts_per_run.append(count_all())
    else:
        airbyte = Airbyte()
        for _ in range(2):
            jobs.append(airbyte.run_sync(args.connection_id))
            counts_per_run.append(count_all())
    wall_clock_s = round(time.monotonic() - started)

    final = counts_per_run[-1]
    checks = []
    for tab in args.tabs:
        rows, header = expected[tab]
        checks.append(
            {
                "id": f"rowcount:{tab}",
                "expected": rows,
                "actual": final[tab],
                "source_of_truth": f"google sheet tab '{tab}' via CSV export ({len(header)} columns, {len(set(header))} distinct names)",
                "result": "pass" if final[tab] == rows else "fail",
            }
        )
    for job in jobs:
        checks.append(
            {
                "id": f"airbyte-job:{job['jobId']}",
                "expected": "succeeded",
                "actual": job.get("status"),
                "source_of_truth": "airbyte cloud jobs api",
                "result": "pass" if job.get("status") == "succeeded" else "fail",
            }
        )

    rerun_done = len(jobs) >= 2
    all_pass = all(c["result"] == "pass" for c in checks)
    counts_stable = all(c == final for c in counts_per_run)
    report = {
        "kind": "recon-report",
        "unit": "airbyte-gsheets-billing-export",
        "namespace": args.ns,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "run_mode": "live",
        "target": f"{args.catalog}.{schema}",
        "airbyte_connection_id": args.connection_id,
        "airbyte_job_ids": [j["jobId"] for j in jobs],
        "wall_clock_seconds": wall_clock_s,
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": rerun_done,
            "result": "pass" if rerun_done and all_pass and counts_stable else "fail",
            "evidence": (
                f"two consecutive full_refresh_overwrite syncs ({', '.join(str(j['jobId']) for j in jobs)}) "
                f"landed {'identical' if counts_stable else 'DIFFERENT'} counts; counts after each run: {counts_per_run}"
                if rerun_done
                else "rerun not performed in this invocation"
            ),
        },
        "planted_anomaly_detections": {
            "expected_set": [],
            "actual_set": [],
            "missing": [],
            "unexpected": [],
            "note": "no planted anomalies are defined for the billing export sheet",
        },
        "unverified_paths": [
            "cron-scheduled sync (only API-triggered jobs were observed)",
            "column-level parity: sheet cells land as strings; typing is a silver-layer concern",
            "Fivetran-side row counts (its connector reported 0 loaded rows; not used as a source of truth)",
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"airbyte-gsheets-{args.ns}.recon.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"wrote {path}", file=sys.stderr)
    return 0 if all_pass and report["idempotency_rerun"]["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
