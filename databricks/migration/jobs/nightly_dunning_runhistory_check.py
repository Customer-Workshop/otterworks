#!/usr/bin/env python3
"""Unit p1-job-nightly-dunning (U-25): run-history equivalence, legacy job vs converted job.

`JOB_NIGHTLY_DUNNING` is DISABLED in the source, so there is no legacy run history to
compare a converted run against, and no live run will ever appear for this migration. What
can be compared is a run of each side over the same input state, which is what this program
does, once per `as_of`:

  1. on the Oracle billing fixture (`make oracle-billing-up`), run the scheduler job's own
     text - `BEGIN pkg_dunning.sp_schedule_dunning(:d); pkg_dunning.sp_suspend_overdue(:d);
     END;` - and record every row the run wrote or changed, then roll back;
  2. on Lakebase, run the converted job body (`ow_tp_p1_nightly_dunning.run_chain`, the
     same function the deployed task calls) with the same `as_of`, record the same rows,
     then roll back so the shared wave branch is left as it was found;
  3. compare the two row sets - `dunning_attempts` inserts, `tenants` / `subscriptions`
     updates, `notifications` inserts - as sets of canonical tuples.

Both sides are rolled back, so this is a comparison of what a run *would* write. Two caveats
it cannot roll back or prove, and that belong in the unit's summary:

  - `log_msg` is an autonomous transaction on Oracle (D2-02): its audit rows commit even
     though the run is rolled back, so the fixture keeps them. The converted `log_msg` is
     an ordinary call and its rows roll back with everything else. The audit table is
     therefore excluded from the comparison and the difference is declared, not hidden;
  - an `as_of` chosen here is not proof for every date. The dates are given on the command
     line so a weekday and a weekend date can both be run: the weekend shift is the part of
     the legacy scheduling logic most likely to diverge.

usage:
  python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w2 -- \\
    python3 databricks/migration/jobs/nightly_dunning_runhistory_check.py \\
      --as-of 2026-09-15 --as-of 2026-09-12 --out evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ow_tp_p1_nightly_dunning import next_weekday, run_chain  # noqa: E402

# The tables the legacy chain writes: the dunning batch, and the three the suspension sweep
# touches. Each is read with an explicit column list so the two dialects line up by
# position, and keyed on its primary key so an update is visible as a changed row.
TABLES = {
    "dunning_attempts": ["id", "tenant_id", "invoice_id", "attempt_no", "scheduled_for",
                         "status_cd"],
    "tenants": ["id", "status_cd"],
    "subscriptions": ["id", "tenant_id", "status_cd", "suspended_on"],
    "notifications": ["id", "tenant_id", "kind_cd", "sent_at"],
}

LEGACY_BLOCK = ("BEGIN pkg_dunning.sp_schedule_dunning(:d); "
                "pkg_dunning.sp_suspend_overdue(:d); END;")


def canon(value) -> object:
    """One canonical form for both dialects: ISO timestamps, decimal money as a string."""
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    return value


def snapshot(cur, qualify: str = "") -> dict:
    out = {}
    for table, columns in TABLES.items():
        cur.execute(f"SELECT {', '.join(columns)} FROM {qualify}{table}")
        out[table] = {row[0]: tuple(canon(v) for v in row) for row in cur.fetchall()}
    return out


def written(before: dict, after: dict) -> dict:
    """The run's history: what it inserted and what it changed, per table."""
    history = {}
    for table in TABLES:
        b, a = before[table], after[table]
        history[table] = {
            "inserted": sorted(a[k] for k in a.keys() - b.keys()),
            "changed": sorted([b[k], a[k]] for k in a.keys() & b.keys() if a[k] != b[k]),
            "deleted": sorted(b[k] for k in b.keys() - a.keys()),
        }
    return history


def legacy_run(as_of: datetime, executions: int = 1) -> dict:
    import oracledb

    dsn = (f"{os.environ.get('ORACLE_BILLING_HOST', '127.0.0.1')}:"
           f"{os.environ.get('ORACLE_BILLING_DB_PORT', '52521')}/FREEPDB1")
    with oracledb.connect(user="ow_billing", password="ow_billing", dsn=dsn) as conn:
        cur = conn.cursor()
        state = snapshot(cur)
        raised, history = [], []
        for _ in range(executions):
            try:
                cur.execute(LEGACY_BLOCK, d=as_of)
                raised.append(None)
            except Exception as exc:  # reported, never smoothed
                raised.append(f"{type(exc).__name__}: {exc}")
            after = snapshot(cur)
            history.append(written(state, after))
            state = after
        conn.rollback()
    return {"raised": raised, "history": history}


def converted_run(as_of: datetime, schema: str, executions: int = 1) -> dict:
    import psycopg

    with psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"]) as conn:
        with conn.cursor() as cur:
            state = snapshot(cur, qualify=f"{schema}.")
        raised, history, results = [], [], []
        for _ in range(executions):
            try:
                results.append(run_chain(conn, as_of, schema))
                raised.append(None)
            except Exception as exc:  # reported, never smoothed
                raised.append(f"{type(exc).__name__}: {exc}")
                results.append(None)
            with conn.cursor() as cur:
                after = snapshot(cur, qualify=f"{schema}.")
            history.append(written(state, after))
            state = after
        conn.rollback()
    return {"raised": raised, "result": results, "history": history}


def compare(as_of: datetime, schema: str, executions: int = 1) -> dict:
    legacy = legacy_run(as_of, executions)
    converted = converted_run(as_of, schema, executions)
    differences = {
        f"run{i + 1}.{t}": {"legacy": legacy["history"][i][t],
                            "converted": converted["history"][i][t]}
        for i in range(executions) for t in TABLES
        if legacy["history"][i][t] != converted["history"][i][t]}
    return {
        "as_of": as_of.date().isoformat(),
        "weekday": as_of.strftime("%a"),
        "executions": executions,
        "expected_scheduled_for": next_weekday(as_of).date().isoformat(),
        "legacy": legacy,
        "converted": converted,
        "equivalent": (not differences
                       and legacy["raised"] == converted["raised"] == [None] * executions),
        "differences": differences,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", action="append", required=True, help="YYYY-MM-DD, repeatable")
    ap.add_argument("--schema", default="billing")
    ap.add_argument("--out", type=Path, help="write the evidence JSON here")
    ap.add_argument("--executions", type=int, default=1,
                    help="times to run the chain per side, in one transaction: >1 compares "
                         "the rerun too, which is how a non-idempotent chain is held to "
                         "the legacy rerun behaviour instead of a cleaner one")
    args = ap.parse_args(argv)

    runs = [compare(datetime.strptime(d, "%Y-%m-%d"), args.schema, args.executions)
            for d in args.as_of]
    evidence = {
        "kind": "u25-run-history-equivalence",
        "unit": "p1-job-nightly-dunning",
        "legacy_job": "JOB_NIGHTLY_DUNNING (DISABLED in the source: no live run exists)",
        "converted_job": "ow_tp_p1_nightly_dunning",
        "source": "Oracle billing fixture (make oracle-billing-up)",
        "target": "Lakebase ow-tp-billing/mig-p1-w2, schema billing",
        "both_sides_rolled_back": True,
        "excluded": ["billing_audit_log: log_msg is an autonomous transaction on Oracle "
                     "(D2-02) and an ordinary call on the target, so its rows survive the "
                     "rollback on one side only"],
        "runs": runs,
        "equivalent": all(r["equivalent"] for r in runs),
    }
    text = json.dumps(evidence, indent=2, default=str)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0 if evidence["equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
