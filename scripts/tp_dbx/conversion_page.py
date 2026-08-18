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
    if not all(c.isalnum() or c in "_*" for c in pattern):
        raise SystemExit(f"table pattern must be [A-Za-z0-9_*]+: {pattern!r}")
    result = dbx.sql_ok(f"SHOW TABLES IN {catalog}.{schema} LIKE '{pattern}'")
    return sorted(
        f"{catalog}.{schema}.{require_ident(row[1], 'discovered table')}"
        for row in result.rows
    )


def conv_ns_of(table: str) -> str:
    """Namespace suffix of a converted table (`..._cnvorch` -> `cnvorch`)."""
    return "cnv" + table.rsplit("_cnv", 1)[1]


def rows_of(dbx: Databricks, query: str) -> int:
    return len(dbx.sql_ok(query).rows)


def columns_of(dbx: Databricks, table: str) -> list[str]:
    return [require_ident(c.lower(), f"{table} column")
            for c in dbx.sql_ok(f"SELECT * FROM {table} LIMIT 1").columns]


def record_type_column(columns: list[str], table: str) -> str:
    for candidate in ("record_type_name", "record_type"):
        if candidate in columns:
            return candidate
    raise SystemExit(f"{table} carries no record type column: {columns}")


def count_expr(columns: list[str], alias: str, table: str) -> str:
    for candidate in ("record_count", "legacy_record_count", "records"):
        if candidate in columns:
            return f"{alias}.{candidate}"
    raise SystemExit(f"{table} carries no record count column: {columns}")


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
        try:
            currency = row["Currency"]
            record_type = row["RecordType"]
            if not (currency.isalnum() and record_type.isalnum()):
                raise SystemExit(f"legacy report carried a non-alphanumeric code: {row!r}")
            count = int(row["RecordCount"])
            raw_amount = row["TotalAmount"].strip()
            sign = -1 if raw_amount.startswith("-") else 1
            dollars, _, cents = raw_amount.lstrip("-").partition(".")
            amount_cents = sign * (int(dollars) * 100 + int((cents + "00")[:2]))
        except (KeyError, ValueError) as exc:
            raise SystemExit(f"legacy report row is malformed ({exc!r}): {row!r}") from exc
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

    # a run's outputs are coherent only within one conversion namespace: either
    # each unit's own (cnvingest/cnvparse/cnvfinance) or a single shared one
    # (e.g. the orchestrator's cnvorch); never mix namespaces across slots
    slots = [
        ("ingest files", "bronze", "custbill_ingest_files_cnv*", "cnvingest"),
        ("ingest raw", "bronze", "custbill_raw_cnv*", "cnvingest"),
        ("parsed", "silver", "custbill_parsed_cnv*", "cnvparse"),
        ("parse quarantine", "silver", "custbill_parse_quarantine_cnv*", "cnvparse"),
        ("finance summary", "gold", "finance_billing_summary_cnv*", "cnvfinance"),
        ("delivery", "gold", "finance_report_delivery_cnv*", "cnvfinance"),
    ]
    found = {label: discover(dbx, catalog, schema, pattern)
             for label, schema, pattern, _ in slots}
    if all(any(conv_ns_of(t) == unit for t in found[label]) for label, _, _, unit in slots):
        chosen = {label: next(t for t in found[label] if conv_ns_of(t) == unit)
                  for label, _, _, unit in slots}
    else:
        common = set.intersection(*(({conv_ns_of(t) for t in tables})
                                    for tables in found.values()))
        if not common:
            raise SystemExit(
                "no conversion namespace carries all six outputs; refusing to mix runs")
        conv_ns = "cnvorch" if "cnvorch" in common else sorted(common)[-1]
        chosen = {label: next(t for t in found[label] if conv_ns_of(t) == conv_ns)
                  for label, _, _, _ in slots}
    print("discovered converted tables:")
    for label, _, _, _ in slots:
        print(f"  {label}: {chosen[label]}")
    ingest_files, ingest_raw, parsed, quarantine, summary, delivery = (
        chosen[label] for label, _, _, _ in slots)

    # candidates: the mirror landed by the same conversion namespace the gold
    # summary came from, then the ns-suffixed mirror a previous run of this
    # tool may have landed itself; take the first with rows
    finance_ns = conv_ns_of(summary)
    legacy = None
    candidates = discover(dbx, catalog, "ops", f"legacy_finance_report_{finance_ns}")
    candidates += discover(dbx, catalog, "ops", f"legacy_finance_report_{ns}")
    for candidate in candidates:
        if rows_of(dbx, f"SELECT 1 FROM {candidate} LIMIT 1"):
            legacy = candidate
            break
        print(f"  legacy mirror {candidate} is empty; skipping")
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
    legacy_count = count_expr(legacy_columns, "l", legacy)
    legacy_amount = amount_expr(legacy_columns, "l", legacy)
    lakehouse_amount = f"coalesce({amount_expr(summary_columns, 'g', summary)}, 0)"

    def latest_slice(table: str, columns: list[str]) -> str:
        """Both sides are slice-keyed by report_date (one slice per run); pin
        the newest slice so the join cannot fan out across dates."""
        if "report_date" in columns:
            return (f"(SELECT * FROM {table} WHERE report_date = "
                    f"(SELECT max(report_date) FROM {table}))")
        return table

    legacy_src = latest_slice(legacy, legacy_columns)
    summary_src = latest_slice(summary, summary_columns)
    parity_query = (
        f"SELECT l.currency, l.{legacy_rt} AS record_type, "
        f"{legacy_count} AS legacy_records, "
        f"{legacy_amount} AS legacy_amount, "
        f"{lakehouse_amount} AS lakehouse_amount, "
        f"{lakehouse_amount} - {legacy_amount} AS delta "
        f"FROM {legacy_src} l "
        f"LEFT JOIN {summary_src} g ON g.currency = l.currency AND g.{summary_rt} = l.{legacy_rt} "
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
    counters = dbx.sql_ok(datasets[0][1])
    for label, value in zip(counters.columns, counters.rows[0]):
        if label.lower() != "quarantined" and not int(value or 0):
            raise SystemExit(
                f"converted estate counter {label} is zero; refusing to publish an empty page")
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
