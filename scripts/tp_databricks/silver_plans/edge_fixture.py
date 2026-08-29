"""A generated bronze fixture for `ns=plans_edge`, and an independent model of what it implies.

Everything in this module is **generated fixture data**. It is not a migration of anything, it is
not customer activity, and it never existed in `OW_BILLING`: it is a synthetic namespace built so the
`pkg_plans` paths that this seed's real data happens to leave at zero — an unmapped `tier_cd`, tied
`starts_on`, a subscription whose plan row is absent, a plan present in the source but rejected by
the run, the strict-`<` overlap, a cancelled row visited by the close-out, the stale package-global
mismatch, and a re-applied change whose `f_md5_uuid` id already exists — are actually exercised
somewhere before this unit ships. The wave-1 `bronze_hist` precedent is the one followed here:
generated activity is fine as long as every report says so in plain words, which is why the fixture
carries `_source_table = 'generated-fixture'` on every row it writes.

Isolation: every write is `ns = 'plans_edge'`, both in `ow_tp.bronze.*` and in the four silver
targets this unit owns. No statement here touches another namespace, and no statement is table-wide:
the fixture's own reset deletes exactly the rows carrying its own `ns` (D-28's scoped-delete rule).

The `expectations()` model is a deliberately separate re-expression of `02_pkg_plans.sql` in plain
Python — no Spark, no SQL — so the notebook's SQL is compared against something derived
independently from the source's semantics rather than against itself. Oracle holds no copy of this
fixture (seeding one would mean mutating the source), so for this namespace the model is the declared
side of the comparison, and the recon report says exactly that.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
from typing import Any

NS = "plans_edge"
ORIGIN = "generated-fixture"
ENTITLEMENT_ON = "2026-02-28"
CHANGE_EFFECTIVE_ON = "2026-03-01"

ACTIVE_CD, SUSPENDED_CD, CANCELLED_CD = 10, 20, 30
TIER_MAP = {1: "starter", 2: "growth", 3: "scale"}
TIER_DEFAULT = "UNKNOWN"
STATUS_MAP = {10: "active", 20: "suspended", 30: "cancelled"}
ABSENT_PLAN_ID = "edge-plan-absent"
FILLER_TENANTS = range(13, 75)


def md5_uuid(text: str) -> str:
    """`pkg_ow_util.f_md5_uuid`: lower(md5(input)) sliced 8-4-4-4-12 (D-14)."""
    h = hashlib.md5(text.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _plans() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        # code, tier_cd, fee, units, rate, active_yn — the first six carry the paths under test.
        {"id": "edge-plan-01", "code": "EDGE-A", "tier_cd": 1, "monthly_fee": "10.00",
         "included_units": "1000", "overage_rate": "0.010000", "active_yn": "Y"},
        {"id": "edge-plan-02", "code": "EDGE-B", "tier_cd": 2, "monthly_fee": "20.00",
         "included_units": "2000", "overage_rate": "0.020000", "active_yn": "Y"},
        # An unmapped and a NULL tier_cd: both are the literal 'UNKNOWN', neither is a reject.
        {"id": "edge-plan-03", "code": "EDGE-C", "tier_cd": None, "monthly_fee": "30.00",
         "included_units": "3000", "overage_rate": "0.030000", "active_yn": "Y"},
        {"id": "edge-plan-04", "code": "EDGE-D", "tier_cd": 9, "monthly_fee": "40.00",
         "included_units": "4000", "overage_rate": "0.040000", "active_yn": "Y"},
        # NULL active_yn: NVL(active_yn,'N') = 'Y' makes it inactive, so it loads and is unlisted.
        {"id": "edge-plan-05", "code": "EDGE-E", "tier_cd": 1, "monthly_fee": "50.00",
         "included_units": "5000", "overage_rate": "0.050000", "active_yn": None},
        # A plan that is present in the source population and rejected by the run (KEY_NULL on
        # code): its dependent subscription must be rejected too, not null-extended like D-18's
        # genuinely absent plan.
        {"id": "edge-plan-06", "code": None, "tier_cd": 2, "monthly_fee": "60.00",
         "included_units": "6000", "overage_rate": "0.060000", "active_yn": "Y"},
    ]
    for i in range(7, 27):
        rows.append(
            {
                "id": f"edge-plan-{i:02d}",
                "code": f"EDGE-F{i:02d}",
                "tier_cd": (i % 3) + 1,
                "monthly_fee": f"{100 + i}.00",
                "included_units": f"{1000 * i}",
                "overage_rate": "0.001000",
                "active_yn": "Y",
            }
        )
    return rows


def _tenants() -> list[dict[str, Any]]:
    ids = [f"edge-tenant-{i:02d}" for i in list(range(1, 13)) + list(FILLER_TENANTS)]
    return [
        {
            "id": t,
            "name": f"generated fixture tenant {t.rsplit('-', 1)[1]}",
            "tax_exempt_yn": "N",
            "status_cd": ACTIVE_CD,
        }
        for t in ids
    ]


COLLIDING_ID = md5_uuid(f"edge-tenant-09edge-plan-02{CHANGE_EFFECTIVE_ON}")


def _subscriptions() -> list[dict[str, Any]]:
    def sub(sid, tenant, plan, starts, ends=None, status=ACTIVE_CD, suspended=None):
        return {
            "id": sid,
            "tenant_id": tenant,
            "plan_id": plan,
            "starts_on": starts,
            "ends_on": ends,
            "status_cd": status,
            "suspended_on": suspended,
        }

    rows = [
        # Two subscriptions for one tenant with identical starts_on: the ROWNUM tie.
        sub("edge-sub-tie-a", "edge-tenant-02", "edge-plan-01", "2026-01-01"),
        sub("edge-sub-tie-b", "edge-tenant-02", "edge-plan-02", "2026-01-01"),
        # A subscription whose plan_id has no PLANS row at all: D-18 keeps it and null-extends.
        sub("edge-sub-missing-plan", "edge-tenant-03", ABSENT_PLAN_ID, "2026-01-01"),
        # An open subscription starting exactly on the effective date: the cursor's strict `<`
        # never sees it, so it overlaps the subscription the change inserts.
        sub("edge-sub-on-effective", "edge-tenant-04", "edge-plan-01", CHANGE_EFFECTIVE_ON),
        sub("edge-sub-t04-cover", "edge-tenant-04", "edge-plan-01", "2026-01-01"),
        # An open cancelled subscription: DECODE(status_cd, 30, 30, 10) must leave it cancelled.
        sub("edge-sub-cancelled", "edge-tenant-05", "edge-plan-01", "2026-01-01",
            status=CANCELLED_CD),
        # An open suspended subscription: the close-out reactivates it to 10, which is parity.
        sub("edge-sub-suspended", "edge-tenant-06", "edge-plan-01", "2026-01-01",
            status=SUSPENDED_CD, suspended="2026-02-10"),
        # A covered tenant immediately followed, in the package's iteration order, by one with no
        # covering subscription: g_last_plan_code keeps this tenant's code for the next one.
        sub("edge-sub-t07-cover", "edge-tenant-07", "edge-plan-02", "2026-01-01"),
        sub("edge-sub-t08-ended", "edge-tenant-08", "edge-plan-01", "2025-06-01",
            ends="2026-01-15"),
        # A request whose derived f_md5_uuid id already exists: the source would close the
        # close-outs and then raise ORA-00001; this port converges on the existing row instead.
        sub("edge-sub-t09-cover", "edge-tenant-09", "edge-plan-01", "2026-01-01"),
        sub(COLLIDING_ID, "edge-tenant-09", "edge-plan-02", CHANGE_EFFECTIVE_ON),
        sub("edge-sub-t10-cover", "edge-tenant-10", "edge-plan-01", "2026-01-01"),
        sub("edge-sub-t11-cover", "edge-tenant-11", "edge-plan-01", "2026-01-01"),
        # The dependent row of the plan this run rejects.
        sub("edge-sub-on-rejected-plan", "edge-tenant-12", "edge-plan-06", "2026-01-01"),
    ]
    for i in FILLER_TENANTS:
        rows.append(
            sub(
                f"edge-sub-f{i:02d}",
                f"edge-tenant-{i:02d}",
                "edge-plan-01" if i % 2 else "edge-plan-02",
                "2026-01-01",
            )
        )
    return rows


# One request per tenant per run, which is what the notebook accepts: two sp_change_plan calls for
# one tenant are sequential invocations, not a set.
APPLIED_REQUESTS: list[dict[str, Any]] = [
    {"tenant_id": "edge-tenant-04", "plan_id": "edge-plan-02",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-strict-less-than-overlap"},
    {"tenant_id": "edge-tenant-05", "plan_id": "edge-plan-02",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-cancelled-stays-cancelled"},
    {"tenant_id": "edge-tenant-06", "plan_id": "edge-plan-02",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-suspended-becomes-active"},
    {"tenant_id": "edge-tenant-07", "plan_id": "edge-plan-03",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-plain-change"},
    {"tenant_id": "edge-tenant-09", "plan_id": "edge-plan-02",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-reapply-id-collision"},
    {"tenant_id": "edge-tenant-10", "plan_id": "edge-plan-06",
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-request-on-a-rejected-plan"},
    {"tenant_id": "edge-tenant-11", "plan_id": ABSENT_PLAN_ID,
     "effective_on": CHANGE_EFFECTIVE_ON, "label": "edge-request-on-an-absent-plan"},
]

PLANS = _plans()
TENANTS = _tenants()
SUBSCRIPTIONS = _subscriptions()

PROVENANCE = {
    "namespace": NS,
    "kind": "generated fixture, not migrated source data",
    "generator": "scripts/tp_databricks/silver_plans/edge_fixture.py",
    "bronze_rows_written": {
        "ow_tp.bronze.plans": len(PLANS),
        "ow_tp.bronze.tenants": len(TENANTS),
        "ow_tp.bronze.subscriptions": len(SUBSCRIPTIONS),
    },
    "_source_table_stamped_on_every_row": ORIGIN,
    "statement": "Every row in ns=plans_edge was generated by this file for the purpose of "
    "exercising pkg_plans paths that the demo seed leaves at zero. None of it is customer "
    "activity, none of it exists in OW_BILLING, and no OW_BILLING row was created, changed or "
    "deleted to produce it. The tenants, plans and subscriptions are synthetic identifiers "
    "(edge-tenant-*, edge-plan-*, edge-sub-*) chosen so they cannot be mistaken for seeded data.",
    "oracle_side_of_the_comparison": "Oracle holds no copy of this fixture, because seeding one "
    "would mean mutating the source. The declared side for this namespace is the independent "
    "Python re-expression of 02_pkg_plans.sql in expectations(), evaluated on the fixture; the "
    "live Oracle comparison is the ns=demo evidence.",
    "requests_applied": APPLIED_REQUESTS,
}


# -- writes --------------------------------------------------------------------


def _lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _ts(value: str | None) -> str:
    return "NULL" if value is None else f"TIMESTAMP'{value} 00:00:00'"


def seed_bronze(dbx: Any) -> dict[str, int]:
    """Replace `ns=plans_edge` in the three bronze inputs with the generated fixture.

    The delete is scoped to this namespace, which holds nothing but rows this file wrote.
    """
    written: dict[str, int] = {}
    for table in ("plans", "subscriptions", "tenants"):
        dbx.sql(f"DELETE FROM ow_tp.bronze.{table} WHERE ns = {_lit(NS)}")

    values = ", ".join(
        f"({_lit(p['id'])}, {_lit(p['code'])}, {_lit(p['tier_cd'])}, "
        f"CAST({_lit(p['monthly_fee'])} AS DECIMAL(14,2)), "
        f"CAST({_lit(p['included_units'])} AS DECIMAL(38,0)), "
        f"CAST({_lit(p['overage_rate'])} AS DECIMAL(12,6)), {_lit(p['active_yn'])}, "
        f"{_lit(NS)}, {_lit(ORIGIN)}, current_timestamp())"
        for p in PLANS
    )
    dbx.sql(
        "INSERT INTO ow_tp.bronze.plans (id, code, tier_cd, monthly_fee, included_units, "
        f"overage_rate, active_yn, ns, _source_table, _loaded_at) VALUES {values}"
    )
    written["ow_tp.bronze.plans"] = len(PLANS)

    values = ", ".join(
        f"({_lit(t['id'])}, {_lit(t['name'])}, {_lit(t['tax_exempt_yn'])}, "
        f"{_lit(t['status_cd'])}, {_lit(NS)}, {_lit(ORIGIN)}, current_timestamp())"
        for t in TENANTS
    )
    dbx.sql(
        "INSERT INTO ow_tp.bronze.tenants (id, name, tax_exempt_yn, status_cd, ns, "
        f"_source_table, _loaded_at) VALUES {values}"
    )
    written["ow_tp.bronze.tenants"] = len(TENANTS)

    values = ", ".join(
        f"({_lit(s['id'])}, {_lit(s['tenant_id'])}, {_lit(s['plan_id'])}, "
        f"{_ts(s['starts_on'])}, {_ts(s['ends_on'])}, {_lit(s['status_cd'])}, "
        f"{_ts(s['suspended_on'])}, {_lit(NS)}, {_lit(ORIGIN)}, current_timestamp())"
        for s in SUBSCRIPTIONS
    )
    dbx.sql(
        "INSERT INTO ow_tp.bronze.subscriptions (id, tenant_id, plan_id, starts_on, ends_on, "
        f"status_cd, suspended_on, ns, _source_table, _loaded_at) VALUES {values}"
    )
    written["ow_tp.bronze.subscriptions"] = len(SUBSCRIPTIONS)
    return written


def reset_targets(dbx: Any, catalog: str = "ow_tp", schema: str = "silver") -> dict[str, int]:
    """Drop this namespace's rows from the four owned targets, so the next run is a cold load.

    Scoped to `ns=plans_edge` and therefore to rows this unit itself produced in a namespace it
    generated: no other namespace is read or written, and nothing is table-wide (D-28).
    """
    removed: dict[str, int] = {}
    for table in ("plans", "subscriptions", "entitlements", "quarantine_silver_plans"):
        before = int(
            dbx.sql(f"SELECT count(*) FROM {catalog}.{schema}.{table} WHERE ns = {_lit(NS)}")[0][0]
        )
        if before:
            dbx.sql(f"DELETE FROM {catalog}.{schema}.{table} WHERE ns = {_lit(NS)}")
        removed[f"{catalog}.{schema}.{table}"] = before
    return removed


# -- the independent model -----------------------------------------------------


def _d(value: str | None) -> decimal.Decimal | None:
    return None if value is None else decimal.Decimal(value)


def _date(value: str | None) -> dt.date | None:
    return None if value is None else dt.date.fromisoformat(value)


def expectations() -> dict[str, Any]:
    """What `02_pkg_plans.sql` implies for this fixture, re-derived in plain Python.

    Written from the source text rather than from the notebook: the active filter's `NVL`, the
    tier `DECODE`'s default, the two entitlement predicates, the `(+)` null-extension, the pinned
    tie-break, the strict `<` close-out cursor with its `DECODE(status_cd, 30, 30, 10)`, and the
    `f_md5_uuid` id of the row the `EXECUTE IMMEDIATE` INSERT would add.
    """
    as_of = _date(ENTITLEMENT_ON)
    eff = _date(CHANGE_EFFECTIVE_ON)

    # Rejections this run must make, by the notebook's own closed reason set.
    rejected_plan_ids = {p["id"] for p in PLANS if p["id"] is None or p["code"] is None}
    loaded_plans = [p for p in PLANS if p["id"] not in rejected_plan_ids]
    plans_by_id = {p["id"]: p for p in loaded_plans}
    source_plan_ids = {p["id"] for p in PLANS}

    def tier(plan: dict[str, Any]) -> str:
        return TIER_MAP.get(plan["tier_cd"], TIER_DEFAULT)

    listed = sorted(
        (p for p in loaded_plans if (p["active_yn"] or "N") == "Y"),
        key=lambda p: (_d(p["monthly_fee"]), p["code"]),
    )
    fn_list_plans = [
        {
            "list_seq": i + 1,
            "code": p["code"],
            "tier": tier(p),
            "monthly_fee": p["monthly_fee"],
            "included_units": p["included_units"],
            "plan_id": p["id"],
        }
        for i, p in enumerate(listed)
    ]

    rejected_subs = {
        s["id"]: "FK_ORPHAN"
        for s in SUBSCRIPTIONS
        if s["plan_id"] in rejected_plan_ids
    }
    loaded_subs = [s for s in SUBSCRIPTIONS if s["id"] not in rejected_subs]

    # The returned cursor, per tenant: starts_on <= as_of and (ends_on IS NULL OR ends_on >=
    # as_of), plans outer-joined, ORDER BY starts_on DESC with the pinned id DESC tie-break.
    def covered(rows: list[dict[str, Any]], sentinel: bool) -> list[dict[str, Any]]:
        out = []
        for s in rows:
            if _date(s["starts_on"]) > as_of:
                continue
            ends = _date(s["ends_on"])
            if sentinel:
                if (ends or dt.date(2099, 12, 31)) < as_of:
                    continue
            elif ends is not None and ends < as_of:
                continue
            out.append(s)
        return out

    entitlements: dict[str, dict[str, Any]] = {}
    ties = 0
    multi = 0
    null_extended = 0
    for t in TENANTS:
        cand = covered([s for s in loaded_subs if s["tenant_id"] == t["id"]], sentinel=False)
        if not cand:
            continue
        cand.sort(key=lambda s: (s["starts_on"], s["id"]), reverse=True)
        pick = cand[0]
        if len(cand) > 1:
            multi += 1
        if sum(1 for s in cand if s["starts_on"] == pick["starts_on"]) > 1:
            ties += 1
        plan = plans_by_id.get(pick["plan_id"])
        if plan is None:
            null_extended += 1
        entitlements[t["id"]] = {
            "subscription_id": pick["id"],
            "plan_id": pick["plan_id"],
            "plan_code": plan["code"] if plan else None,
            "tier": tier(plan) if plan else None,
            "monthly_fee": plan["monthly_fee"] if plan else None,
            "included_units": plan["included_units"] if plan else None,
            "status_cd": pick["status_cd"],
            "subscription_status": STATUS_MAP.get(pick["status_cd"], "UNKNOWN"),
            "plan_null_extended": plan is None,
            "candidate_rows": len(cand),
        }

    # The stale package-global walk, in the declared tenant order.
    stale_mismatch = 0
    uncovered_sentinel = 0
    matched_before = False
    for t in sorted(TENANTS, key=lambda t: t["id"]):
        cand = covered([s for s in loaded_subs if s["tenant_id"] == t["id"]], sentinel=True)
        if cand:
            matched_before = True
        else:
            # g_last_tenant_id is this tenant, g_last_plan_code is still a predecessor's.
            uncovered_sentinel += 1
            if matched_before:
                stale_mismatch += 1

    # The applied requests, judged the way the notebook judges them.
    tenant_ids = {t["id"] for t in TENANTS}
    requests: list[dict[str, Any]] = []
    for r in APPLIED_REQUESTS:
        reason = None
        if r["tenant_id"] not in tenant_ids:
            reason = "FK_ORPHAN"
        elif r["plan_id"] not in source_plan_ids or r["plan_id"] in rejected_plan_ids:
            reason = "FK_ORPHAN"
        requests.append(
            {
                **r,
                "new_subscription_id": md5_uuid(
                    f"{r['tenant_id']}{r['plan_id']}{r['effective_on']}"
                ),
                "quarantine_reason": reason,
            }
        )
    accepted = [r for r in requests if r["quarantine_reason"] is None]
    accepted_tenants = {r["tenant_id"] for r in accepted}
    existing_ids = {s["id"] for s in SUBSCRIPTIONS}
    collisions = [r for r in accepted if r["new_subscription_id"] in existing_ids]

    # The close-out cursor: open rows with starts_on < effective_on, strictly.
    closed, flips, cancelled_visited, overlaps = [], 0, 0, 0
    for s in loaded_subs:
        if s["tenant_id"] not in accepted_tenants or s["ends_on"] is not None:
            continue
        if _date(s["starts_on"]) < eff:
            closed.append(s)
            if s["status_cd"] == CANCELLED_CD:
                cancelled_visited += 1
            elif s["status_cd"] == SUSPENDED_CD:
                flips += 1
        else:
            overlaps += 1

    # The SUBSCRIPTIONS end state the accepted requests leave: closed rows carry
    # ends_on = effective_on - 1 and DECODE(status_cd, 30, 30, 10), an accepted request whose id is
    # already a bronze row inserts nothing, and every other row keeps its migrated state.
    closed_ids = {s["id"] for s in closed}
    end_state: dict[str, dict[str, Any]] = {}
    for s in loaded_subs:
        ends, status = s["ends_on"], s["status_cd"]
        if s["id"] in closed_ids:
            ends = (eff - dt.timedelta(days=1)).isoformat()
            status = CANCELLED_CD if s["status_cd"] == CANCELLED_CD else ACTIVE_CD
        end_state[s["id"]] = {
            "tenant_id": s["tenant_id"],
            "plan_id": s["plan_id"],
            "starts_on": f"{s['starts_on']} 00:00:00",
            "ends_on": None if ends is None else f"{ends} 00:00:00",
            "status_cd": status,
        }
    for r in accepted:
        if r["new_subscription_id"] in existing_ids:
            continue
        end_state[r["new_subscription_id"]] = {
            "tenant_id": r["tenant_id"],
            "plan_id": r["plan_id"],
            "starts_on": f"{r['effective_on']} 00:00:00",
            "ends_on": None,
            "status_cd": ACTIVE_CD,
        }

    subs_source = len(SUBSCRIPTIONS) + len(requests)
    subs_rejected = len(rejected_subs) + (len(requests) - len(accepted))
    ent_source = len(entitlements) + sum(
        1
        for t in TENANTS
        if t["id"] not in entitlements
        and covered([s for s in SUBSCRIPTIONS if s["tenant_id"] == t["id"]], sentinel=False)
    )

    def pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 4) if den else 0.0

    return {
        "fn_list_plans": fn_list_plans,
        "entitlements": entitlements,
        "requests": requests,
        "subscriptions_end_state": end_state,
        "populations": {
            "plans_source_rows": len(PLANS),
            "plans_rejected_rows": len(rejected_plan_ids),
            "unknown_tier_plans": sum(1 for p in loaded_plans if tier(p) == TIER_DEFAULT),
            "inactive_plans": sum(1 for p in loaded_plans if (p["active_yn"] or "N") != "Y"),
            "null_active_yn_plans": sum(1 for p in loaded_plans if p["active_yn"] is None),
            "listed_by_fn_list_plans": len(listed),
            "subscriptions_source_rows": len(SUBSCRIPTIONS),
            "subscriptions_rejected_rows": len(rejected_subs),
            "rows_whose_plan_is_absent_from_the_source": sum(
                1 for s in loaded_subs if s["plan_id"] not in source_plan_ids
            ),
            "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run": len(rejected_subs),
            "entitlement_rows": len(entitlements),
            "entitlement_source_rows": ent_source,
            "entitlement_rejected_rows": ent_source - len(entitlements),
            "plan_null_extended_rows": null_extended,
            "rows_with_tied_starts_on": ties,
            "rows_with_more_than_one_candidate": multi,
            "tenants_with_no_covering_subscription_sentinel_predicate": uncovered_sentinel,
            "tenants_carrying_a_stale_predecessor_plan_code": stale_mismatch,
            "requests_applied": len(requests),
            "requests_accepted": len(accepted),
            "requests_rejected": len(requests) - len(accepted),
            "subscriptions_closed_by_the_loop": len(closed),
            "suspended_to_active_flips": flips,
            "cancelled_subscriptions_visited": cancelled_visited,
            "cancelled_preserved": cancelled_visited,
            "open_subscriptions_left_overlapping_by_the_strict_less_than": overlaps,
            "new_ids_already_present_in_the_source": len(collisions),
            "new_subscriptions": len(accepted) - len(collisions),
        },
        "halt_rates_pct": {
            "plans": pct(len(rejected_plan_ids), len(PLANS)),
            "subscriptions": pct(subs_rejected, subs_source),
            "entitlements": pct(ent_source - len(entitlements), ent_source),
        },
        "quarantine_reasons": {
            "plans": {"edge-plan-06": "KEY_NULL"},
            "subscriptions": rejected_subs,
            "requests": {
                r["tenant_id"]: r["quarantine_reason"]
                for r in requests
                if r["quarantine_reason"]
            },
        },
    }
