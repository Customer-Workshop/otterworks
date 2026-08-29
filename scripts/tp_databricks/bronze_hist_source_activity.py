#!/usr/bin/env python3
"""Exercise the OW_BILLING capture triggers so the history tables hold rows.

CUSTOMER_MASTER_HIST and SUBSCRIPTIONS_HIST are written exclusively by
trg_customer_master_hist / trg_subscriptions_hist, which fire on UPDATE and
DELETE of the base tables. A local estate that has only ever been loaded (the
loader clears both history tables as part of its per-batch cleanup) therefore
carries no history, and the bronze_hist unit has nothing to migrate.

This utility performs ordinary maintenance activity against the local OW_BILLING
fixture -- balance and contact updates, account closures, plan changes,
suspensions and subscription removals -- and lets the estate's own triggers
record it. It writes no history row itself: every HIST_DT, HIST_OP and HIST_ID
value is produced by the triggers exactly as it is in the source system.

Activity is deterministic for a given --ns and --rounds, so the source
population a recon run measures can be reproduced.

    uv run --with oracledb==2.5.1 python3 \
        scripts/tp_databricks/bronze_hist_source_activity.py --ns demo

Local fixture only. It is never pointed at a customer estate.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys

import oracledb

MONS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# Reserved for the stored-procedure parity harness; activity here stays clear of
# them so recorded transcripts keep matching.
STATIC_TENANTS = tuple(f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 10))


def ns_seed(ns: str) -> int:
    return int(hashlib.md5(ns.encode()).hexdigest()[:8], 16)


def legacy_date(rng: random.Random) -> str:
    """A VARCHAR2(9) date in the estate's DD-MON-YY spelling."""
    return f"{rng.randint(1, 28):02d}-{rng.choice(MONS)}-{rng.randint(20, 26):02d}"


def customer_activity(cur, rng: random.Random, rounds: int, updates: int, closures: int) -> None:
    cur.execute("SELECT cust_id FROM customer_master ORDER BY cust_no")
    cust_ids = [r[0] for r in cur.fetchall()]
    if not cust_ids:
        raise SystemExit("customer_master is empty: load the estate before generating activity")

    # Several passes over an overlapping population, so a customer accumulates
    # more than one version -- which is what makes the history table worth
    # migrating in the first place.
    for round_no in range(rounds):
        for cust_id in rng.sample(cust_ids, min(updates, len(cust_ids))):
            cur.execute(
                """UPDATE customer_master
                      SET cur_bal_amt      = NVL(cur_bal_amt, 0) + :delta,
                          past_due_amt     = NVL(past_due_amt, 0) + :past_due,
                          last_activity_dt = :activity_dt,
                          contact_notes    = :notes,
                          updated_by       = 'BATCH_MAINT',
                          updated_dt       = SYSDATE,
                          row_version_no   = NVL(row_version_no, 1) + 1
                    WHERE cust_id = :cust_id""",
                delta=round(rng.uniform(-450, 1200), 2),
                past_due=round(rng.uniform(0, 300), 2),
                activity_dt=legacy_date(rng),
                notes=f"maintenance pass {round_no + 1}",
                cust_id=cust_id,
            )

    # Account closures. The customer row goes; its last known state survives
    # only in CUSTOMER_MASTER_HIST, which is why those rows must be migrated.
    for cust_id in rng.sample(cust_ids, min(closures, len(cust_ids))):
        cur.execute(
            """UPDATE customer_master
                  SET status_cd    = 90,
                      terminate_dt = :terminate_dt,
                      updated_by   = 'BATCH_CLOSE',
                      updated_dt   = SYSDATE
                WHERE cust_id = :cust_id""",
            terminate_dt=legacy_date(rng),
            cust_id=cust_id,
        )
        cur.execute("DELETE FROM entity_attr_value WHERE entity_id = :cust_id", cust_id=cust_id)
        cur.execute("DELETE FROM customer_master WHERE cust_id = :cust_id", cust_id=cust_id)


def subscription_activity(cur, rng: random.Random, plan_changes: int, suspensions: int, removals: int) -> None:
    binds = {f"t{i}": t for i, t in enumerate(STATIC_TENANTS)}
    excluded = ", ".join(f":{k}" for k in binds)
    cur.execute(
        f"""SELECT s.id
              FROM subscriptions s
             WHERE s.tenant_id NOT IN ({excluded})
               AND NOT EXISTS (SELECT 1 FROM rating_results r WHERE r.subscription_id = s.id)
             ORDER BY s.id""",
        binds,
    )
    sub_ids = [r[0] for r in cur.fetchall()]
    if not sub_ids:
        raise SystemExit("no eligible subscriptions: load the estate before generating activity")

    cur.execute("SELECT id FROM plans WHERE active_yn = 'Y' ORDER BY code")
    plan_ids = [r[0] for r in cur.fetchall()]

    for sub_id in rng.sample(sub_ids, min(plan_changes, len(sub_ids))):
        cur.execute(
            "UPDATE subscriptions SET plan_id = :plan_id WHERE id = :sub_id",
            plan_id=rng.choice(plan_ids),
            sub_id=sub_id,
        )

    # status 20 is the suspended state the rating proration keys off.
    for sub_id in rng.sample(sub_ids, min(suspensions, len(sub_ids))):
        cur.execute(
            """UPDATE subscriptions
                  SET status_cd = 20,
                      suspended_on = TRUNC(SYSDATE) - :age
                WHERE id = :sub_id""",
            age=rng.randint(1, 60),
            sub_id=sub_id,
        )

    for sub_id in rng.sample(sub_ids, min(removals, len(sub_ids))):
        cur.execute("DELETE FROM subscriptions WHERE id = :sub_id", sub_id=sub_id)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", default="demo", help="namespace whose seeded RNG drives the activity")
    ap.add_argument("--rounds", type=int, default=3, help="maintenance passes over customer_master")
    ap.add_argument("--customer-updates", type=int, default=120, help="customers touched per pass")
    ap.add_argument("--customer-closures", type=int, default=40, help="accounts closed and removed")
    ap.add_argument("--plan-changes", type=int, default=18)
    ap.add_argument("--suspensions", type=int, default=12)
    ap.add_argument("--subscription-removals", type=int, default=8)
    ap.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--password", default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    args = ap.parse_args()

    rng = random.Random(ns_seed(args.ns))
    dsn = f"{args.host}:{args.port}/{args.service}"
    with oracledb.connect(user=args.user, password=args.password, dsn=dsn) as conn:
        cur = conn.cursor()
        customer_activity(cur, rng, args.rounds, args.customer_updates, args.customer_closures)
        subscription_activity(cur, rng, args.plan_changes, args.suspensions, args.subscription_removals)
        conn.commit()

        for table in ("customer_master_hist", "subscriptions_hist"):
            cur.execute(f"SELECT hist_op, COUNT(*) FROM {table} GROUP BY hist_op ORDER BY hist_op")
            counts = ", ".join(f"{op}={n}" for op, n in cur.fetchall()) or "empty"
            print(f"[activity] {table}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
