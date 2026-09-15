#!/usr/bin/env python3
"""Unit p1-job-nightly-dunning (U-25): the converted body of JOB_NIGHTLY_DUNNING.

The legacy object is a DBMS_SCHEDULER job whose whole definition is one PL/SQL block:

    BEGIN pkg_dunning.sp_schedule_dunning(TRUNC(SYSDATE));
          pkg_dunning.sp_suspend_overdue(TRUNC(SYSDATE)); END;

run daily at 02:00 and currently DISABLED in the source. This module is that block on the
converted side: it opens one Lakebase session, calls `billing.sp_schedule_dunning` and then
`billing.sp_suspend_overdue` with the same `as_of`, and commits once at the end. The
procedures themselves are unit p1-pkg-dunning's (w3-d) and are read, never re-converted.

What the conversion has to keep, and how:

  - one transaction for both calls. The scheduler ran the block in a single session and
    committed at the end, so a failure in the sweep leaves no half-written dunning batch;
  - the same `as_of` for both calls. `TRUNC(SYSDATE)` was evaluated twice in the legacy
    block, so a run crossing midnight used two different dates; here it is read once and
    passed to both, which is the behaviour the job intended and the only one reproducible
    from a job parameter. That difference is declared in the unit's summary.md;
  - package state stays explicit (plan decision P1-D4): `sp_schedule_dunning` returns the
    `scheduled_cnt` / `last_run_dt` that used to live in `pkg_dunning` globals, and this
    module reports them as the run's output instead of leaving them in a session global;
  - nothing is retried and nobody is notified. The legacy job told no one when it failed.

The Lakebase credential is minted per run from the job's own identity and lives only in
this process; it is never printed or persisted. The branch is a parameter because each wave
runs on its own branch, and `production` is refused here as well as in the deploy script -
repointing production is the owner's STOP E cutover decision, not this job's.

usage (locally, against the wave branch):
  python3 databricks/migration/jobs/ow_tp_p1_nightly_dunning.py --lakebase-branch mig-p1-w2
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

PROJECT = "ow-tp-billing"
DATABASE = "ow_tp"
SCHEMA = "billing"
# This unit's write target, and the only branch the task will connect to. `production` is
# not merely excluded: repointing it is the STOP E cutover decision, which this code does
# not get to make, and a mistyped branch name must fail rather than write dunning rows
# somewhere outside the unit's declared target.
DEFAULT_BRANCH = "mig-p1-w2"
ALLOWED_BRANCHES = (DEFAULT_BRANCH,)


def lakebase_dsn(branch: str, database: str = DATABASE) -> str:
    """Mint a short-lived Lakebase DSN for `branch` from the running identity."""
    from databricks.sdk import WorkspaceClient

    if branch not in ALLOWED_BRANCHES:
        raise SystemExit(f"refusing to run against the {branch!r} Lakebase branch; "
                         f"this job writes only {', '.join(ALLOWED_BRANCHES)}")
    w = WorkspaceClient()
    parent = f"projects/{PROJECT}/branches/{branch}"
    endpoints = w.api_client.do("GET", f"/api/2.0/postgres/{parent}/endpoints")
    # The pooled host rejects the generated OAuth credential; connect to the endpoint host.
    host = endpoints["endpoints"][0]["status"]["hosts"]["host"]
    token = w.api_client.do("POST", "/api/2.0/postgres/credentials",
                            body={"endpoint": f"{parent}/endpoints/primary"})["token"]
    user = w.current_user.me().user_name
    return (f"host={host} port=5432 dbname={database} user={user} "
            f"password={token} sslmode=require")


def as_of_default(now: datetime | None = None) -> datetime:
    """`TRUNC(SYSDATE)`: midnight of the run's own day, UTC (plan decision P1-D3)."""
    now = now or datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day)


def run_chain(conn, as_of: datetime, schema: str = SCHEMA) -> dict:
    """Run the converted job body once on an open Lakebase connection.

    The caller owns the transaction: the job commits it, the run-history check rolls it
    back so a fixture comparison leaves the shared branch as it found it.
    """
    from psycopg import sql

    name = sql.Identifier(schema)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CALL {}.sp_schedule_dunning(%s, %s, %s)").format(name),
                    (as_of, 0, None))
        scheduled_cnt, last_run_dt = cur.fetchone()
        cur.execute(sql.SQL("CALL {}.sp_suspend_overdue(%s)").format(name), (as_of,))
    return {"as_of": as_of.isoformat(), "scheduled_cnt": scheduled_cnt,
            "last_run_dt": last_run_dt.isoformat() if last_run_dt else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", help="YYYY-MM-DD; defaults to the run's own UTC date")
    ap.add_argument("--lakebase-branch", default=DEFAULT_BRANCH)
    ap.add_argument("--schema", default=SCHEMA)
    args = ap.parse_args(argv)

    import psycopg

    as_of = (datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of
             else as_of_default())
    with psycopg.connect(lakebase_dsn(args.lakebase_branch)) as conn:
        result = run_chain(conn, as_of, args.schema)
        conn.commit()
    print(json.dumps({"job": "ow_tp_p1_nightly_dunning",
                      "branch": args.lakebase_branch, **result}))
    return 0


def next_weekday(day: datetime) -> datetime:
    """The legacy `DECODE(TO_CHAR(d,'DY'), 'SAT', 2, 'SUN', 1, 0)` weekend shift.

    Kept here because the run-history check predicts the scheduled date independently of
    the procedure it is checking.
    """
    return day + timedelta(days={5: 2, 6: 1}.get(day.weekday(), 0))


if __name__ == "__main__":
    raise SystemExit(main())
