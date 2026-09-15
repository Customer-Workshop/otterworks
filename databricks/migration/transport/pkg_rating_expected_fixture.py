#!/usr/bin/env python3
"""Capture what Oracle pkg_rating does, from the fixture, as a JSON expectation file.

Unit p1-pkg-rating (U-22). No op can compare a live Oracle package entrypoint with the
converted one (P1-D9: that would need an Oracle view over the package and the source is
read-only), so the behavioural half of this unit's evidence is a fixture run-diff: run the
legacy package and the converted one over the same fixture state and diff what each returns
and writes. This script is the Oracle half, and only that half: it reads Oracle and writes a
JSON file. The Lakebase half is a separate program
(databricks/migration/lakebase/pkg_rating_behaviour_check.py), so no single program both
reads the source and writes a target.

Everything runs inside a transaction that is rolled back, so the fixture is left exactly as
it was found; the real Oracle estate is never touched by this script at all (it takes the
fixture DSN, and the fixture only).

usage: python3 pkg_rating_expected_fixture.py --out <file.json>
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

PERIOD_START = dt.datetime(2026, 2, 1)
PERIOD_END = dt.datetime(2026, 2, 28)

# Four scenarios over the seeded estate, chosen for the branches they reach:
#   rollover   - the only tenant with prior rating periods inside the three-month window
#   suspended  - the only status-20 subscription with a suspended_on inside the period
#   tier_two   - the busiest tenant, well past the 101-unit tier break
#   no_subscription - an id with no subscription at all: the NO_DATA_FOUND -> NULL path
SCENARIOS = [
    {"name": "rollover", "tenant_id": "00000000-0000-0000-0000-000000000001", "finalize": True},
    {"name": "suspended", "tenant_id": "00000000-0000-0000-0000-000000000002", "finalize": True},
    {"name": "tier_two", "tenant_id": "9cc3e480-8bac-946d-1475-6bdaaa87a386", "finalize": True},
    {"name": "no_subscription", "tenant_id": "no-such-tenant", "finalize": False},
]

RATING_PERIODS = """
SELECT id, tenant_id, period_start, period_end
  FROM rating_periods WHERE tenant_id = :tenant_id ORDER BY period_start
"""

RATING_RESULTS = """
SELECT rr.id, rr.period_id, rr.subscription_id, rr.used_units, rr.quota_units,
       rr.rollover_units, rr.billable_units, rr.overage_amount, rr.created_at
  FROM rating_results rr, rating_periods rp
 WHERE rp.id = rr.period_id AND rp.tenant_id = :tenant_id
 ORDER BY rp.period_start
"""


def jsonable(value):
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def rows(cur) -> list[dict]:
    cols = [d[0].lower() for d in cur.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def fetch(cur, sql, **binds) -> list[dict]:
    cur.execute(sql, binds)
    return rows(cur)


def refcursor(cur, member: str, tenant_id: str) -> list[dict]:
    out = cur.callfunc(f"pkg_rating.{member}", oracledb.CURSOR,
                       [tenant_id, PERIOD_START, PERIOD_END])
    return rows(out)


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
    out = {
        "source": "oracle-fixture",
        "period_start": PERIOD_START.isoformat(sep=" ", timespec="seconds"),
        "period_end": PERIOD_END.isoformat(sep=" ", timespec="seconds"),
        "scenarios": {},
    }
    try:
        cur = conn.cursor()
        for scenario in SCENARIOS:
            tenant_id = scenario["tenant_id"]
            captured = {
                "tenant_id": tenant_id,
                "usage_rating": refcursor(cur, "fn_usage_rating", tenant_id),
                "usage_summary": refcursor(cur, "fn_usage_summary", tenant_id),
                "rating_periods_pre": fetch(cur, RATING_PERIODS, tenant_id=tenant_id),
                "rating_results_pre": fetch(cur, RATING_RESULTS, tenant_id=tenant_id),
            }
            if scenario["finalize"]:
                cur.callproc("pkg_rating.sp_finalize_rating",
                             [tenant_id, PERIOD_START, PERIOD_END])
                # g_overage_amount is the package global pkg_invoicing reads next. On
                # Lakebase it is a billing.rating_state row (P1-D4); here it still has to be
                # read out of package state, which only PL/SQL can see.
                state = cur.var(oracledb.DB_TYPE_NUMBER)
                cur.execute("BEGIN :v := pkg_rating.g_overage_amount; END;", v=state)
                # A bind variable comes back as a float, unlike a fetched column; round-trip
                # through the literal text so the money value stays exact.
                value = state.getvalue()
                captured["overage_state"] = (None if value is None
                                             else jsonable(Decimal(str(value))))
                captured["rating_periods_post"] = fetch(cur, RATING_PERIODS,
                                                        tenant_id=tenant_id)
                captured["rating_results_post"] = fetch(cur, RATING_RESULTS,
                                                        tenant_id=tenant_id)
                # Second finalize of the same period: the DUP_VAL_ON_INDEX branches.
                cur.callproc("pkg_rating.sp_finalize_rating",
                             [tenant_id, PERIOD_START, PERIOD_END])
                captured["rating_periods_rerun"] = fetch(cur, RATING_PERIODS,
                                                         tenant_id=tenant_id)
                captured["rating_results_rerun"] = fetch(cur, RATING_RESULTS,
                                                         tenant_id=tenant_id)
            out["scenarios"][scenario["name"]] = captured
            conn.rollback()     # each scenario starts from the state the fixture shipped

        conn.rollback()         # the fixture is left exactly as found
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"captured pkg_rating expectation for {len(out['scenarios'])} scenarios -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
