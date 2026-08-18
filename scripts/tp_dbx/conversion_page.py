#!/usr/bin/env python3
"""Add the conversion page to the migration dashboard, live from a run's outputs.

The base branch intentionally says nothing about converted outputs: the
conversion fan-out's children create their tables during a run, so this tool
discovers what actually exists in the workspace (`SHOW TABLES ... LIKE`),
verifies every widget's dataset returns rows, and only then appends the page
to `ow_tp_billing_migration_<ns>` and re-publishes.

Widgets, in demo order:
  - the finance report's currency x record-type rows: legacy CSV (landed as
    `ow_tp.ops.legacy_finance_report_<ns>`) next to the converted gold table,
    with a delta column that must be all zeros
  - the delivery/evidence record that replaced the legacy sendmail pipe
  - ingest / parse / quarantine counters from the converted tables
  - a receipt table mapping each legacy script to its converted job and PR

Usage:
  python3 scripts/tp_dbx/conversion_page.py --ns demo --receipt receipt.json
where receipt.json is [{"script": ..., "job": ..., "pr": ...}, ...].
The legacy side prefers the ops mirror the converted finance job landed
(`ow_tp.ops.legacy_finance_report_cnv*`); pass --legacy-report <csv> to land
one as `ow_tp.ops.legacy_finance_report_<ns>` when no mirror exists yet.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sql as S  # noqa: E402
from client import Databricks, DbxError, require_ident, require_ns  # noqa: E402
from showcase import _counter, _table, dashboard_name, find_dashboard  # noqa: E402

PAGE_NAME = "conversion"


def discover(dbx: Databricks, catalog: str, schema: str, pattern: str) -> list[str]:
    result = dbx.sql_ok(f"SHOW TABLES IN {catalog}.{schema} LIKE '{pattern}'")
    return sorted(f"{catalog}.{schema}.{row[1]}" for row in result.rows)


def pick(tables: list[str], preferred_ns: str) -> str | None:
    """Prefer the dedicated unit namespace; fall back to any converted table."""
    for table in tables:
        if table.endswith(f"_{preferred_ns}"):
            return table
    return tables[0] if tables else None


def rows_of(dbx: Databricks, query: str) -> int:
    return len(dbx.sql_ok(query).rows)


def columns_of(dbx: Databricks, table: str) -> list[str]:
    return [c.lower() for c in dbx.sql_ok(f"SELECT * FROM {table} LIMIT 1").columns]


def record_type_column(columns: list[str], table: str) -> str:
    for candidate in ("record_type_name", "record_type"):
        if candidate in columns:
            return candidate
    raise SystemExit(f"{table} carries no record type column: {columns}")


def amount_expr(columns: list[str], alias: str, table: str) -> str:
    if "total_amount_cents" in columns:
        return f"{alias}.total_amount_cents / 100.0"
    if "total_amount" in columns:
        return f"{alias}.total_amount"
    raise SystemExit(f"{table} carries no total_amount/total_amount_cents column: {columns}")


def land_legacy_report(dbx: Databricks, table: str, csv_path: Path) -> str:
    with csv_path.open(newline="") as handle:
        entries = list(csv.DictReader(handle))
    if not entries:
        raise SystemExit(f"legacy report {csv_path} carried no rows")
    values = []
    for row in entries:
        currency = row["Currency"]
        record_type = row["RecordType"]
        if not (currency.isalnum() and record_type.isalnum()):
            raise SystemExit(f"legacy report carried a non-alphanumeric code: {row!r}")
        count = int(row["RecordCount"])
        dollars, _, cents = row["TotalAmount"].partition(".")
        amount_cents = int(dollars) * 100 + int((cents + "00")[:2])
        values.append(f"('{currency}', '{record_type}', {count}, {amount_cents})")
    dbx.sql_ok(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "currency STRING, record_type STRING, record_count BIGINT, "
        "total_amount_cents BIGINT COMMENT 'Report dollars held as cents') USING DELTA "
        "COMMENT 'Legacy finance_excel_report.pl output, landed for the conversion page'"
    )
    dbx.sql_ok(f"INSERT OVERWRITE {table} VALUES " + ",\n".join(values))
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default="demo")
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--legacy-report",
                        help="legacy finance CSV to land when no ops mirror exists yet")
    parser.add_argument("--receipt", required=True,
                        help="JSON list of {script, job, pr} rows for the receipt table")
    args = parser.parse_args()
    ns = require_ns(args.ns)
    catalog = require_ident(args.catalog, "catalog")
    dbx = Databricks()

    ingest_files = pick(discover(dbx, catalog, "bronze", "custbill_ingest_files_cnv*"), "cnvingest")
    ingest_raw = pick(discover(dbx, catalog, "bronze", "custbill_raw_cnv*"), "cnvingest")
    parsed = pick(discover(dbx, catalog, "silver", "custbill_parsed_cnv*"), "cnvparse")
    quarantine = pick(discover(dbx, catalog, "silver", "custbill_parse_quarantine_cnv*"), "cnvparse")
    summary = pick(discover(dbx, catalog, "gold", "finance_billing_summary_cnv*"), "cnvfinance")
    delivery = pick(discover(dbx, catalog, "gold", "finance_report_delivery_cnv*"), "cnvfinance")
    print("discovered converted tables:")
    for label, table in (("ingest files", ingest_files), ("ingest raw", ingest_raw),
                         ("parsed", parsed), ("parse quarantine", quarantine),
                         ("finance summary", summary), ("delivery", delivery)):
        print(f"  {label}: {table or 'ABSENT'}")
    missing = [t for t in (ingest_files, ingest_raw, parsed, quarantine, summary, delivery) if not t]
    if missing:
        raise SystemExit("conversion outputs incomplete; build the page only from tables that exist")

    legacy = pick(discover(dbx, catalog, "ops", "legacy_finance_report_cnv*"), "cnvfinance")
    if legacy and not rows_of(dbx, f"SELECT 1 FROM {legacy} LIMIT 1"):
        print(f"  legacy mirror {legacy} is empty; landing from CSV instead")
        legacy = None
    if legacy:
        print(f"  legacy mirror: {legacy}")
    elif args.legacy_report:
        legacy = land_legacy_report(
            dbx, f"{catalog}.ops.legacy_finance_report_{ns}", Path(args.legacy_report))
        print(f"  legacy mirror: {legacy} (landed from {args.legacy_report})")
    else:
        raise SystemExit("no ops legacy mirror found and no --legacy-report given")

    receipt_rows = json.loads(Path(args.receipt).read_text())
    if not receipt_rows:
        raise SystemExit("receipt file carried no rows")
    for entry in receipt_rows:
        for key in ("script", "job", "pr"):
            value = entry.get(key, "")
            if not value or not value.isprintable() or "'" in value or "\\" in value:
                raise SystemExit(f"receipt row has a missing or unsafe {key}: {entry!r}")
    receipt_values = ",\n".join(
        f"('{e['script']}', '{e['job']}', '{e['pr']}')" for e in receipt_rows
    )

    # the summary/mirror schemas are the converted unit's to define; adapt to
    # whichever column names it landed with rather than assuming them
    legacy_columns = columns_of(dbx, legacy)
    summary_columns = columns_of(dbx, summary)
    legacy_rt = record_type_column(legacy_columns, legacy)
    summary_rt = record_type_column(summary_columns, summary)
    legacy_amount = amount_expr(legacy_columns, "l", legacy)
    lakehouse_amount = f"coalesce({amount_expr(summary_columns, 'g', summary)}, 0)"
    parity_query = (
        f"SELECT l.currency, l.{legacy_rt} AS record_type, "
        f"l.record_count AS legacy_records, "
        f"{legacy_amount} AS legacy_amount, "
        f"{lakehouse_amount} AS lakehouse_amount, "
        f"{lakehouse_amount} - {legacy_amount} AS delta "
        f"FROM {legacy} l "
        f"LEFT JOIN {summary} g ON g.currency = l.currency AND g.{summary_rt} = l.{legacy_rt} "
        f"ORDER BY l.currency, l.{legacy_rt}"
    )
    datasets = [
        ("cnv_summary", (
            f"SELECT (SELECT count(*) FROM {ingest_files}) AS files_ingested, "
            f"(SELECT count(*) FROM {ingest_raw}) AS raw_lines, "
            f"(SELECT count(*) FROM {parsed}) AS parsed_records, "
            f"(SELECT count(*) FROM {quarantine}) AS quarantined")),
        ("cnv_parity", parity_query),
        ("cnv_parity_state", f"SELECT count_if(delta != 0) AS rows_off FROM ({parity_query})"),
        ("cnv_delivery", ""),  # filled in below from the delivery table's actual columns
        ("cnv_receipt", (
            "SELECT script, job, pr FROM (VALUES " + receipt_values +
            ") AS receipt(script, job, pr) ORDER BY script")),
    ]

    # delivery table columns are the converted unit's to define; take what exists
    delivery_columns = columns_of(dbx, delivery)
    preferred = ("report_date", "run_id", "artifact_path", "artifact_sha256",
                 "artifact_bytes", "delivery_status", "status", "mail_transport", "delivered_at")
    wanted = [c for c in preferred if c in delivery_columns] or delivery_columns[:5]
    datasets[3] = ("cnv_delivery", f"SELECT {', '.join(wanted)} FROM {delivery} ORDER BY 1 DESC")

    for name, query in datasets:
        count = rows_of(dbx, query)
        print(f"dataset {name}: {count} rows")
        if count == 0:
            raise SystemExit(f"dataset {name} returned no rows; refusing to publish an empty widget")
    off = int(dbx.sql_ok(datasets[2][1]).scalar() or 0)
    if off:
        raise SystemExit(f"finance parity has {off} non-zero delta rows; not publishing a red page")

    layout = [
        _counter("cnv_files", "cnv_summary", "files_ingested", "Feed files ingested",
                 {"x": 0, "y": 0, "width": 3, "height": 3}),
        _counter("cnv_raw", "cnv_summary", "raw_lines", "Raw lines landed",
                 {"x": 3, "y": 0, "width": 3, "height": 3}),
        _counter("cnv_parsed", "cnv_summary", "parsed_records", "Records parsed",
                 {"x": 6, "y": 0, "width": 3, "height": 3}),
        _counter("cnv_quarantined", "cnv_summary", "quarantined", "Records quarantined",
                 {"x": 9, "y": 0, "width": 3, "height": 3}),
        _table("cnv_parity_table", "cnv_parity", [
            ("currency", "Currency"),
            ("record_type", "Record type"),
            ("legacy_records", "Legacy records"),
            ("legacy_amount", "Legacy report says"),
            ("lakehouse_amount", "Lakehouse says"),
            ("delta", "Difference"),
        ], "The finance report, to the cent", {"x": 0, "y": 3, "width": 9, "height": 6}),
        _counter("cnv_rows_off", "cnv_parity_state", "rows_off", "Rows off by a cent or more",
                 {"x": 9, "y": 3, "width": 3, "height": 6}),
        _table("cnv_delivery_table", "cnv_delivery",
               [(c, c.replace("_", " ").title()) for c in wanted],
               "Verified delivery — no more silent sendmail", {"x": 0, "y": 9, "width": 6, "height": 5}),
        _table("cnv_receipt_table", "cnv_receipt", [
            ("script", "Legacy script"),
            ("job", "Converted job"),
            ("pr", "Merged PR"),
        ], "Who did the conversion work", {"x": 6, "y": 9, "width": 6, "height": 5}),
    ]

    name = dashboard_name(S.Names(catalog=catalog, ns=ns))
    existing = find_dashboard(dbx, name)
    if not existing:
        raise SystemExit(f"dashboard {name} not found; run `make dbx-showcase CMD=dashboard NS={ns}` first")
    current = dbx.ok("GET", f"/api/2.0/lakeview/dashboards/{existing['dashboard_id']}")
    spec = json.loads(current["serialized_dashboard"])
    spec["datasets"] = [d for d in spec.get("datasets", []) if not d["name"].startswith("cnv_")]
    spec["datasets"] += [{"name": key, "displayName": key, "queryLines": [query]} for key, query in datasets]
    spec["pages"] = [p for p in spec.get("pages", []) if p.get("name") != PAGE_NAME]
    spec["pages"].append({"name": PAGE_NAME, "displayName": "The converted estate", "layout": layout})
    body = {
        "display_name": name,
        "warehouse_id": dbx.warehouse_id,
        "serialized_dashboard": json.dumps(spec),
        "etag": current.get("etag", ""),
    }
    result = dbx.ok("PATCH", f"/api/2.0/lakeview/dashboards/{existing['dashboard_id']}", body)
    dashboard_id = result["dashboard_id"]
    dbx.ok("POST", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
           {"embed_credentials": True, "warehouse_id": dbx.warehouse_id})
    print(f"conversion page published: {dbx.host}/dashboardsv3/{dashboard_id}/published")
    return 0


def entrypoint() -> int:
    try:
        return main()
    except DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
