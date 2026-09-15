"""Publish the current period of the meter to Lakebase so billing can read it.

The billing application reads Postgres, not Delta, so the invoice-time figures
have to live in Lakebase. One run replaces the whole current-period slice inside
a single transaction: readers see either the previous slice or the new one, never
a half-written one.

Target: project `ow-tp-billing`, branch `mig-p1-w0`, database `ow_tp`, schema
`billing`. The branch is checked against an allowlist before a credential is
minted, and `production` is refused outright. Timestamps are `timestamp` without
time zone, matching the zoneless Oracle source.

    python3 lakebase_sync.py [--branch mig-p1-w0] [--period 2026-02-01]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any

# The Lakeflow task execs this file without setting __file__, so fall back to argv.
for _candidate in (globals().get("__file__"), sys.argv[0]):
    if _candidate:
        sys.path.insert(0, os.path.dirname(os.path.abspath(_candidate)))

from executor import get_executor
from meter_sql import PRODUCTION, Namespace, current_period, current_period_rows

PROJECT = "ow-tp-billing"
DATABASE = "ow_tp"
SCHEMA = "billing"
TABLE = f"{SCHEMA}.usage_meter_current"
STATE_TABLE = f"{SCHEMA}.usage_meter_sync_state"
# Migration branches only. `production` is never a target for this pipeline.
ALLOWED_BRANCHES = ("mig-p1-w0", "mig-p1-w1", "mig-p1-w2")

DDL = (
    f"""CREATE TABLE IF NOT EXISTS {TABLE} (
  tenant_id text NOT NULL,
  metric text NOT NULL,
  kind_cd smallint NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  event_count bigint NOT NULL,
  units_total bigint NOT NULL,
  late_event_count bigint NOT NULL,
  avg_units_per_event double precision NOT NULL,
  first_event_at timestamp NOT NULL,
  last_event_at timestamp NOT NULL,
  meter_computed_at timestamp NOT NULL,
  synced_at timestamp NOT NULL,
  CONSTRAINT pk_usage_meter_current PRIMARY KEY (tenant_id, metric, period_start),
  CONSTRAINT ck_usage_meter_current_positive CHECK (event_count > 0 AND units_total > 0),
  CONSTRAINT ck_usage_meter_current_period CHECK (period_end >= period_start)
)""",
    f"""COMMENT ON TABLE {TABLE} IS
 'Current-period per-tenant usage meter, published from ow_tp.gold.usage_meter_period. Read-only for the billing application; replaced atomically by the ow_tp_usage_meter job.'""",
    f"""CREATE TABLE IF NOT EXISTS {STATE_TABLE} (
  meter text PRIMARY KEY,
  period_start date NOT NULL,
  period_end date NOT NULL,
  row_count bigint NOT NULL,
  units_total bigint NOT NULL,
  source_watermark timestamp NOT NULL,
  synced_at timestamp NOT NULL
)""",
    f"""COMMENT ON TABLE {STATE_TABLE} IS
 'What the last usage meter sync published, so billing can tell how fresh the figures are.'""",
)


def _workspace():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def dsn(branch: str) -> str:
    """Short-lived OAuth DSN for the branch endpoint. Never logged, never stored."""
    if branch not in ALLOWED_BRANCHES:
        raise SystemExit(f"refusing to connect: {branch!r} is not a migration branch")
    w = _workspace()
    endpoints = w.api_client.do(
        "GET", f"/api/2.0/postgres/projects/{PROJECT}/branches/{branch}/endpoints")
    items = endpoints if isinstance(endpoints, list) else endpoints.get("endpoints", [])
    # The pooled host rejects the generated credential; connect to the endpoint host.
    host = items[0]["status"]["hosts"]["host"]
    token = w.api_client.do(
        "POST", "/api/2.0/postgres/credentials",
        body={"endpoint": f"projects/{PROJECT}/branches/{branch}/endpoints/primary"})["token"]
    user = w.current_user.me().user_name
    return f"host={host} port=5432 dbname={DATABASE} user={user} password={token} sslmode=require"


def sync(branch: str = "mig-p1-w0", period: str | None = None,
         ns: Namespace = PRODUCTION) -> dict[str, Any]:
    import psycopg

    ex = get_executor()
    # The period reaches Databricks SQL as a literal, so it is parsed as a date first.
    period_start = str(date.fromisoformat(period)) if period else str(ex.scalar(current_period(ns)))
    rows = ex.sql(current_period_rows(ns, period_start))
    if not rows:
        raise SystemExit(f"meter has no rows for period {period_start}")
    watermark = ex.scalar(
        f"SELECT MAX(source_watermark) FROM {ns.meter} WHERE period_start = DATE'{period_start}'")

    payload = [(r["tenant_id"], r["metric"], int(r["kind_cd"]), r["period_start"], r["period_end"],
                int(r["event_count"]), int(r["units_total"]), int(r["late_event_count"]),
                float(r["avg_units_per_event"]), r["first_event_at"], r["last_event_at"],
                r["computed_at"]) for r in rows]

    with psycopg.connect(dsn(branch)) as conn:
        with conn.cursor() as cur:
            for statement in DDL:
                cur.execute(statement)
            conn.commit()
        # Everything below is one transaction: billing never sees a partial slice.
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE stage_usage_meter (LIKE " + TABLE
                        + " INCLUDING DEFAULTS) ON COMMIT DROP")
            cur.execute("SELECT LOCALTIMESTAMP")
            (synced_at,) = cur.fetchone()
            with cur.copy(
                "COPY stage_usage_meter (tenant_id, metric, kind_cd, period_start, period_end,"
                " event_count, units_total, late_event_count, avg_units_per_event,"
                " first_event_at, last_event_at, meter_computed_at, synced_at) FROM STDIN"
            ) as copy:
                for record in payload:
                    copy.write_row(record + (synced_at,))
            # The table holds the current period only, so rows from a period that is
            # no longer current go too, not just rows missing from this one.
            cur.execute(f"DELETE FROM {TABLE} t WHERE NOT EXISTS ("
                        "SELECT 1 FROM stage_usage_meter s"
                        " WHERE s.tenant_id = t.tenant_id AND s.metric = t.metric"
                        " AND s.period_start = t.period_start)")
            cur.execute(f"""INSERT INTO {TABLE}
SELECT * FROM stage_usage_meter
ON CONFLICT (tenant_id, metric, period_start) DO UPDATE SET
  kind_cd = EXCLUDED.kind_cd,
  period_end = EXCLUDED.period_end,
  event_count = EXCLUDED.event_count,
  units_total = EXCLUDED.units_total,
  late_event_count = EXCLUDED.late_event_count,
  avg_units_per_event = EXCLUDED.avg_units_per_event,
  first_event_at = EXCLUDED.first_event_at,
  last_event_at = EXCLUDED.last_event_at,
  meter_computed_at = EXCLUDED.meter_computed_at,
  synced_at = EXCLUDED.synced_at""")
            cur.execute(f"""INSERT INTO {STATE_TABLE}
  (meter, period_start, period_end, row_count, units_total, source_watermark, synced_at)
SELECT 'ow_tp_usage_meter', %s, MAX(period_end), COUNT(*), SUM(units_total), %s, LOCALTIMESTAMP
FROM {TABLE} WHERE period_start = %s
ON CONFLICT (meter) DO UPDATE SET
  period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
  row_count = EXCLUDED.row_count, units_total = EXCLUDED.units_total,
  source_watermark = EXCLUDED.source_watermark, synced_at = EXCLUDED.synced_at""",
                        (period_start, watermark, period_start))
            cur.execute(f"SELECT COUNT(*), SUM(units_total) FROM {TABLE} WHERE period_start = %s",
                        (period_start,))
            published, units = cur.fetchone()
        conn.commit()

    return {"stage": "lakebase_sync", "branch": branch, "period_start": period_start,
            "rows_published": int(published), "units_total": int(units)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", default=os.environ.get("OW_TP_LAKEBASE_BRANCH", "mig-p1-w0"))
    parser.add_argument("--period", default=None, help="period start, e.g. 2026-02-01")
    args = parser.parse_args(argv)
    print(json.dumps(sync(args.branch, args.period), default=str))
    return 0


if __name__ == "__main__":
    # The Lakeflow task execs this file, where SystemExit(0) still marks the run
    # failed, so only exit on a non-zero code.
    _code = main(sys.argv[1:])
    if _code:
        sys.exit(_code)
