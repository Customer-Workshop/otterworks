"""Generated bronze fixtures for this unit's declared scratch namespaces, and a model of each.

Everything here is **generated fixture data**. It is not a migration of anything, it is not customer
activity, and no row of it exists in `OW_BILLING`: every row carries `_source_table =
'generated-fixture'` so no report can present it as source history. Three namespaces are built:

* `dunning_edge` — the paths the `ns=demo` seed leaves at zero: an invoice whose tenant row is
  missing and is kept by the outer join (D-18), an unmapped tenant status that decodes to the literal
  `'UNKNOWN'`, an invoice issued on `p_as_of` itself (overdue by the driver but not by
  `fn_overdue_accounts`' strict `<`), an invoice issued exactly on `TRUNC(p_as_of) - 14` (the
  inclusive edge of the sweep), subscriptions left alone at `20` and at `30` beside one that is
  suspended, a tenant already carrying a suspension notification on the same `p_as_of` (the source's
  `NOT EXISTS` suppression) and one carrying it on a different date (the multi-date exposure), plus
  every reachable quarantine reason — with enough clean rows that no population crosses the 5% halt.
* `dunning_halt` — an attempt population that is deliberately over the halt threshold, run once to
  show the halt fires and that the rejected rows are already in the ledger when it does.
* `dunning_t002` / `dunning_t003` — replays of `ns=demo`'s own migrated ingest rows under a different
  `ns`, so `DUNNING-002` (`as_of = 2026-02-14`) and `DUNNING-003` (`as_of = 2026-02-17`) can be run
  on their own `p_as_of` without a second write into `ns=demo`. Their rows are copies of bronze rows,
  declared as copies, and they are never presented as a separate source population.

`ow_tp.silver.subscriptions` is written by `silver_plans` and this unit may not INSERT into it, not
even in a scratch namespace. The fixture therefore generates *bronze* subscriptions and the
namespace's silver rows are produced by running the merged `ow_tp_silver_plans` notebook on it — the
table's own writer — before this unit's job runs. Invoices are generated in `ow_tp.bronze.invoices`
for the same reason (`ow_tp.silver.invoices` is `silver_invoicing`'s), which is why the fixture
namespaces run with `invoice_source = bronze`.

`expectations()` is a deliberately separate re-expression of `05_pkg_dunning.sql` in plain Python — no
Spark, no SQL — so the notebook's SQL is compared against something derived from the source's
semantics rather than against itself. Oracle holds no copy of these namespaces (seeding one would
mean mutating the source), so for them the model is the declared side of the comparison and the recon
report says exactly that.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
from typing import Any

NS_EDGE = "dunning_edge"
NS_HALT = "dunning_halt"
ORIGIN = "generated-fixture"
AS_OF = "2026-02-28"
CUTOFF_DAYS = 14

ACTIVE_CD, SUSPENDED_CD, CANCELLED_CD = 10, 20, 30
OVERDUE_CD, PAID_CD = 40, 30
ATTEMPT_SCHEDULED_CD, ATTEMPT_SENT_CD = 10, 20
KIND_INVOICE_CD, KIND_SUSPENSION_CD = 1, 3
UNMAPPED_TENANT_CD = 99
UNMAPPED_ATTEMPT_CD = 77
UNMAPPED_KIND_CD = 88

# The duplicated tenant id. It deliberately carries no subscription: `ow_tp.silver.subscriptions` is
# produced for this namespace by the merged `ow_tp_silver_plans` notebook, and a duplicated tenant id
# that also has a subscription fans its entitlement cursor out to two rows per tenant, which that
# unit's own accounting rejects. The duplicate is an ingest defect on TENANTS, so it is placed on a
# tenant outside the subscription population rather than by changing another unit's notebook.
DUP_TENANT = "edge-t-50"
ABSENT_TENANT = "edge-t-absent"
ABSENT_INVOICE = "edge-i-absent"
EDGE_PLAN = "edge-plan-dun"

# Filler sizes. They exist only so that each population's rejects stay under the 5% halt: the halt
# must fire on a real breach, never on the fixture's own shape.
FILLER_TENANTS = range(7, 81)
FILLER_INVOICES = range(100, 250)
FILLER_ATTEMPTS = 120
FILLER_NOTIFICATIONS = 60
FILLER_SUBSCRIPTIONS = range(7, 27)


def md5_uuid(text: str) -> str:
    """`pkg_ow_util.f_md5_uuid`: lower(md5(input)) sliced 8-4-4-4-12 (D-14)."""
    h = hashlib.md5(text.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _date(text: str) -> dt.date:
    return dt.datetime.strptime(text, "%Y-%m-%d").date()


def _money(text: str) -> str:
    return str(decimal.Decimal(text).quantize(decimal.Decimal("0.01")))


def day_abbr(day: dt.date) -> str:
    """The source's own English `TO_CHAR(d,'DY','NLS_DATE_LANGUAGE=ENGLISH')` abbreviations."""
    return ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][day.weekday()]


def weekend_shift(day: dt.date) -> int:
    return {"SAT": 2, "SUN": 1}.get(day_abbr(day), 0)


# -- edge namespace rows -------------------------------------------------------


def _edge_tenants() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        # swept: active, an invoice inside the inclusive 14-day cut, three subscriptions
        {"id": "edge-t-01", "status_cd": ACTIVE_CD},
        # a candidate the sweep skips because it is not status_cd = 10 (IF v_active > 0)
        {"id": "edge-t-02", "status_cd": SUSPENDED_CD},
        # an unmapped status: DECODE gives the literal 'UNKNOWN', and the row is CODE_UNKNOWN
        {"id": "edge-t-03", "status_cd": UNMAPPED_TENANT_CD},
        # active, but its only overdue invoice was issued on p_as_of itself
        {"id": "edge-t-04", "status_cd": ACTIVE_CD},
        # active, overdue but inside 14 days, and already notified on a *different* date
        {"id": "edge-t-05", "status_cd": ACTIVE_CD},
        # swept, but its suspension notification for this p_as_of already exists
        {"id": "edge-t-06", "status_cd": ACTIVE_CD},
    ]
    rows += [{"id": f"edge-t-{i:02d}", "status_cd": ACTIVE_CD} for i in FILLER_TENANTS]
    out = [
        {
            "id": r["id"],
            "name": f"Edge Tenant {r['id']}",
            "tax_exempt_yn": "N",
            "status_cd": r["status_cd"],
        }
        for r in rows
    ]
    # A duplicated tenant id: impossible under the source primary key, so it can only be an ingest
    # defect. KEY_DUPLICATE, and deduplicated before the outer join rather than allowed to fan out.
    out.append(
        {"id": DUP_TENANT, "name": f"Edge Tenant {DUP_TENANT} (duplicate)", "tax_exempt_yn": "N",
         "status_cd": ACTIVE_CD}
    )
    return out


def _edge_invoices() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {"id": "edge-i-01", "tenant_id": "edge-t-01", "issued": "2026-02-01", "total": "100.00",
         "status_cd": OVERDUE_CD},
        {"id": "edge-i-02", "tenant_id": "edge-t-02", "issued": "2026-02-02", "total": "200.00",
         "status_cd": OVERDUE_CD},
        {"id": "edge-i-03", "tenant_id": "edge-t-03", "issued": "2026-02-03", "total": "300.00",
         "status_cd": OVERDUE_CD},
        # issued on p_as_of: in the schedule cursor (no date filter) but not overdue by the
        # function's strict TO_CHAR(...) < TO_CHAR(...) comparison, and outside the sweep's cut
        {"id": "edge-i-04", "tenant_id": "edge-t-04", "issued": AS_OF, "total": "400.00",
         "status_cd": OVERDUE_CD},
        # overdue, but inside 14 days: scheduled, not swept
        {"id": "edge-i-05", "tenant_id": "edge-t-05", "issued": "2026-02-20", "total": "500.00",
         "status_cd": OVERDUE_CD},
        {"id": "edge-i-06", "tenant_id": "edge-t-06", "issued": "2026-02-06", "total": "600.00",
         "status_cd": OVERDUE_CD},
        # the outer join keeps this invoice although its tenant row is absent (D-18)
        {"id": "edge-i-07", "tenant_id": ABSENT_TENANT, "issued": "2026-02-07", "total": "700.00",
         "status_cd": OVERDUE_CD},
        # issued exactly on TRUNC(p_as_of) - 14: the sweep's compare is <=, so this is inside it
        {"id": "edge-i-08", "tenant_id": "edge-t-01", "issued": "2026-02-14", "total": "800.00",
         "status_cd": OVERDUE_CD},
    ]
    filler_tenants = [f"edge-t-{i:02d}" for i in FILLER_TENANTS]
    rows += [
        {
            "id": f"edge-i-{i}",
            "tenant_id": filler_tenants[i % len(filler_tenants)],
            "issued": "2026-01-15",
            "total": "10.00",
            "status_cd": PAID_CD,
        }
        for i in FILLER_INVOICES
    ]
    return [
        {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "period_id": "edge-period-01",
            "issued_at": f"{r['issued']} 00:00:00",
            "subtotal": _money(r["total"]),
            "tax": "0.00",
            "total": _money(r["total"]),
            "status_cd": r["status_cd"],
        }
        for r in rows
    ]


def _edge_attempts() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        # an existing attempt, so NVL(MAX(attempt_no),0)+1 is 2 for edge-i-01 rather than 1
        {"id": "edge-a-01", "tenant_id": "edge-t-01", "invoice_id": "edge-i-01", "attempt_no": 1,
         "scheduled_for": "2026-02-16 00:00:00", "status_cd": ATTEMPT_SENT_CD},
        # two ingest rows on one (invoice_id, attempt_no): uq_dunning_attempts, KEY_DUPLICATE
        {"id": "edge-a-dup-a", "tenant_id": "edge-t-07", "invoice_id": "edge-i-100",
         "attempt_no": 1, "scheduled_for": "2026-01-20 00:00:00", "status_cd": ATTEMPT_SENT_CD},
        {"id": "edge-a-dup-b", "tenant_id": "edge-t-07", "invoice_id": "edge-i-100",
         "attempt_no": 1, "scheduled_for": "2026-01-21 00:00:00", "status_cd": ATTEMPT_SENT_CD},
        # fk_da_invoice has no invoice row: FK_ORPHAN
        {"id": "edge-a-orphan", "tenant_id": "edge-t-08", "invoice_id": ABSENT_INVOICE,
         "attempt_no": 1, "scheduled_for": "2026-01-22 00:00:00", "status_cd": ATTEMPT_SENT_CD},
        # a status_cd with no CODES('DUN_STATUS') row: CODE_UNKNOWN
        {"id": "edge-a-badstatus", "tenant_id": "edge-t-09", "invoice_id": "edge-i-101",
         "attempt_no": 1, "scheduled_for": "2026-01-23 00:00:00",
         "status_cd": UNMAPPED_ATTEMPT_CD},
    ]
    invoices = [f"edge-i-{i}" for i in FILLER_INVOICES][2 : 2 + FILLER_ATTEMPTS]
    filler_tenants = [f"edge-t-{i:02d}" for i in FILLER_TENANTS]
    rows += [
        {
            "id": f"edge-a-{n:03d}",
            "tenant_id": filler_tenants[n % len(filler_tenants)],
            "invoice_id": inv,
            "attempt_no": 1,
            "scheduled_for": "2026-01-25 00:00:00",
            "status_cd": ATTEMPT_SENT_CD,
        }
        for n, inv in enumerate(invoices)
    ]
    return rows


def _edge_notifications() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        # an active tenant already carrying a suspension notice on another date: the population a
        # second p_as_of would write into again
        {"id": "edge-n-01", "tenant_id": "edge-t-05", "kind_cd": KIND_SUSPENSION_CD,
         "sent_at": "2026-02-10 00:00:00"},
        # the same p_as_of, so the source's NOT EXISTS suppresses this tenant's notification
        {"id": "edge-n-02", "tenant_id": "edge-t-06", "kind_cd": KIND_SUSPENSION_CD,
         "sent_at": f"{AS_OF} 00:00:00"},
        # fk_notif_tenant with no tenant row: FK_ORPHAN
        {"id": "edge-n-orphan", "tenant_id": ABSENT_TENANT, "kind_cd": KIND_SUSPENSION_CD,
         "sent_at": "2026-02-05 00:00:00"},
        # a kind_cd with no CODES('NOTIF_KIND') row: CODE_UNKNOWN
        {"id": "edge-n-badkind", "tenant_id": "edge-t-07", "kind_cd": UNMAPPED_KIND_CD,
         "sent_at": "2026-02-05 00:00:00"},
    ]
    filler_tenants = [f"edge-t-{i:02d}" for i in FILLER_TENANTS]
    rows += [
        {
            "id": f"edge-n-{n:03d}",
            "tenant_id": filler_tenants[n % len(filler_tenants)],
            "kind_cd": KIND_INVOICE_CD,
            "sent_at": "2026-01-30 00:00:00",
        }
        for n in range(FILLER_NOTIFICATIONS)
    ]
    return rows


def _edge_subscriptions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        # the swept tenant: one active row the sweep suspends, one already suspended and one
        # cancelled, both of which the source's WHERE status_cd = 10 leaves alone (D-16)
        {"id": "edge-s-01", "tenant_id": "edge-t-01", "status_cd": ACTIVE_CD},
        {"id": "edge-s-02", "tenant_id": "edge-t-01", "status_cd": SUSPENDED_CD},
        {"id": "edge-s-03", "tenant_id": "edge-t-01", "status_cd": CANCELLED_CD},
        {"id": "edge-s-04", "tenant_id": "edge-t-06", "status_cd": ACTIVE_CD},
        {"id": "edge-s-05", "tenant_id": "edge-t-02", "status_cd": ACTIVE_CD},
    ]
    rows += [
        {"id": f"edge-s-{i:02d}", "tenant_id": f"edge-t-{i:02d}", "status_cd": ACTIVE_CD}
        for i in FILLER_SUBSCRIPTIONS
    ]
    return [
        {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "plan_id": EDGE_PLAN,
            "starts_on": "2026-01-01 00:00:00",
            "ends_on": None,
            "status_cd": r["status_cd"],
            "suspended_on": None,
        }
        for r in rows
    ]


def _edge_plans() -> list[dict[str, Any]]:
    return [
        {
            "id": EDGE_PLAN,
            "code": "EDGE-DUN",
            "tier_cd": 1,
            "monthly_fee": "10.00",
            "included_units": "1000",
            "overage_rate": "0.010000",
            "active_yn": "Y",
        }
    ]


def edge_rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "plans": _edge_plans(),
        "tenants": _edge_tenants(),
        "subscriptions": _edge_subscriptions(),
        "invoices": _edge_invoices(),
        "dunning_attempts": _edge_attempts(),
        "notifications": _edge_notifications(),
    }


def halt_rows() -> dict[str, list[dict[str, Any]]]:
    """An attempt population that is 30% rejects: three of ten invoices have no tenant row."""
    tenants = [
        {"id": f"halt-t-{i:02d}", "name": f"Halt Tenant {i}", "tax_exempt_yn": "N",
         "status_cd": ACTIVE_CD}
        for i in range(1, 5)
    ]
    invoices = []
    for i in range(1, 11):
        tenant = "halt-t-absent" if i > 7 else f"halt-t-{((i - 1) % 4) + 1:02d}"
        invoices.append(
            {
                "id": f"halt-i-{i:02d}",
                "tenant_id": tenant,
                "period_id": "halt-period-01",
                "issued_at": "2026-02-01 00:00:00",
                "subtotal": "50.00",
                "tax": "0.00",
                "total": "50.00",
                "status_cd": OVERDUE_CD,
            }
        )
    return {"tenants": tenants, "invoices": invoices}


# -- the independent model ----------------------------------------------------


def expectations() -> dict[str, Any]:
    """What `05_pkg_dunning.sql` implies for `ns=dunning_edge`, re-expressed without Spark or SQL."""
    as_of = _date(AS_OF)
    cutoff = as_of - dt.timedelta(days=CUTOFF_DAYS)
    shift = weekend_shift(as_of)
    scheduled_for = as_of + dt.timedelta(days=shift)

    tenants = {t["id"]: t for t in _edge_tenants() if t["name"].find("duplicate") < 0}
    invoices = _edge_invoices()
    attempts = _edge_attempts()
    notifications = _edge_notifications()
    subscriptions = _edge_subscriptions()

    overdue = [i for i in invoices if i["status_cd"] == OVERDUE_CD]
    overdue.sort(key=lambda i: (i["issued_at"], i["id"]))

    def tenant_status(tenant_id: str) -> str:
        row = tenants.get(tenant_id)
        if row is None:
            return "UNKNOWN"
        return {ACTIVE_CD: "active", SUSPENDED_CD: "suspended"}.get(row["status_cd"], "UNKNOWN")

    basis: dict[str, int] = {}
    for a in attempts:
        basis[a["invoice_id"]] = max(basis.get(a["invoice_id"], 0), int(a["attempt_no"]))

    # fn_overdue_accounts: the strict same-day exclusion, on truncated dates, string-compared.
    fn_rows = [
        {
            "invoice_id": i["id"],
            "tenant_id": i["tenant_id"],
            "total": i["total"],
            "days_overdue": (as_of - _date(i["issued_at"][:10])).days,
            "tenant_status": tenant_status(i["tenant_id"]),
        }
        for i in overdue
        if i["issued_at"][:10].replace("-", "") < AS_OF.replace("-", "")
    ]

    # sp_schedule_dunning: one attempt per overdue invoice, id = f_md5_uuid(invoice || attempt_no).
    schedule = []
    for i in overdue:
        attempt_no = basis.get(i["id"], 0) + 1
        schedule.append(
            {
                "id": md5_uuid(f"{i['id']}{attempt_no}"),
                "invoice_id": i["id"],
                "tenant_id": i["tenant_id"],
                "attempt_no": attempt_no,
                "attempt_no_basis": basis.get(i["id"], 0),
                "scheduled_for": scheduled_for.isoformat(),
                "unshifted_scheduled_for": AS_OF,
                "source_day_of_week": day_abbr(as_of),
                "weekend_shift_days": shift,
                "status_cd": ATTEMPT_SCHEDULED_CD,
                "tenant_row_missing": i["tenant_id"] not in tenants,
            }
        )

    # sp_suspend_overdue: the inclusive 14-day cut, then IF v_active > 0 per candidate tenant.
    in_cutoff = [i for i in overdue if i["issued_at"][:10] <= cutoff.isoformat()]
    candidates = sorted({i["tenant_id"] for i in in_cutoff})
    # A tenant the run rejects (CODE_UNKNOWN) is not swept by the target: it never reaches the load.
    rejected_tenants = {
        t["id"] for t in tenants.values() if t["status_cd"] not in (ACTIVE_CD, SUSPENDED_CD)
    }
    duplicated_tenants = {DUP_TENANT}
    swept = [
        t
        for t in candidates
        if t in tenants
        and tenants[t]["status_cd"] == ACTIVE_CD
        and t not in rejected_tenants
        and t not in duplicated_tenants
    ]
    notified_on_as_of = {
        n["tenant_id"]
        for n in notifications
        if n["kind_cd"] == KIND_SUSPENSION_CD and n["sent_at"][:10] == AS_OF
    }
    subs_of_swept = [s for s in subscriptions if s["tenant_id"] in swept]
    return {
        "as_of": AS_OF,
        "suspend_cutoff_date": cutoff.isoformat(),
        "as_of_day_of_week_english": day_abbr(as_of),
        "as_of_weekend_shift_days": shift,
        "scheduled_for": scheduled_for.isoformat(),
        "fn_overdue_accounts": fn_rows,
        "schedule": schedule,
        "invoices_in_the_schedule_driver": len(overdue),
        "invoices_overdue_by_the_function": len(fn_rows),
        "same_calendar_day_invoices": len(overdue) - len(fn_rows),
        "invoices_kept_with_no_tenant_row": sum(1 for i in overdue if i["tenant_id"] not in tenants),
        "tenant_status_unknown": sum(1 for i in overdue if tenant_status(i["tenant_id"]) == "UNKNOWN"),
        "candidate_tenants": len(candidates),
        "candidates_with_no_tenant_row": sum(1 for t in candidates if t not in tenants),
        "tenants_swept": len(swept),
        "tenants_skipped_inactive_at_ingest": sum(
            1 for t in candidates if t in tenants and tenants[t]["status_cd"] != ACTIVE_CD
        ),
        "swept_tenants": swept,
        "subscriptions_matched_by_the_sweep": len(subs_of_swept),
        "subscriptions_suspended": sum(1 for s in subs_of_swept if s["status_cd"] == ACTIVE_CD),
        "subscriptions_left_at_20": sum(1 for s in subs_of_swept if s["status_cd"] == SUSPENDED_CD),
        "subscriptions_left_at_30": sum(1 for s in subs_of_swept if s["status_cd"] == CANCELLED_CD),
        "suspended_on": AS_OF,
        "notifications_written": sum(1 for t in swept if t not in notified_on_as_of),
        "notifications_suppressed_by_not_exists": sum(1 for t in swept if t in notified_on_as_of),
        "notification_ids": sorted(
            md5_uuid(f"{t}suspension{AS_OF}") for t in swept if t not in notified_on_as_of
        ),
        "tenants_active_with_suspension_notice_on_another_date": sorted(
            {
                n["tenant_id"]
                for n in notifications
                if n["kind_cd"] == KIND_SUSPENSION_CD
                and n["sent_at"][:10] != AS_OF
                and n["tenant_id"] in tenants
                and tenants[n["tenant_id"]]["status_cd"] == ACTIVE_CD
                and n["tenant_id"] not in swept
            }
        ),
        "expected_quarantine": {
            "dunning_attempts": {
                "KEY_DUPLICATE": 2,
                "FK_ORPHAN": 2,
                "CODE_UNKNOWN": 1,
            },
            "tenants": {"KEY_DUPLICATE": 1, "CODE_UNKNOWN": 1},
            "notifications": {"FK_ORPHAN": 1, "CODE_UNKNOWN": 1},
            "subscriptions_swept": {},
        },
        "provenance": (
            "generated fixture: every row carries _source_table = 'generated-fixture', no row of it "
            "exists in OW_BILLING, and Oracle holds no copy of this namespace. The declared side of "
            "the comparison is this Python model of 05_pkg_dunning.sql, not live Oracle."
        ),
    }


# -- SQL emission --------------------------------------------------------------

BRONZE_COLUMNS: dict[str, tuple[str, ...]] = {
    "plans": ("id", "code", "tier_cd", "monthly_fee", "included_units", "overage_rate", "active_yn"),
    "tenants": ("id", "name", "tax_exempt_yn", "status_cd"),
    "subscriptions": (
        "id", "tenant_id", "plan_id", "starts_on", "ends_on", "status_cd", "suspended_on",
    ),
    "invoices": (
        "id", "tenant_id", "period_id", "issued_at", "subtotal", "tax", "total", "status_cd",
    ),
    "dunning_attempts": (
        "id", "tenant_id", "invoice_id", "attempt_no", "scheduled_for", "status_cd",
    ),
    "notifications": ("id", "tenant_id", "kind_cd", "sent_at"),
}
TIMESTAMP_COLUMNS = {"starts_on", "ends_on", "suspended_on", "issued_at", "scheduled_for", "sent_at"}
DECIMAL_COLUMNS = {"monthly_fee", "included_units", "overage_rate", "subtotal", "tax", "total"}


def _literal(column: str, value: Any) -> str:
    if value is None:
        return "NULL"
    if column in TIMESTAMP_COLUMNS:
        return f"TIMESTAMP'{value}'"
    if column in DECIMAL_COLUMNS:
        return str(value)
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert_statements(
    catalog: str, schema: str, ns: str, rows: dict[str, list[dict[str, Any]]], batch: int = 200
) -> list[str]:
    """One INSERT per table (chunked), every row carrying this namespace's `ns` and the fixture tag."""
    ns_lit = "'" + ns.replace("'", "''") + "'"
    out: list[str] = []
    for table, table_rows in rows.items():
        cols = BRONZE_COLUMNS[table]
        collist = ", ".join(list(cols) + ["ns", "_source_table", "_loaded_at"])
        for start in range(0, len(table_rows), batch):
            values = ",\n       ".join(
                "("
                + ", ".join(_literal(c, r.get(c)) for c in cols)
                + f", {ns_lit}, '{ORIGIN}', current_timestamp())"
                for r in table_rows[start : start + batch]
            )
            out.append(f"INSERT INTO {catalog}.{schema}.{table} ({collist}) VALUES\n       {values}")
    return out


def reset_statements(catalog: str, bronze: str, silver: str, ns: str, unit: str) -> list[str]:
    """Drop only this fixture namespace's own rows: `ns`-scoped, never table-wide.

    The silver tables cleared here are the ones this unit owns plus `quarantine_<unit>`.
    `<silver>.subscriptions`, `<silver>.plans` and `<silver>.entitlements` belong to `silver_plans`
    and are left exactly as its own run left them: this unit deletes nothing on another unit's table.
    """
    ns_lit = "'" + ns.replace("'", "''") + "'"
    stmts = [
        f"DELETE FROM {catalog}.{bronze}.{t} WHERE ns = {ns_lit}"
        for t in ("plans", "tenants", "subscriptions", "invoices", "dunning_attempts", "notifications")
    ]
    stmts += [
        f"DELETE FROM {catalog}.{silver}.{t} WHERE ns = {ns_lit}"
        for t in ("dunning_attempts", "notifications", "tenants", f"quarantine_{unit}")
    ]
    return stmts


def replay_statements(
    catalog: str, bronze: str, source_ns: str, ns: str
) -> list[str]:
    """Copy one namespace's bronze ingest rows under another `ns`, tagged as a copy.

    Used for the transcript replays: `DUNNING-002`/`DUNNING-003` need `sp_schedule_dunning` on a
    different `p_as_of` than the reconciled run, and running that second date into `ns=demo` would
    write `ns=demo` twice for two different nights.
    """
    ns_lit = "'" + ns.replace("'", "''") + "'"
    src_lit = "'" + source_ns.replace("'", "''") + "'"
    out = [
        f"DELETE FROM {catalog}.{bronze}.{t} WHERE ns = {ns_lit}"
        for t in ("codes", "tenants", "invoices", "dunning_attempts", "notifications")
    ]
    for table, cols in (
        ("codes", ("code_type", "code_val", "code_desc")),
        ("tenants", BRONZE_COLUMNS["tenants"]),
        ("invoices", BRONZE_COLUMNS["invoices"]),
        ("dunning_attempts", BRONZE_COLUMNS["dunning_attempts"]),
        ("notifications", BRONZE_COLUMNS["notifications"]),
    ):
        collist = ", ".join(list(cols) + ["ns", "_source_table", "_loaded_at"])
        selectlist = ", ".join(list(cols) + [ns_lit, f"'replay-of-{source_ns}'", "current_timestamp()"])
        out.append(
            f"INSERT INTO {catalog}.{bronze}.{table} ({collist}) "
            f"SELECT {selectlist} FROM {catalog}.{bronze}.{table} WHERE ns = {src_lit}"
        )
    return out


def codes_copy_statements(catalog: str, bronze: str, source_ns: str, ns: str) -> list[str]:
    """The fixture namespaces reuse the source's own CODES rows; only `ns` differs."""
    ns_lit = "'" + ns.replace("'", "''") + "'"
    src_lit = "'" + source_ns.replace("'", "''") + "'"
    return [
        f"DELETE FROM {catalog}.{bronze}.codes WHERE ns = {ns_lit}",
        f"INSERT INTO {catalog}.{bronze}.codes (code_type, code_val, code_desc, ns, _source_table, "
        f"_loaded_at) SELECT code_type, code_val, code_desc, {ns_lit}, '{ORIGIN}', "
        f"current_timestamp() FROM {catalog}.{bronze}.codes WHERE ns = {src_lit}",
    ]
