#!/usr/bin/env python3
"""Replay the pkg_plans expectation against Lakebase and diff the behaviour.

Unit p1-pkg-plans (U-21), behavioural half. The Oracle side was captured by
databricks/migration/transport/pkg_plans_expected_fixture.py; this program only reads that
JSON and drives the target, so no single program both reads the source and writes a target.

The whole replay runs inside one transaction that is rolled back, so the shared wave branch
keeps the state the loader put there: no subscriptions row, and no billing_audit_log row from
the procedure's audit call, survives this check.

Compared, per the unit's behavioural contract:
  * the rows sp_assign_plan writes into billing.subscriptions vs the rows Oracle's
    sp_change_plan wrote (close-out date, preserved status, generated id, new row);
  * fn_plan_entitlements' projection before and after, vs Oracle fn_entitlement's;
  * trg_sub_no_uncancel: a cancelled row silently stays cancelled and no error is raised.

usage: python3 pkg_plans_behaviour_check.py --expected <file.json> --out <file.json>
       run under with_lakebase_dsn.py, which sets $OW_TP_LAKEBASE_DSN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

ROWS_FOR_TENANT = """
SELECT id, tenant_id, plan_id, starts_on, ends_on, status_cd, suspended_on
  FROM billing.subscriptions WHERE tenant_id = %s ORDER BY id
"""
ENTITLEMENT = """
SELECT tenant_id, plan_code, tier, monthly_fee, included_units, subscription_status,
       effective_on, last_tenant_id, last_plan_code
  FROM billing.fn_plan_entitlements(%s, %s)
"""
ENTITLEMENT_COLUMNS = ["tenant_id", "plan_code", "tier", "monthly_fee", "included_units",
                       "subscription_status", "effective_on"]
PROBE_ID = "probe-uncancel-0000000000000000000"


def scalar(value):
    """One engine-neutral form per value, so 49 and 49.00 and '10' compare as equal."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (int, Decimal, float)):
        return str(Decimal(str(value)).normalize())
    if isinstance(value, str):
        try:
            return str(Decimal(value).normalize())
        except InvalidOperation:
            return value
    return str(value)


def rows(cur, sql, *params) -> list[dict]:
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [{c: scalar(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def canon(records: list[dict], columns: list[str] | None = None) -> list[dict]:
    keys = columns or (list(records[0]) if records else [])
    return [{k: scalar(r.get(k)) for k in keys} for r in records]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")
    exp = json.loads(args.expected.read_text())
    tenant_id, plan_id = exp["tenant_id"], exp["plan_id"]
    eff = dt.datetime.fromisoformat(exp["effective_on"])
    ent_on = dt.datetime.fromisoformat(exp["entitlement_on"])

    checks: list[dict] = []
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            pre = rows(cur, ROWS_FOR_TENANT, tenant_id)
            checks.append({"name": "starting_rows_match_source",
                           "expected": canon(exp["pre_rows"]), "actual": pre})

            ent_pre = rows(cur, ENTITLEMENT, tenant_id, ent_on)
            checks.append({"name": "fn_plan_entitlements_before_change",
                           "expected": canon(exp["entitlement_pre"], ENTITLEMENT_COLUMNS),
                           "actual": canon(ent_pre, ENTITLEMENT_COLUMNS)})

            cur.execute("CALL billing.sp_assign_plan(%s, %s, %s)", (tenant_id, plan_id, eff))
            checks.append({"name": "sp_assign_plan_written_rows",
                           "expected": canon(exp["post_rows"]),
                           "actual": rows(cur, ROWS_FOR_TENANT, tenant_id)})

            ent_post = rows(cur, ENTITLEMENT, tenant_id, ent_on)
            checks.append({"name": "fn_plan_entitlements_after_change",
                           "expected": canon(exp["entitlement_post"], ENTITLEMENT_COLUMNS),
                           "actual": canon(ent_post, ENTITLEMENT_COLUMNS)})

            cur.execute(
                "INSERT INTO billing.subscriptions "
                "(id, tenant_id, plan_id, starts_on, status_cd) VALUES (%s, %s, %s, %s, 30)",
                (PROBE_ID, tenant_id, plan_id, eff))
            probe = {"raised": None}
            try:
                cur.execute("UPDATE billing.subscriptions SET status_cd = 10 WHERE id = %s",
                            (PROBE_ID,))
            except Exception as exc:                                # noqa: BLE001
                probe["raised"] = type(exc).__name__
            cur.execute("SELECT status_cd FROM billing.subscriptions WHERE id = %s",
                        (PROBE_ID,))
            probe["status_after_uncancel"] = int(cur.fetchone()[0])
            checks.append({"name": "trg_sub_no_uncancel",
                           "expected": exp["uncancel_probe"], "actual": probe})

            # The explicit form of the Oracle package globals (P1-D4), recorded not diffed:
            # Oracle hides them in package state the harness cannot read.
            package_state = {"last_tenant_id": ent_post[0]["last_tenant_id"],
                             "last_plan_code": ent_post[0]["last_plan_code"]} if ent_post else {}
        conn.rollback()

    for c in checks:
        c["match"] = c["expected"] == c["actual"]
    result = {"unit": "p1-pkg-plans", "mode": "fixture-expectation-replay",
              "tenant_id": tenant_id, "plan_id": plan_id,
              "effective_on": exp["effective_on"],
              "verdict": "PASS" if all(c["match"] for c in checks) else "FAIL",
              "package_state_returned": package_state, "checks": checks}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    for c in checks:
        print(f"{'ok  ' if c['match'] else 'FAIL'} {c['name']}")
    print(f"{result['verdict']} -> {args.out}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
