#!/usr/bin/env python3
"""Copy the OLTP reference data the finance gold layer needs out of Lakebase into Delta.

Plans, tenants, subscriptions, credit notes and the legacy rating results live only in
Lakebase Postgres (`ow-tp-billing`, database `ow_tp`, schema `billing`). The Delta side of
pipeline 1 carries invoices, invoice lines and usage events, but `ow_tp.silver`
`subscriptions_hist` is empty, so ARR/MRR has no Delta source at all. This task is the one
place the gold layer reads OLTP, and it reads it read-only:

    SELECT ... FROM billing.<table>

and nothing else. Every write goes to `ow_tp.gold` through the migration SQL warehouse.

The row counts here are tiny (three plans, 69 tenants, 69 subscriptions, five credit notes,
three rating results), so each table is rebuilt with a single `CREATE OR REPLACE TABLE ... AS
SELECT ... FROM VALUES`: the statement is atomic, the rerun is idempotent, and no partial
state is visible to a reader between runs. A table that comes back empty is an error rather
than an empty rebuild, so a Lakebase outage cannot silently zero out ARR.

Types are pinned on the way in, not inferred: money is `DECIMAL`, unit counts are `BIGINT`,
and every timestamp is `TIMESTAMP_NTZ`. Oracle DATE carries a time part and Oracle TIMESTAMP
is zoneless, so the migrated Postgres columns are `timestamp without time zone` and the Delta
columns must be zoneless too — a `TIMESTAMP` (UTC-adjusted) column here would silently shift
every subscription start and usage event by the session timezone.

The Lakebase credential is minted for the run's own principal, lives about an hour, and is
only ever held in memory. It is never printed and never written down.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/gold/python/ingest_lakebase_reference.py --branch mig-p1-w2
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json

import psycopg
from apply_gold_sql import run
from databricks.sdk import WorkspaceClient

PROJECT = "ow-tp-billing"
DATABASE = "ow_tp"
# Mirrors .migration/allowed_targets.json. The repo file is not on the job's filesystem, so
# the guard is restated here: a branch outside this list, `production` above all, is refused
# before a credential is requested.
ALLOWED_BRANCHES = ("mig-p1-w0", "mig-p1-w1", "mig-p1-w2", "mig-p2-w1", "mig-p3-w1")
CATALOG, SCHEMA = "ow_tp", "gold"

# (gold table, comment, source query, [(column, delta type)]). The column list is the
# contract: the Postgres select and the Delta cast are written next to each other so a type
# cannot drift between them unnoticed.
TABLES = [
    (
        "dim_plan",
        "Plan catalogue copied from Lakebase billing.plans. monthly_fee is the list price "
        "that MRR is built from; overage_rate is the per-unit price used for overage and "
        "for attributed storage cost.",
        "SELECT id, code, tier_cd, monthly_fee, included_units, overage_rate, active_yn "
        "FROM billing.plans",
        [("plan_id", "STRING"), ("plan_code", "STRING"), ("tier_cd", "SMALLINT"),
         ("monthly_fee", "DECIMAL(12,2)"), ("included_units", "BIGINT"),
         ("overage_rate", "DECIMAL(12,6)"), ("active_yn", "STRING")],
    ),
    (
        "dim_tenant",
        "Tenant master copied from Lakebase billing.tenants. This is the OLTP tenant "
        "population (69 tenants); the migrated invoice history in ow_tp.silver uses a "
        "separate legacy customer key and does not join to it.",
        "SELECT id, name, tax_exempt_yn, status_cd FROM billing.tenants",
        [("tenant_id", "STRING"), ("tenant_name", "STRING"), ("tax_exempt_yn", "STRING"),
         ("status_cd", "SMALLINT")],
    ),
    (
        "fct_subscription",
        "Subscriptions copied from Lakebase billing.subscriptions. One row per "
        "subscription, unfiltered: the active-subscription rule is applied downstream in "
        "ow_tp.gold.fct_subscription_mrr, not here.",
        "SELECT id, tenant_id, plan_id, starts_on, ends_on, status_cd, suspended_on "
        "FROM billing.subscriptions",
        [("subscription_id", "STRING"), ("tenant_id", "STRING"), ("plan_id", "STRING"),
         ("starts_on", "TIMESTAMP_NTZ"), ("ends_on", "TIMESTAMP_NTZ"),
         ("status_cd", "SMALLINT"), ("suspended_on", "TIMESTAMP_NTZ")],
    ),
    (
        "fct_credit_note",
        "Credit notes copied from Lakebase billing.credit_notes. Carried for visibility "
        "only: a credit note has no invoice reference in the estate, so it reduces neither "
        "ARR nor the AR open balance. See databricks/gold/METRIC_DEFINITIONS.md.",
        "SELECT id, tenant_id, issued_on, amount, remaining_amount FROM billing.credit_notes",
        [("credit_note_id", "STRING"), ("tenant_id", "STRING"), ("issued_on", "TIMESTAMP_NTZ"),
         ("amount", "DECIMAL(14,2)"), ("remaining_amount", "DECIMAL(14,2)")],
    ),
    (
        "fct_rating_result",
        "Rating results as the legacy rating engine computed them, joined to their period. "
        "Not an input to ow_tp.gold.fct_usage_period: it is the independent number the "
        "recomputed overage is checked against, and the source of the rollover credit.",
        "SELECT rr.id, rp.id, rp.tenant_id, rp.period_start, rp.period_end, "
        "rr.subscription_id, rr.used_units, rr.quota_units, rr.rollover_units, "
        "rr.billable_units, rr.overage_amount, rr.created_at "
        "FROM billing.rating_results rr JOIN billing.rating_periods rp ON rp.id = rr.period_id",
        [("rating_result_id", "STRING"), ("period_id", "STRING"), ("tenant_id", "STRING"),
         ("period_start", "TIMESTAMP_NTZ"), ("period_end", "TIMESTAMP_NTZ"),
         ("subscription_id", "STRING"), ("used_units", "BIGINT"), ("quota_units", "BIGINT"),
         ("rollover_units", "BIGINT"), ("billable_units", "BIGINT"),
         ("overage_amount", "DECIMAL(14,2)"), ("created_at", "TIMESTAMP_NTZ")],
    ),
]


def lakebase_dsn(w: WorkspaceClient, branch: str) -> str:
    if branch not in ALLOWED_BRANCHES:
        raise SystemExit(f"branch {branch!r} is not an allowed migration branch")
    endpoints = w.api_client.do(
        "GET", f"/api/2.0/postgres/projects/{PROJECT}/branches/{branch}/endpoints")
    # The pooled host rejects the generated OAuth credential; connect to the endpoint host.
    host = endpoints["endpoints"][0]["status"]["hosts"]["host"]
    user = w.current_user.me().user_name
    token = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={
        "endpoint": f"projects/{PROJECT}/branches/{branch}/endpoints/primary"})["token"]
    return (f"host={host} port=5432 dbname={DATABASE} user={user} "
            f"password={token} sslmode=require")


def sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, decimal.Decimal)):
        return str(value)
    if isinstance(value, dt.datetime):
        return "'" + value.isoformat(sep=" ", timespec="microseconds") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def rebuild_statement(table: str, comment: str, columns: list[tuple[str, str]],
                      rows: list[tuple], branch: str) -> str:
    cols = ", ".join(f"CAST(c{i} AS {t}) AS {name}" for i, (name, t) in enumerate(columns))
    values = ",\n         ".join(
        "(" + ", ".join(sql_literal(v) for v in row) + ")" for row in rows)
    placeholders = ", ".join(f"c{i}" for i in range(len(columns)))
    return (
        f"CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.{table}\n"
        f"COMMENT {sql_literal(comment)}\n"
        f"AS SELECT {cols},\n"
        f"          CAST({sql_literal(branch)} AS STRING) AS source_lakebase_branch,\n"
        f"          CAST(current_timestamp() AS TIMESTAMP_NTZ) AS ingested_at\n"
        f"     FROM VALUES\n         {values}\n"
        f"     AS t({placeholders})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="mig-p1-w2",
                    help="Lakebase branch holding the migrated billing schema")
    ap.add_argument("--dry-run", action="store_true",
                    help="read Lakebase and print row counts without writing Delta")
    args = ap.parse_args(argv)

    w = WorkspaceClient()
    summary = {}
    with psycopg.connect(lakebase_dsn(w, args.branch)) as conn:
        for table, comment, query, columns in TABLES:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
            if not rows:
                raise SystemExit(
                    f"billing source for {table} returned no rows; refusing to replace "
                    f"{CATALOG}.{SCHEMA}.{table} with an empty table")
            summary[table] = len(rows)
            if args.dry_run:
                continue
            # run() polls to a terminal state. A wait timeout only bounds the API call, not
            # the statement, so treating PENDING/RUNNING as failure would abandon a CTAS that
            # then replaces the table after the load has already given up on the rest.
            run(w, rebuild_statement(table, comment, columns, rows, args.branch), {})

    print(json.dumps({"branch": args.branch, "dry_run": args.dry_run,
                      "rows_ingested": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
