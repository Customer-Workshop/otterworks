#!/usr/bin/env python3
"""Convert etl/legacy-extra/jobs/finance_excel_report.pl into a gold rollup.

The legacy Perl report accumulated float totals keyed `currency|rectype` from
whatever .psv files it could open (`|| next` skipped the rest silently), wrote
CSV, copied it to .xls, and piped to a sendmail that no longer exists. This
replacement aggregates from the typed silver column in exact integer cents,
carries the legacy-vs-lakehouse delta in the gold table itself, shows the
excluded-quarantine count next to the totals, publishes an AI/BI dashboard
page, and records every delivery attempt (including failures) in
ow_tp.ops.report_runs_<ns>.

Everything is namespace-scoped (`--ns`) and ow_tp-prefixed; this tool only
creates objects suffixed with its own namespace.

  provision   create the unit's tables in the namespace
  baseline    load the captured legacy report CSV as the recon baseline
  land        upload the archived CUSTBILL drops into the landing volume
  load        bronze -> typed silver + quarantine (fails loudly on a short load)
  report      build gold rollup + delta, record the run and delivery attempt
  probe       exercise the legacy failure modes (unknown rectype, bad amount,
              missing file) against a separate probe batch
  dashboard   upsert the finance rollup page on ow_tp_billing_migration_<ns>
  job         create/refresh the (PAUSED) ow_tp_report_<ns> Databricks job
  recon       recompute the contract checks from the target, emit the report
  status      summarise what exists in the namespace
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import smtplib
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import Databricks, DbxError, require_ident, require_ns

REPO = Path(__file__).resolve().parents[2]
NOTEBOOK_DIR = "/Shared/ow_tp"
RT_LABEL = ("CASE WHEN record_type = '01' THEN 'INVOICE' "
            "WHEN record_type = '02' THEN 'CREDIT' "
            "ELSE concat('UNKNOWN(', record_type, ')') END")


@dataclass(frozen=True)
class Names:
    catalog: str = "ow_tp"
    ns: str = "demo"

    @property
    def landing(self) -> str:
        return f"/Volumes/{self.catalog}/bronze/landing/{self.ns}"

    @property
    def drops_dir(self) -> str:
        return f"{self.landing}/report/clean"

    @property
    def probe_dir(self) -> str:
        return f"{self.landing}/report/probe"

    @property
    def bronze(self) -> str:
        return f"{self.catalog}.bronze.custbill_report_raw_{self.ns}"

    @property
    def silver(self) -> str:
        return f"{self.catalog}.silver.custbill_report_{self.ns}"

    @property
    def quarantine(self) -> str:
        return f"{self.catalog}.silver.custbill_report_quarantine_{self.ns}"

    @property
    def gold(self) -> str:
        return f"{self.catalog}.gold.billing_summary_{self.ns}"

    @property
    def delta(self) -> str:
        return f"{self.catalog}.gold.billing_summary_delta_{self.ns}"

    @property
    def baseline(self) -> str:
        return f"{self.catalog}.ops.report_legacy_baseline_{self.ns}"

    @property
    def recipients(self) -> str:
        return f"{self.catalog}.ops.report_recipients_{self.ns}"

    @property
    def runs(self) -> str:
        return f"{self.catalog}.ops.report_runs_{self.ns}"


def names(args) -> Names:
    return Names(catalog=require_ident(args.catalog, "catalog"), ns=require_ns(args.ns))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


# --- SQL ---------------------------------------------------------------------
def provision_sql(n: Names) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS {n.bronze} (
              source_file STRING COMMENT 'CUSTBILL drop file name as landed',
              batch STRING COMMENT 'clean = seeded drops, probe = failure-mode probe batch',
              record_kind STRING COMMENT 'HDR, TRL or BODY',
              raw_line STRING COMMENT 'Untouched fixed-width record',
              ingested_at TIMESTAMP)
            USING DELTA
            COMMENT 'Bronze: byte-preserved CUSTBILL drops feeding the finance report unit'""",
        f"""CREATE TABLE IF NOT EXISTS {n.silver} (
              cust_id STRING, cust_name STRING, bill_date DATE,
              amount_cents BIGINT COMMENT 'PIC 9(10)V99 implied decimal held as exact cents',
              currency STRING, record_type STRING COMMENT '01=invoice 02=credit, anything else is an explicit unknown group',
              source_file STRING, batch STRING)
            USING DELTA
            COMMENT 'Silver: typed billing records for the finance report unit (quarantined rows excluded); the parse unit owns the production silver contract'""",
        f"""CREATE TABLE IF NOT EXISTS {n.quarantine} (
              source_file STRING, batch STRING, cust_id STRING, raw_line STRING,
              reason STRING COMMENT 'nonnumeric_amount | invalid_calendar_date | null_grouping_key | trailer_count_mismatch',
              detected_at TIMESTAMP)
            USING DELTA
            COMMENT 'Silver: records the legacy report would have coerced into its totals'""",
        f"""CREATE TABLE IF NOT EXISTS {n.gold} (
              period_start DATE COMMENT 'Report dated by the data period, not execution wall-clock',
              period_end DATE,
              currency STRING, record_type STRING,
              record_type_label STRING COMMENT '01=INVOICE 02=CREDIT else UNKNOWN(rt)',
              record_count BIGINT,
              total_amount_cents BIGINT COMMENT 'Exact integer cents summed from typed silver',
              legacy_record_count BIGINT COMMENT 'From the captured legacy finance_billing CSV',
              legacy_total_amount_cents BIGINT,
              delta_cents BIGINT COMMENT 'lakehouse minus legacy, in cents',
              delta_count BIGINT,
              excluded_quarantine_count BIGINT COMMENT 'Quarantined records excluded from every group in this rollup',
              silver_version BIGINT COMMENT 'Delta version of silver this rollup aggregated')
            USING DELTA
            COMMENT 'Gold: finance billing rollup, the finance_excel_report.pl replacement'""",
        f"""CREATE TABLE IF NOT EXISTS {n.delta} (
              currency STRING, record_type_label STRING,
              legacy_record_count BIGINT, lakehouse_record_count BIGINT, delta_count BIGINT,
              legacy_total_amount_cents BIGINT, lakehouse_total_amount_cents BIGINT, delta_cents BIGINT,
              status STRING COMMENT 'match | divergent | legacy_only | lakehouse_only')
            USING DELTA
            COMMENT 'Gold: legacy-vs-lakehouse comparison, one row per report group'""",
        f"""CREATE TABLE IF NOT EXISTS {n.baseline} (
              currency STRING, record_type_label STRING,
              record_count BIGINT, total_amount_cents BIGINT)
            USING DELTA
            COMMENT 'Captured legacy finance_billing report rows (integer cents), the recon baseline'""",
        f"""CREATE TABLE IF NOT EXISTS {n.recipients} (
              recipient STRING, active BOOLEAN, note STRING)
            USING DELTA
            COMMENT 'Managed distribution list replacing the hardcoded $MAILTO branches'""",
        f"""CREATE TABLE IF NOT EXISTS {n.runs} (
              run_id STRING, run_at TIMESTAMP, batch STRING,
              period_start DATE, period_end DATE,
              status STRING COMMENT 'ok | failed',
              detail STRING,
              groups INT, record_count BIGINT, total_amount_cents BIGINT,
              quarantine_excluded BIGINT,
              expected_files INT, files_loaded INT,
              delivery_recipients STRING,
              delivery_status STRING COMMENT 'sent | failed | skipped',
              delivery_detail STRING)
            USING DELTA
            COMMENT 'Every report run and delivery attempt, including failures the legacy chain swallowed'""",
    ]


def load_bronze_sql(n: Names, path: str, batch: str) -> str:
    return f"""
    INSERT INTO {n.bronze}
    SELECT
      regexp_extract(_metadata.file_path, '([^/]+)$', 1) AS source_file,
      '{batch}' AS batch,
      CASE WHEN startswith(value, 'HDR') THEN 'HDR'
           WHEN startswith(value, 'TRL') THEN 'TRL'
           ELSE 'BODY' END AS record_kind,
      value AS raw_line,
      current_timestamp() AS ingested_at
    FROM read_files('{path}', format => 'text', recursiveFileLookup => true)
    WHERE length(trim(value)) > 0"""


def _body_projection(n: Names, batch: str) -> str:
    return f"""
      SELECT
        trim(substr(raw_line, 1, 10)) AS cust_id,
        trim(substr(raw_line, 11, 30)) AS cust_name,
        substr(raw_line, 41, 8) AS bill_date_raw,
        substr(raw_line, 49, 12) AS amount_raw,
        trim(substr(raw_line, 61, 3)) AS currency,
        substr(raw_line, 64, 2) AS record_type,
        source_file, batch, raw_line
      FROM {n.bronze}
      WHERE record_kind = 'BODY' AND batch = '{batch}'"""


def build_silver_sql(n: Names, batch: str) -> str:
    return f"""
    INSERT INTO {n.silver}
    REPLACE WHERE batch = '{batch}'
    SELECT cust_id, cust_name, to_date(bill_date_raw, 'yyyyMMdd') AS bill_date,
           CAST(amount_raw AS BIGINT) AS amount_cents, currency, record_type,
           source_file, batch
    FROM ({_body_projection(n, batch)}) parsed
    WHERE amount_raw RLIKE '^[0-9]{{12}}$'
      AND try_to_date(bill_date_raw, 'yyyyMMdd') IS NOT NULL
      AND length(trim(currency)) > 0
      AND length(trim(record_type)) > 0"""


def build_quarantine_sql(n: Names, batch: str) -> str:
    return f"""
    INSERT INTO {n.quarantine}
    REPLACE WHERE batch = '{batch}'
    WITH parsed AS ({_body_projection(n, batch)}),
    row_defects AS (
      SELECT source_file, batch, cust_id, raw_line,
             CASE WHEN NOT amount_raw RLIKE '^[0-9]{{12}}$' THEN 'nonnumeric_amount'
                  WHEN try_to_date(bill_date_raw, 'yyyyMMdd') IS NULL THEN 'invalid_calendar_date'
                  ELSE 'null_grouping_key' END AS reason
      FROM parsed
      WHERE NOT amount_raw RLIKE '^[0-9]{{12}}$'
         OR try_to_date(bill_date_raw, 'yyyyMMdd') IS NULL
         OR length(trim(currency)) = 0
         OR length(trim(record_type)) = 0
    ),
    trailer_defects AS (
      SELECT b.source_file, b.batch, '' AS cust_id,
             concat('trailer=', CAST(b.trailer_count AS STRING), ' body=', CAST(b.body_count AS STRING)) AS raw_line,
             'trailer_count_mismatch' AS reason
      FROM (
        SELECT source_file, batch,
               max(CASE WHEN record_kind = 'TRL' THEN CAST(substr(raw_line, 4, 10) AS BIGINT) END) AS trailer_count,
               count_if(record_kind = 'BODY') AS body_count
        FROM {n.bronze} WHERE batch = '{batch}' GROUP BY source_file, batch
      ) b
      WHERE b.trailer_count IS NOT NULL AND b.trailer_count <> b.body_count
    )
    SELECT source_file, batch, cust_id, raw_line, reason, current_timestamp()
    FROM (SELECT * FROM row_defects UNION ALL SELECT * FROM trailer_defects)"""


def rollup_sql(n: Names) -> str:
    """The report of record: exact-cents rollup over clean silver, with the
    legacy baseline and its delta carried in the table itself. The silver
    version is resolved when the statement runs, so scheduled runs stamp the
    version they actually aggregated. The excluded count covers records
    withheld from the totals; file-level trailer mismatch notices are not
    records and are not counted."""
    return f"""
    INSERT OVERWRITE {n.gold}
    WITH clean AS (SELECT * FROM {n.silver} WHERE batch = 'clean'),
    quarantined AS (
      SELECT count(*) AS excluded FROM {n.quarantine}
      WHERE batch = 'clean' AND reason != 'trailer_count_mismatch'
    ),
    groups AS (
      SELECT currency, record_type, {RT_LABEL} AS record_type_label,
             count(*) AS record_count, sum(amount_cents) AS total_amount_cents
      FROM clean GROUP BY currency, record_type
    ),
    period AS (SELECT min(bill_date) AS period_start, max(bill_date) AS period_end FROM clean)
    SELECT p.period_start, p.period_end,
           g.currency, g.record_type, g.record_type_label,
           g.record_count, g.total_amount_cents,
           coalesce(b.record_count, 0) AS legacy_record_count,
           coalesce(b.total_amount_cents, 0) AS legacy_total_amount_cents,
           g.total_amount_cents - coalesce(b.total_amount_cents, 0) AS delta_cents,
           g.record_count - coalesce(b.record_count, 0) AS delta_count,
           q.excluded AS excluded_quarantine_count,
           (SELECT max(version) FROM (DESCRIBE HISTORY {n.silver})) AS silver_version
    FROM groups g
    CROSS JOIN period p CROSS JOIN quarantined q
    LEFT JOIN {n.baseline} b
      ON b.currency = g.currency AND b.record_type_label = g.record_type_label"""


def delta_sql(n: Names) -> str:
    return f"""
    INSERT OVERWRITE {n.delta}
    SELECT coalesce(b.currency, g.currency) AS currency,
           coalesce(b.record_type_label, g.record_type_label) AS record_type_label,
           coalesce(b.record_count, 0) AS legacy_record_count,
           coalesce(g.record_count, 0) AS lakehouse_record_count,
           coalesce(g.record_count, 0) - coalesce(b.record_count, 0) AS delta_count,
           coalesce(b.total_amount_cents, 0) AS legacy_total_amount_cents,
           coalesce(g.total_amount_cents, 0) AS lakehouse_total_amount_cents,
           coalesce(g.total_amount_cents, 0) - coalesce(b.total_amount_cents, 0) AS delta_cents,
           CASE WHEN b.currency IS NULL THEN 'lakehouse_only'
                WHEN g.currency IS NULL THEN 'legacy_only'
                WHEN b.record_count = g.record_count
                 AND b.total_amount_cents = g.total_amount_cents THEN 'match'
                ELSE 'divergent' END AS status
    FROM {n.baseline} b
    FULL OUTER JOIN (SELECT * FROM {n.gold}) g
      ON b.currency = g.currency AND b.record_type_label = g.record_type_label"""


def gold_groups_sql(n: Names) -> str:
    return (f"SELECT currency, record_type_label, record_count, total_amount_cents, "
            f"delta_cents, delta_count, excluded_quarantine_count "
            f"FROM {n.gold} ORDER BY currency, record_type_label")


# --- helpers ------------------------------------------------------------------
def silver_version(dbx: Databricks, n: Names) -> int:
    return int(dbx.sql_ok(f"DESCRIBE HISTORY {n.silver} LIMIT 1").rows[0][0])


def parse_legacy_csv(path: Path) -> list[tuple[str, str, int, int]]:
    """Exact-cents parse of the captured legacy report: the amount text is split
    on the decimal point, never floated."""
    rows = []
    lines = path.read_text().splitlines()
    if lines[0] != "Currency,RecordType,RecordCount,TotalAmount":
        raise SystemExit(f"unexpected legacy report header: {lines[0]!r}")
    for line in lines[1:]:
        currency, label, count, amount = line.split(",")
        whole, frac = amount.split(".")
        if len(frac) != 2:
            raise SystemExit(f"legacy amount not 2dp: {amount!r}")
        rows.append((currency, label, int(count), int(whole) * 100 + int(frac)))
    return rows


def find_dashboard(dbx: Databricks, name: str) -> dict | None:
    for dashboard in dbx.list_all("/api/2.0/lakeview/dashboards", "dashboards"):
        if dashboard.get("display_name") == name and dashboard.get("lifecycle_state") == "ACTIVE":
            return dashboard
    return None


def record_run(dbx: Databricks, n: Names, run: dict) -> None:
    cols = ("run_id", "run_at", "batch", "period_start", "period_end", "status", "detail",
            "groups", "record_count", "total_amount_cents", "quarantine_excluded",
            "expected_files", "files_loaded", "delivery_recipients", "delivery_status",
            "delivery_detail")
    values = []
    for col in cols:
        value = run.get(col)
        if col == "run_at":
            values.append("current_timestamp()")
        elif value is None:
            values.append("NULL")
        elif isinstance(value, (int, float)):
            values.append(str(int(value)))
        elif col in ("period_start", "period_end"):
            values.append(f"DATE'{esc(str(value))}'")
        else:
            values.append(f"'{esc(str(value))}'")
    dbx.sql_ok(f"INSERT INTO {n.runs} ({', '.join(cols)}) VALUES ({', '.join(values)})")


def attempt_delivery(dbx: Databricks, n: Names, subject: str) -> tuple[str, str, str]:
    """Deliver to the managed recipient list, or record exactly why not.
    There is no SMTP transport in this environment, so the expected honest
    outcome here is a recorded failure — never the legacy silent no-op."""
    rows = dbx.sql_ok(f"SELECT recipient FROM {n.recipients} WHERE active ORDER BY recipient").rows
    recipients = [r[0] for r in rows]
    if not recipients:
        return "", "skipped", "no active recipients configured"
    try:
        with smtplib.SMTP("localhost", 25, timeout=10) as smtp:
            smtp.sendmail("ow-tp-reports@otterworks.dev", recipients,
                          f"Subject: {subject}\n\nSee dashboard.".encode())
        return ",".join(recipients), "sent", "delivered via localhost:25"
    except OSError as exc:
        return ",".join(recipients), "failed", f"smtp localhost:25 unavailable: {exc}"


# --- commands -----------------------------------------------------------------
def cmd_provision(dbx: Databricks, args) -> int:
    n = names(args)
    for statement in provision_sql(n):
        dbx.sql_ok(statement)
    if int(dbx.sql_ok(f"SELECT count(*) FROM {n.recipients}").scalar()) == 0:
        dbx.sql_ok(f"""
            INSERT INTO {n.recipients} VALUES
            ('finance-reports@otterworks.dev', true, 'finance team distribution list'),
            ('jake@otterworks.dev', false, 'left 2020; retained inactive for audit, never mailed')""")
        print("seeded managed recipient list")
    else:
        print("recipient list already managed; leaving it untouched")
    print(f"provisioned finance report unit tables for ns={n.ns}")
    return 0


def cmd_baseline(dbx: Databricks, args) -> int:
    n = names(args)
    reports = sorted(Path(args.legacy_root).glob("reports/finance_billing_*.csv"))
    if not reports:
        raise SystemExit(f"no legacy report under {args.legacy_root}/reports; run the legacy chain first")
    rows = parse_legacy_csv(reports[-1])
    values = ",\n".join(f"('{esc(c)}', '{esc(l)}', {cnt}, {cents})" for c, l, cnt, cents in rows)
    dbx.sql_ok(f"INSERT OVERWRITE {n.baseline} VALUES\n{values}")
    print(f"loaded {len(rows)} legacy baseline rows from {reports[-1]}")
    return 0


def cmd_land(dbx: Databricks, args) -> int:
    n = names(args)
    archive = Path(args.legacy_root) / "archive"
    drops: dict[str, Path] = {}
    for path in sorted(archive.glob("CUSTBILL_*.dat.*")):
        drops[path.name.rsplit(".dat.", 1)[0] + ".dat"] = path
    if not drops:
        raise SystemExit(f"no archived CUSTBILL drops under {archive}")
    for name, path in drops.items():
        dbx.put_file(f"{n.drops_dir}/{name}", path.read_bytes())
        print(f"landed {name} ({path.stat().st_size} bytes)")
    return 0


def cmd_load(dbx: Databricks, args) -> int:
    n = names(args)
    landed = [e for e in dbx.list_dir(n.drops_dir) if not e.get("is_directory")]
    expected = args.expect_files if args.expect_files else len(landed)
    if len(landed) != expected:
        detail = (f"expected {expected} drop files, found {len(landed)}: "
                  f"a short load ships a short report, so the run fails instead")
        record_run(dbx, n, {
            "run_id": uuid.uuid4().hex[:12], "batch": "clean", "status": "failed",
            "detail": detail, "expected_files": expected, "files_loaded": len(landed),
            "delivery_status": "skipped", "delivery_detail": "run failed before rollup",
        })
        print(f"LOAD FAILED (recorded): {detail}", file=sys.stderr)
        return 1
    dbx.sql_ok(f"DELETE FROM {n.bronze} WHERE batch = 'clean'")
    dbx.sql_ok(load_bronze_sql(n, n.drops_dir, "clean"))
    dbx.sql_ok(build_silver_sql(n, "clean"))
    dbx.sql_ok(build_quarantine_sql(n, "clean"))
    summary = dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.bronze} WHERE batch='clean') AS bronze_rows, "
        f"(SELECT count(DISTINCT source_file) FROM {n.bronze} WHERE batch='clean') AS files, "
        f"(SELECT count(*) FROM {n.silver} WHERE batch='clean') AS silver_rows, "
        f"(SELECT count(*) FROM {n.quarantine} WHERE batch='clean') AS quarantined"
    ).dicts()[0]
    print(json.dumps(summary, indent=2))
    return 0


def cmd_report(dbx: Databricks, args) -> int:
    n = names(args)
    dbx.sql_ok(rollup_sql(n))
    dbx.sql_ok(delta_sql(n))
    raw_version = dbx.sql_ok(f"SELECT max(silver_version) FROM {n.gold}").scalar()
    if raw_version is None:
        # Contract empty_input_semantics: a period with no silver records writes
        # a recorded run with zero groups and a declared zero total, so an empty
        # period is distinguishable from a failed run.
        version = silver_version(dbx, n)
        record_run(dbx, n, {
            "run_id": uuid.uuid4().hex[:12], "batch": "clean", "status": "ok",
            "detail": f"empty period: no clean silver records to aggregate (silver v{version})",
            "groups": 0, "record_count": 0, "total_amount_cents": 0,
            "quarantine_excluded": 0,
            "delivery_status": "skipped", "delivery_detail": "nothing to report for an empty period",
        })
        print(json.dumps({"groups": 0, "records": 0, "cents": 0}, indent=2))
        print("empty period recorded: zero groups, zero total")
        return 0
    version = int(raw_version)
    stats = dbx.sql_ok(
        f"SELECT count(*) AS groups, coalesce(sum(record_count), 0) AS records, "
        f"coalesce(sum(total_amount_cents), 0) AS cents, "
        f"coalesce(max(excluded_quarantine_count), 0) AS quarantined, "
        f"min(period_start) AS period_start, max(period_end) AS period_end "
        f"FROM {n.gold}"
    ).dicts()[0]
    recipients, delivery_status, delivery_detail = attempt_delivery(
        dbx, n, f"[AUTO] Finance billing rollup {stats['period_start']}..{stats['period_end']} ns={n.ns}")
    record_run(dbx, n, {
        "run_id": uuid.uuid4().hex[:12], "batch": "clean",
        "period_start": stats["period_start"], "period_end": stats["period_end"],
        "status": "ok", "detail": f"rollup over silver v{version}",
        "groups": stats["groups"], "record_count": stats["records"],
        "total_amount_cents": stats["cents"], "quarantine_excluded": stats["quarantined"],
        "delivery_recipients": recipients, "delivery_status": delivery_status,
        "delivery_detail": delivery_detail,
    })
    print(json.dumps(stats, indent=2))
    print(f"delivery: {delivery_status} — {delivery_detail} (to: {recipients or 'nobody'})")
    for row in dbx.sql_ok(gold_groups_sql(n)).rows:
        print("  " + " | ".join(str(v) for v in row))
    return 0 if delivery_status != "failed" or args.allow_delivery_failure else 1


def cmd_probe(dbx: Databricks, args) -> int:
    """Exercise the three legacy failure modes the contract requires this unit
    to detect, in an isolated probe batch that never reaches the gold rollup."""
    n = names(args)
    body = [
        "HDR CUSTBILL EXTRACT NS=PROBE      FILE=001" + " " * 20,
        # RPT-A1: record type outside {01,02}
        "C000000001" + f"{'PROBE UNKNOWN RT':<30}" + "20240115" + "000000010000" + "USD" + "09",
        # RPT-A2: non-numeric amount the legacy awk coerced to 0.00
        "C000000002" + f"{'PROBE BAD AMOUNT':<30}" + "20240116" + "0000000ABCDE" + "USD" + "01",
        # control row: fully valid
        "C000000003" + f"{'PROBE CONTROL':<30}" + "20240117" + "000000020000" + "EUR" + "02",
        "TRL" + f"{3:010d}" + " " * 52,
    ]
    dbx.put_file(f"{n.probe_dir}/CUSTBILL_PROBE_001.dat", ("\n".join(body) + "\n").encode())
    dbx.sql_ok(f"DELETE FROM {n.bronze} WHERE batch = 'probe'")
    dbx.sql_ok(load_bronze_sql(n, n.probe_dir, "probe"))
    dbx.sql_ok(build_silver_sql(n, "probe"))
    dbx.sql_ok(build_quarantine_sql(n, "probe"))
    results = {
        "unknown_record_type_group": dbx.sql_ok(
            f"SELECT {RT_LABEL} AS label, count(*), sum(amount_cents) FROM {n.silver} "
            f"WHERE batch='probe' AND record_type NOT IN ('01','02') GROUP BY record_type").rows,
        "nonnumeric_amount_quarantined": dbx.sql_ok(
            f"SELECT cust_id, reason FROM {n.quarantine} "
            f"WHERE batch='probe' AND reason='nonnumeric_amount'").rows,
        "gold_records_minus_clean_silver": int(dbx.sql_ok(
            f"SELECT coalesce((SELECT sum(record_count) FROM {n.gold}), 0) - "
            f"(SELECT count(*) FROM {n.silver} WHERE batch='clean')").scalar()),
    }
    print(json.dumps(results, indent=2))
    return 0


def cmd_dashboard(dbx: Databricks, args) -> int:
    """Upsert the finance rollup page on the namespace's migration dashboard,
    preserving any pages other commands built."""
    n = names(args)
    name = f"ow_tp_billing_migration_{n.ns}"

    def widget(wname, dataset, fields, spec, pos, aggregated=None):
        field_specs = [{"name": f, "expression": f"`{f}`"} for f in fields]
        if aggregated:
            field_specs += [{"name": alias, "expression": expr} for alias, expr in aggregated.items()]
        return {"widget": {"name": wname, "queries": [{
            "name": f"{wname}_q",
            "query": {"datasetName": dataset, "fields": field_specs, "disaggregated": not aggregated},
        }], "spec": spec}, "position": pos}

    def counter(wname, dataset, field, title, pos):
        return widget(wname, dataset, [field], {
            "version": 2, "widgetType": "counter",
            "encodings": {"value": {"fieldName": field, "displayName": title}},
            "frame": {"title": title, "showTitle": True},
        }, pos)

    def table(wname, dataset, columns, title, pos):
        return widget(wname, dataset, [f for f, _ in columns], {
            "version": 3, "widgetType": "table",
            "encodings": {"columns": [{"fieldName": f, "displayName": d} for f, d in columns]},
            "frame": {"title": title, "showTitle": True},
        }, pos)

    datasets = [
        ("rpt_summary", (
            f"SELECT (SELECT count(*) FROM {n.gold}) AS groups, "
            f"(SELECT coalesce(sum(record_count), 0) FROM {n.gold}) AS records, "
            f"(SELECT coalesce(sum(total_amount_cents), 0) / 100.0 FROM {n.gold}) AS total_billed, "
            f"(SELECT coalesce(max(excluded_quarantine_count), 0) FROM {n.gold}) AS quarantine_excluded, "
            f"(SELECT count_if(status != 'match') FROM {n.delta}) AS groups_divergent")),
        ("rpt_rollup", (
            f"SELECT currency, record_type_label, record_count, "
            f"total_amount_cents / 100.0 AS total_amount, "
            f"legacy_total_amount_cents / 100.0 AS legacy_amount, "
            f"delta_cents / 100.0 AS delta, excluded_quarantine_count "
            f"FROM {n.gold} ORDER BY currency, record_type_label")),
        ("rpt_delta", (
            f"SELECT currency, record_type_label, legacy_record_count, lakehouse_record_count, "
            f"delta_count, legacy_total_amount_cents / 100.0 AS legacy_amount, "
            f"lakehouse_total_amount_cents / 100.0 AS lakehouse_amount, "
            f"delta_cents / 100.0 AS delta, status FROM {n.delta} ORDER BY currency, record_type_label")),
        ("rpt_runs", (
            f"SELECT run_at, status, detail, groups, record_count, "
            f"total_amount_cents / 100.0 AS total_amount, quarantine_excluded, "
            f"delivery_recipients, delivery_status, delivery_detail "
            f"FROM {n.runs} ORDER BY run_at DESC LIMIT 20")),
    ]
    layout = [
        counter("rpt_groups", "rpt_summary", "groups", "Report groups",
                {"x": 0, "y": 0, "width": 2, "height": 3}),
        counter("rpt_records", "rpt_summary", "records", "Billing records",
                {"x": 2, "y": 0, "width": 2, "height": 3}),
        counter("rpt_total", "rpt_summary", "total_billed", "Total billed",
                {"x": 4, "y": 0, "width": 3, "height": 3}),
        counter("rpt_quarantine", "rpt_summary", "quarantine_excluded", "Quarantined records excluded",
                {"x": 7, "y": 0, "width": 3, "height": 3}),
        counter("rpt_divergent", "rpt_summary", "groups_divergent", "Groups off from legacy",
                {"x": 10, "y": 0, "width": 2, "height": 3}),
        table("rpt_rollup_table", "rpt_rollup", [
            ("currency", "Currency"), ("record_type_label", "Record type"),
            ("record_count", "Records"), ("total_amount", "Total"),
            ("legacy_amount", "Legacy report said"), ("delta", "Difference"),
            ("excluded_quarantine_count", "Quarantined (excluded)"),
        ], "Finance billing rollup — the .xls that was never an .xls", {"x": 0, "y": 3, "width": 12, "height": 6}),
        table("rpt_delta_table", "rpt_delta", [
            ("currency", "Currency"), ("record_type_label", "Record type"),
            ("legacy_record_count", "Legacy records"), ("lakehouse_record_count", "Lakehouse records"),
            ("legacy_amount", "Legacy total"), ("lakehouse_amount", "Lakehouse total"),
            ("delta", "Difference"), ("status", "Status"),
        ], "Legacy vs lakehouse, to the cent", {"x": 0, "y": 9, "width": 6, "height": 6}),
        table("rpt_runs_table", "rpt_runs", [
            ("run_at", "Run at"), ("status", "Run"), ("record_count", "Records"),
            ("total_amount", "Total"), ("quarantine_excluded", "Quarantined excluded"),
            ("delivery_recipients", "Recipients"), ("delivery_status", "Delivery"),
            ("delivery_detail", "Delivery detail"),
        ], "Report runs and delivery attempts (failures recorded, not swallowed)",
              {"x": 6, "y": 9, "width": 6, "height": 6}),
    ]
    page = {"name": "finance_report", "displayName": "Finance billing rollup", "layout": layout}

    existing = find_dashboard(dbx, name)
    if existing:
        current = dbx.ok("GET", f"/api/2.0/lakeview/dashboards/{existing['dashboard_id']}", None)
        spec = json.loads(current.get("serialized_dashboard") or '{"datasets": [], "pages": []}')
        spec["datasets"] = [d for d in spec.get("datasets", []) if not d["name"].startswith("rpt_")]
        spec["pages"] = [p for p in spec.get("pages", []) if p.get("name") != "finance_report"]
    else:
        current = None
        spec = {"datasets": [], "pages": []}
    spec["datasets"] += [{"name": key, "displayName": key, "queryLines": [query]} for key, query in datasets]
    spec["pages"].append(page)
    body = {
        "display_name": name,
        "warehouse_id": dbx.warehouse_id,
        "serialized_dashboard": json.dumps(spec),
    }
    if existing:
        body["etag"] = current.get("etag", "")
        result = dbx.ok("PATCH", f"/api/2.0/lakeview/dashboards/{existing['dashboard_id']}", body)
    else:
        result = dbx.ok("POST", "/api/2.0/lakeview/dashboards", body)
    dashboard_id = result["dashboard_id"]
    dbx.ok("POST", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
           {"embed_credentials": True, "warehouse_id": dbx.warehouse_id})
    print(f"dashboard (finance_report page): {dbx.host}/dashboardsv3/{dashboard_id}/published")
    return 0


def cmd_job(dbx: Databricks, args) -> int:
    """The converted job as a Databricks job: rebuild silver, quarantine, gold
    and the delta from bronze. Schedule stays PAUSED — nothing in the shared
    workspace runs unattended."""
    n = names(args)
    statements = ";\n\n".join([
        build_silver_sql(n, "clean"),
        build_quarantine_sql(n, "clean"),
        rollup_sql(n),
        delta_sql(n),
    ])
    sql_path = f"{NOTEBOOK_DIR}/finance_report_{n.ns}.sql"
    dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": NOTEBOOK_DIR})
    dbx.ok("POST", "/api/2.0/workspace/import", {
        "path": sql_path, "format": "AUTO", "overwrite": True,
        "content": base64.b64encode(statements.encode()).decode(),
    })
    settings = {
        "name": f"ow_tp_report_{n.ns}",
        "tags": {"project": "otterworks-tp", "demo": "billing-history", "namespace": n.ns},
        "max_concurrent_runs": 1,
        "tasks": [{
            "task_key": "finance_rollup",
            "sql_task": {
                "warehouse_id": dbx.warehouse_id,
                "file": {"path": sql_path, "source": "WORKSPACE"},
            },
        }],
        "schedule": {
            "quartz_cron_expression": "0 30 6 * * ?",
            "timezone_id": "UTC",
            "pause_status": "PAUSED",
        },
        "queue": {"enabled": True},
    }
    job_id = dbx.upsert_job(settings)
    print(f"report job {job_id} (schedule PAUSED): {dbx.host}/jobs/{job_id}")
    return 0


def cmd_status(dbx: Databricks, args) -> int:
    n = names(args)
    result = dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.bronze}) AS bronze_rows, "
        f"(SELECT count(*) FROM {n.silver} WHERE batch='clean') AS silver_clean, "
        f"(SELECT count(*) FROM {n.quarantine} WHERE batch='clean') AS quarantine_clean, "
        f"(SELECT count(*) FROM {n.gold}) AS gold_groups, "
        f"(SELECT coalesce(sum(total_amount_cents), 0) FROM {n.gold}) AS gold_cents, "
        f"(SELECT count(*) FROM {n.runs}) AS report_runs"
    )
    print(json.dumps(result.dicts()[0], indent=2))
    job = dbx.find_job(f"ow_tp_report_{n.ns}")
    if job:
        detail = dbx.ok("GET", f"/api/2.1/jobs/get?job_id={int(job['job_id'])}")
        schedule = detail.get("settings", {}).get("schedule")
        state = schedule.get("pause_status", "UNKNOWN") if schedule else "NO SCHEDULE"
        print(f"report job: {dbx.host}/jobs/{job['job_id']} schedule={state}")
    else:
        print("report job: absent")
    return 0


def cmd_recon(dbx: Databricks, args) -> int:
    n = names(args)
    reports = sorted(Path(args.legacy_root).glob("reports/finance_billing_*.csv"))
    if not reports:
        raise SystemExit("no captured legacy report; run the legacy chain first")
    legacy = {(c, l): (cnt, cents) for c, l, cnt, cents in parse_legacy_csv(reports[-1])}

    def gold_rows() -> list[list]:
        return dbx.sql_ok(gold_groups_sql(n)).rows

    checks: list[dict] = []

    def check(check_id: str, expected, actual, source: str) -> None:
        checks.append({
            "id": check_id, "expected": expected, "actual": actual,
            "source_of_truth": source,
            "result": "pass" if expected == actual else "fail",
        })

    legacy_src = f"captured legacy run {reports[-1].name} (make legacy-etl-run JOB=run_all)"
    rows = gold_rows()
    actual_groups = {(r[0], r[1]): (int(r[2]), int(r[3])) for r in rows}
    check("RPT-01",
          {f"{c}/{l}": list(v) for (c, l), v in sorted(legacy.items())},
          {f"{c}/{l}": list(v) for (c, l), v in sorted(actual_groups.items())},
          legacy_src + ", compared in integer cents")

    types = {r["col_name"]: r["data_type"] for r in dbx.sql_ok(f"DESCRIBE {n.silver}").dicts()}
    gold_types = {r["col_name"]: r["data_type"] for r in dbx.sql_ok(f"DESCRIBE {n.gold}").dicts()}
    check("RPT-02", {"silver.amount_cents": "bigint", "gold.total_amount_cents": "bigint"},
          {"silver.amount_cents": types.get("amount_cents"),
           "gold.total_amount_cents": gold_types.get("total_amount_cents")},
          "table schemas: integer-cents end to end, no float accumulation")

    delta = dbx.sql_ok(
        f"SELECT count(*) AS groups, count_if(delta_cents = 0 AND delta_count = 0) AS zero, "
        f"count_if(status = 'match') AS matches FROM {n.delta}").dicts()[0]
    in_gold = dbx.sql_ok(
        f"SELECT count_if(delta_cents IS NOT NULL) FROM {n.gold}").scalar()
    check("RPT-03",
          {"delta_column_populated_in_gold": len(rows), "delta_table_groups_matching": len(rows)},
          {"delta_column_populated_in_gold": int(in_gold), "delta_table_groups_matching": int(delta["matches"])},
          "gold.billing_summary delta_cents column and gold.billing_summary_delta status, recomputed from target")

    quarantine_declared = dbx.sql_ok(
        f"SELECT min(excluded_quarantine_count) FROM {n.gold}").scalar()
    quarantine_actual = dbx.sql_ok(
        f"SELECT count(*) FROM {n.quarantine} "
        f"WHERE batch = 'clean' AND reason != 'trailer_count_mismatch'").scalar()
    silver_plus_quarantine = dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.silver} WHERE batch='clean') + "
        f"(SELECT count(*) FROM {n.quarantine} WHERE batch='clean' AND reason != 'trailer_count_mismatch')").scalar()
    body_rows = dbx.sql_ok(
        f"SELECT count(*) FROM {n.bronze} WHERE batch='clean' AND record_kind='BODY'").scalar()
    check("RPT-04",
          {"declared_next_to_totals": int(quarantine_actual), "silver_plus_quarantine": int(body_rows)},
          {"declared_next_to_totals": int(quarantine_declared or 0), "silver_plus_quarantine": int(silver_plus_quarantine)},
          "gold.excluded_quarantine_count vs quarantine table; every bronze body row is in silver or quarantine")

    dashboard = find_dashboard(dbx, f"ow_tp_billing_migration_{n.ns}")
    has_page = False
    if dashboard:
        detail = dbx.ok("GET", f"/api/2.0/lakeview/dashboards/{dashboard['dashboard_id']}", None)
        spec = json.loads(detail.get("serialized_dashboard") or "{}")
        has_page = any(p.get("name") == "finance_report" for p in spec.get("pages", []))
    check("RPT-05", {"dashboard_finance_page_published": True},
          {"dashboard_finance_page_published": bool(dashboard) and has_page},
          "lakeview dashboards API: finance_report page on ow_tp_billing_migration_" + n.ns)

    runs = dbx.sql_ok(
        f"SELECT delivery_status, delivery_recipients, delivery_detail FROM {n.runs} "
        f"WHERE status = 'ok' ORDER BY run_at DESC LIMIT 1").dicts()
    hardcoded = dbx.sql_ok(
        f"SELECT count(*) FROM {n.recipients} WHERE active AND recipient = 'jake@otterworks.dev'").scalar()
    check("RPT-06",
          {"delivery_attempt_recorded": True, "delivery_status": "failed",
           "jake_active_on_distribution": 0},
          {"delivery_attempt_recorded": bool(runs),
           "delivery_status": runs[0]["delivery_status"] if runs else None,
           "jake_active_on_distribution": int(hardcoded)},
          "ops.report_runs delivery columns and ops.report_recipients (no SMTP here, so a recorded failure is the honest outcome)")

    before = gold_rows()
    version = silver_version(dbx, n)
    dbx.sql_ok(build_silver_sql(n, "clean"))
    dbx.sql_ok(build_quarantine_sql(n, "clean"))
    dbx.sql_ok(rollup_sql(n))
    dbx.sql_ok(delta_sql(n))
    after = gold_rows()
    idempotent = before == after
    period = dbx.sql_ok(f"SELECT DISTINCT period_start, period_end FROM {n.gold}").rows
    data_period = dbx.sql_ok(
        f"SELECT CAST(min(bill_date) AS STRING), CAST(max(bill_date) AS STRING) "
        f"FROM {n.silver} WHERE batch = 'clean'").rows
    check("RPT-07",
          {"rerun_identical_groups": True, "period_from_data": data_period},
          {"rerun_identical_groups": idempotent, "period_from_data": period},
          "full silver->gold rebuild rerun compared row-for-row; period columns from min/max bill_date, not wall clock")

    labels = dbx.sql_ok(
        f"SELECT DISTINCT record_type, record_type_label FROM {n.gold} ORDER BY record_type").rows
    probe_unknown = dbx.sql_ok(
        f"SELECT {RT_LABEL} AS label, count(*) AS cnt FROM {n.silver} "
        f"WHERE batch='probe' AND record_type NOT IN ('01','02') GROUP BY record_type").rows
    check("RPT-08",
          {"clean_labels": [["01", "INVOICE"], ["02", "CREDIT"]],
           "probe_unknown_explicit_group": [["UNKNOWN(09)", 1]]},
          {"clean_labels": labels,
           "probe_unknown_explicit_group": [[r[0], int(r[1])] for r in probe_unknown]},
          "gold label column plus probe batch: rt 09 surfaces as its own UNKNOWN(09) group, never folded into a currency total")

    # planted anomaly detections, from the probe batch (A1, A2) and the
    # short-load guard (A3); A4 stays a declared coverage gap
    probe_quarantined = dbx.sql_ok(
        f"SELECT cust_id, reason FROM {n.quarantine} WHERE batch='probe' AND reason='nonnumeric_amount'").rows
    failed_run = dbx.sql_ok(
        f"SELECT count(*) FROM {n.runs} WHERE status = 'failed' AND expected_files > files_loaded").scalar()
    expected_set = [
        ["RPT-A1", "unknown_record_type", "explicit UNKNOWN(09) group"],
        ["RPT-A2", "nonnumeric_amount", "quarantined, not coerced to 0.00"],
        ["RPT-A3", "short_load", "run recorded failed, report not shipped"],
    ]
    actual_set = []
    if probe_unknown:
        actual_set.append(["RPT-A1", "unknown_record_type", "explicit UNKNOWN(09) group"])
    if probe_quarantined:
        actual_set.append(["RPT-A2", "nonnumeric_amount", "quarantined, not coerced to 0.00"])
    if int(failed_run or 0) > 0:
        actual_set.append(["RPT-A3", "short_load", "run recorded failed, report not shipped"])
    expected_keys = {tuple(x) for x in expected_set}
    actual_keys = {tuple(x) for x in actual_set}

    report = {
        "kind": "recon-report",
        "unit": "finance_excel_report",
        "namespace": n.ns,
        "generated_at": now(),
        "run_mode": "live",
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": (f"silver/quarantine/gold/delta rebuilt from bronze (silver was v{version}); "
                         + ("all gold groups byte-identical" if idempotent else "gold groups changed on rerun")),
        },
        "planted_anomaly_detections": {
            "expected_set": expected_set,
            "actual_set": actual_set,
            "missing": sorted(list(k) for k in expected_keys - actual_keys),
            "unexpected": sorted(list(k) for k in actual_keys - expected_keys),
        },
        "unverified_paths": [
            "RPT-A4: successful email delivery — no SMTP transport exists in this environment; "
            "the attempt and its failure are recorded in ow_tp.ops.report_runs_" + n.ns
            + ", but delivery itself is unverified",
        ],
    }
    out = Path(args.out) if args.out else REPO / f"docs/tech-partnerships/recon/finance_excel_report-{n.ns}.recon.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    failed = [c for c in checks if c["result"] == "fail"]
    print(f"wrote {out}")
    print(f"checks: {len(checks)}, failed: {len(failed)}")
    for c in failed:
        print(f"  FAIL {c['id']} expected={c['expected']} actual={c['actual']}")
    if failed or not idempotent or report["planted_anomaly_detections"]["missing"]:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ns", default="demo")
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--legacy-root",
                        default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("provision")
    sub.add_parser("baseline")
    sub.add_parser("land")
    load = sub.add_parser("load")
    load.add_argument("--expect-files", type=int, default=0)
    report = sub.add_parser("report")
    report.add_argument("--allow-delivery-failure", action=argparse.BooleanOptionalAction, default=True,
                        help="pass --no-allow-delivery-failure to make a failed delivery fail the command")
    sub.add_parser("probe")
    sub.add_parser("dashboard")
    sub.add_parser("job")
    sub.add_parser("status")
    recon = sub.add_parser("recon")
    recon.add_argument("--out", default="")
    args = parser.parse_args()
    if args.legacy_root is None:
        args.legacy_root = os.environ.get("OTTERWORKS_LEGACY_ROOT", "/tmp/otterworks-legacy")
    commands = {
        "provision": cmd_provision, "baseline": cmd_baseline, "land": cmd_land,
        "load": cmd_load, "report": cmd_report, "probe": cmd_probe,
        "dashboard": cmd_dashboard, "job": cmd_job, "status": cmd_status,
        "recon": cmd_recon,
    }
    try:
        return commands[args.command](Databricks(), args)
    except DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
