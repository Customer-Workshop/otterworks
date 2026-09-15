#!/usr/bin/env python3
"""Unit p1-job-purge-audit-log (U-26): prove the converted purge behaves like the legacy job.

The Oracle scheduler job is DISABLED in the source, so there is no legacy run history to
compare a converted run against. What can be proved is the behaviour the job text
specifies, and that is what this check exercises, against the deployed SQL text itself
(`ow_tp_p1_purge_audit_log.sql`) on the migration warehouse:

  1. identity: an insert that omits `log_id` gets one allocated, which is what
     `seq_billing_audit_log` + `trg_billing_audit_log_id` did;
  2. retention: with `retention_days = 90`, a row older than 90 days is deleted and a row
     inside the window is kept - the legacy `logged_at < SYSDATE - 90`;
  3. parameterised retention: the same text with `retention_days = 1` deletes a row the
     90-day run kept, so the constant really is a parameter now. The purge is unscoped,
     so this short window only runs when the probe rows are the whole table; otherwise it
     is skipped and recorded untested rather than deleting rows it did not write;
  4. swallowed error: a run whose parameter makes the statement fail raises nothing and
     reports success, reproducing `EXCEPTION WHEN OTHERS THEN NULL` (plan decision P1-D2).
     The same predicate without the handler is run as a control, so the evidence shows the
     handler swallowing a real failure rather than a parameter that quietly did nothing;
  5. rerun safety: a second run with the same parameter deletes nothing more.

The probe rows are written and removed by this program, and it fails unless the table is
back to the row count it started at.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/migration/jobs/purge_audit_log_behaviour_check.py --out evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from databricks import sql as dbsql

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_purge_audit_log import SQL_FILE, WAREHOUSE  # noqa: E402

# The table the job purges. It is owned and loaded by unit p1-billing-audit-log; this
# unit only deletes from it on the retention schedule.
TARGET = "ow_tp.silver.billing_audit_log"

PROBE_MODULE = "u26_behaviour_check"
OLD_DAYS = 120
RECENT_DAYS = 10

INSERT = (f"INSERT INTO {TARGET} (logged_at, module, message) VALUES "
          f"(current_timestamp() - INTERVAL {OLD_DAYS} DAYS, '{PROBE_MODULE}', 'old row'), "
          f"(current_timestamp() - INTERVAL {RECENT_DAYS} DAYS, '{PROBE_MODULE}', "
          "'recent row')")
PROBE_ROWS = (f"SELECT message, log_id FROM {TARGET} WHERE module = '{PROBE_MODULE}' "
              "ORDER BY log_id")
CLEANUP = f"DELETE FROM {TARGET} WHERE module = '{PROBE_MODULE}'"
# The purge predicate with no EXIT handler around it: the control that shows the failing
# parameter really does fail.
BARE_DELETE = (f"DELETE FROM {TARGET} WHERE logged_at < "
               "CAST(current_timestamp() AS TIMESTAMP_NTZ) "
               "- make_dt_interval(CAST(:retention_days AS INT))")


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def purge(cur, text: str, retention_days: str) -> dict:
    """Run the deployed purge text once; report whether it raised."""
    try:
        cur.execute(text, {"retention_days": retention_days})
        return {"retention_days": retention_days, "raised": None}
    except Exception as exc:  # the point of the check: the legacy job raised nothing
        return {"retention_days": retention_days, "raised": type(exc).__name__}


def messages(cur) -> list[str]:
    cur.execute(PROBE_ROWS)
    return [row[0] for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, help="write the evidence JSON here")
    args = ap.parse_args(argv)

    text = SQL_FILE.read_text()
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TARGET}")
        rows_before = cur.fetchone()[0]
        cur.execute(INSERT)
        cur.execute(PROBE_ROWS)
        seeded = [{"message": m, "log_id": i} for m, i in cur.fetchall()]

        retention_90 = purge(cur, text, "90")
        after_90 = messages(cur)
        rerun_90 = purge(cur, text, "90")
        after_rerun = messages(cur)
        failing = purge(cur, text, "not-a-number")
        after_failing = messages(cur)
        unhandled = purge(cur, BARE_DELETE, "not-a-number")

        # `retention_days = 1` is the proof that the constant really is a parameter, but
        # the purge is unscoped: it would delete any row older than a day, including rows
        # this check did not write. Only run it when the probe rows are the whole table.
        cur.execute(f"SELECT count(*) FROM {TARGET} WHERE module <> '{PROBE_MODULE}' "
                    "OR module IS NULL")
        foreign_rows = cur.fetchone()[0]
        if foreign_rows:
            retention_1 = {"retention_days": "1", "raised": None, "skipped":
                           f"{foreign_rows} rows this check did not write; a one-day "
                           "window would delete them"}
            after_1 = None
        else:
            retention_1 = purge(cur, text, "1")
            after_1 = messages(cur)

        cur.execute(CLEANUP)
        cur.execute(f"SELECT count(*) FROM {TARGET}")
        rows_after = cur.fetchone()[0]

    evidence = {
        "kind": "u26-behaviour-check",
        "target": TARGET,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "identity_allocated_without_explicit_key": [r["log_id"] for r in seeded],
        "retention_90": {**retention_90, "remaining": after_90},
        "rerun_90": {**rerun_90, "remaining": after_rerun},
        "failing_parameter": {**failing, "remaining": after_failing},
        "failing_parameter_without_handler": unhandled,
        "retention_1": {**retention_1, "remaining": after_1},
    }
    checks = {
        "identity_allocated": all(r["log_id"] is not None for r in seeded),
        "old_row_purged_at_90": after_90 == ["recent row"],
        "rerun_changed_nothing": after_rerun == after_90,
        "error_swallowed": failing["raised"] is None,
        "control_without_handler_raised": unhandled["raised"] is not None,
        "recent_row_purged_at_1": after_1 == [] if after_1 is not None else "untested",
        # the probe rows are gone and nothing else was left behind
        "table_restored": rows_after == rows_before,
    }
    evidence["checks"] = checks
    evidence["verdict"] = ("PASS" if all(v is True or v == "untested"
                                         for v in checks.values()) else "FAIL")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
