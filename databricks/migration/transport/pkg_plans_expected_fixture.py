#!/usr/bin/env python3
"""Capture what Oracle pkg_plans does, from the fixture, as a JSON expectation file.

Unit p1-pkg-plans (U-21). The behavioural half of this unit's recon is an op diff over the
package entrypoints plus the rows the package writes into subscriptions, so something has to
run the Oracle package and record what it did. This script is that half, and only that half:
it reads Oracle and writes a JSON file. The Lakebase side is a separate program
(databricks/migration/lakebase/pkg_plans_behaviour_check.py) because one program may not both
read the source and write a target.

Everything here runs inside a transaction that is rolled back, so the fixture is left exactly
as it was found; the real Oracle estate is never touched by this script at all (it takes the
fixture DSN, and the fixture only).

usage: python3 pkg_plans_expected_fixture.py --out <file.json>
       run under databricks/migration/recon/with_oracle_fixture.py, which sets the env var.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path

import oracledb

oracledb.defaults.fetch_decimals = True

EFFECTIVE_ON = dt.datetime(2026, 6, 1)
ENTITLEMENT_ON = dt.datetime(2026, 6, 1)

PICK_TENANT = """
SELECT s.tenant_id, s.plan_id
  FROM subscriptions s
 WHERE s.ends_on IS NULL
   AND s.starts_on < :eff
 ORDER BY s.tenant_id
 FETCH FIRST 1 ROWS ONLY
"""

PICK_OTHER_PLAN = """
SELECT id FROM plans WHERE id <> :plan_id ORDER BY id FETCH FIRST 1 ROWS ONLY
"""

ROWS_FOR_TENANT = """
SELECT id, tenant_id, plan_id, starts_on, ends_on, status_cd, suspended_on
  FROM subscriptions WHERE tenant_id = :tenant_id ORDER BY id
"""

ENTITLEMENT = """
SELECT * FROM (
    SELECT t.id AS tenant_id, p.code AS plan_code,
           DECODE(p.tier_cd, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS tier,
           p.monthly_fee, p.included_units,
           DECODE(s.status_cd, 10, 'active', 20, 'suspended', 30, 'cancelled',
                  'UNKNOWN') AS subscription_status,
           GREATEST(s.starts_on, :p_on) AS effective_on
      FROM tenants t, subscriptions s, plans p
     WHERE s.tenant_id = t.id
       AND p.id (+) = s.plan_id
       AND t.id = :tenant_id
       AND s.starts_on <= :p_on
       AND (s.ends_on IS NULL OR s.ends_on >= :p_on)
     ORDER BY s.starts_on DESC
) WHERE ROWNUM <= 1
"""


def jsonable(value):
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        return str(value)
    return value


def fetch(cur, sql, **binds) -> list[dict]:
    cur.execute(sql, binds)
    cols = [d[0].lower() for d in cur.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn-secret", default="OW_TP_ORACLE_FIXTURE",
                    help="ENV VAR NAME holding the fixture connection JSON, never a value")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    raw = os.environ.get(args.dsn_secret)
    if not raw:
        raise SystemExit(f"{args.dsn_secret} is not set; run under with_oracle_fixture.py")
    cfg = json.loads(raw)

    conn = oracledb.connect(user=cfg["user"], password=cfg["password"],
                            dsn=f"{cfg['host']}:{cfg['port']}/{cfg['service']}")
    try:
        cur = conn.cursor()
        picked = fetch(cur, PICK_TENANT, eff=EFFECTIVE_ON)
        if not picked:
            raise SystemExit("no open subscription in the fixture to exercise")
        tenant_id = picked[0]["tenant_id"]
        current_plan = picked[0]["plan_id"]
        new_plan = fetch(cur, PICK_OTHER_PLAN, plan_id=current_plan)[0]["id"]

        out = {
            "source": "oracle-fixture",
            "tenant_id": tenant_id,
            "plan_id": new_plan,
            "effective_on": EFFECTIVE_ON.isoformat(sep=" ", timespec="seconds"),
            "entitlement_on": ENTITLEMENT_ON.isoformat(sep=" ", timespec="seconds"),
            "pre_rows": fetch(cur, ROWS_FOR_TENANT, tenant_id=tenant_id),
            "entitlement_pre": fetch(cur, ENTITLEMENT, tenant_id=tenant_id,
                                     p_on=ENTITLEMENT_ON),
        }

        cur.callproc("pkg_plans.sp_change_plan", [tenant_id, new_plan, EFFECTIVE_ON])
        out["post_rows"] = fetch(cur, ROWS_FOR_TENANT, tenant_id=tenant_id)
        out["entitlement_post"] = fetch(cur, ENTITLEMENT, tenant_id=tenant_id,
                                        p_on=ENTITLEMENT_ON)

        # TRG_SUB_NO_UNCANCEL: a cancelled row silently stays cancelled, no error raised.
        probe_id = "probe-uncancel-0000000000000000000"
        cur.execute(
            "INSERT INTO subscriptions (id, tenant_id, plan_id, starts_on, status_cd) "
            "VALUES (:1, :2, :3, :4, 30)",
            [probe_id, tenant_id, new_plan, EFFECTIVE_ON])
        probe = {"raised": None}
        try:
            cur.execute("UPDATE subscriptions SET status_cd = 10 WHERE id = :1", [probe_id])
        except Exception as exc:                                    # noqa: BLE001
            probe["raised"] = type(exc).__name__
        cur.execute("SELECT status_cd FROM subscriptions WHERE id = :1", [probe_id])
        probe["status_after_uncancel"] = int(cur.fetchone()[0])
        out["uncancel_probe"] = probe

        conn.rollback()     # the fixture is left exactly as found
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"captured pkg_plans expectation tenant={out['tenant_id']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
