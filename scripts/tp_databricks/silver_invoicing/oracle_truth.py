"""Read-only Oracle side of the silver_invoicing recon.

Three things are measured here and nothing is written: the invoice the **source database** computes
for the population under test, the credit burn-down that source would perform, and the source's own
`INVOICES` / `INVOICE_LINES` / `CREDIT_NOTES` rows.

The invoice is obtained by re-expressing `pkg_invoicing.compute_preview` / `fn_invoice_preview` /
`sp_issue_invoice` — including the `pkg_rating.compute_rating` call they depend on through
`pkg_rating`'s package globals — as read-only SQL and letting **Oracle** evaluate it. That is the
point: the arithmetic that decides money — the hardcoded `0.0825`, the two unrounded `g_tax/2`
halves, `LEAST`/`GREATEST` null propagation, `NVL`, `DECODE`, `ROUND` half-away-from-zero,
`TO_CHAR(date,'YYYYMMDD')` string windowing, `DATE - DATE` day arithmetic and `NUMBER` precision —
is evaluated by the source engine under its own NLS settings, so a dialect entry that Databricks and
Oracle disagree about shows up as a row-level mismatch instead of being hidden by a second Python
re-implementation of the same guess.

Its limit is stated in the recon report: it is a re-expression, not the PL/SQL package itself. The
six pinned Oracle transcripts in `procs/oracle/transcripts/invoicing/` are what tie this statement to
the real engine, and neither `PKG_INVOICING` nor any other batch chain is ever executed against the
source — running it would write `INVOICES`/`INVOICE_LINES` rows and burn `CREDIT_NOTES` down.
"""

from __future__ import annotations

import decimal
import os
import pathlib

import oracledb

from scripts.tp_databricks.silver_rating.oracle_truth import (  # the shared, source-derived helpers
    F_MD5_UUID,
    _number_handler,
    connect,
    count,
    money,
    oracle_source_sha,
    rate,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]

__all__ = [
    "oracle_source_sha",
    "connect",
    "money",
    "count",
    "rate",
    "snapshot",
    "TAX_RATE",
]

# The constant lives in the package body and nowhere else; it is written out here so the Oracle side
# of the comparison prices with the source's own literal (ANOM-HARDCODED-TAX, D-11).
TAX_RATE = "0.0825"

# compute_preview, in the source's order, with pkg_rating.compute_rating inlined where the source
# calls it and reads g_overage_amount back out of the package global (D-10, ACC-INLINE-RATING).
PREVIEW_BODY = f"""
WITH prm AS (
    SELECT TO_DATE(:ps, 'YYYY-MM-DD') AS ps, TO_DATE(:pe, 'YYYY-MM-DD') AS pe FROM dual
),
-- compute_rating's covering-subscription pick: SUBSCRIPTIONS alone, so a subscription whose plan
-- row is missing still wins here and leaves the quota and the rate NULL.
sub_pick AS (
    SELECT tenant_id, id, status_cd, suspended_on, plan_id, cand_rows, tied_rows
      FROM (SELECT s.tenant_id, s.id, s.status_cd, s.suspended_on, s.plan_id,
                   ROW_NUMBER() OVER (PARTITION BY s.tenant_id
                                      ORDER BY s.starts_on DESC, s.id DESC) AS rn,
                   COUNT(*) OVER (PARTITION BY s.tenant_id) AS cand_rows,
                   COUNT(*) OVER (PARTITION BY s.tenant_id, s.starts_on) AS tied_rows
              FROM subscriptions s, prm p
             WHERE s.starts_on <= p.pe
               AND (s.ends_on IS NULL OR s.ends_on >= p.ps))
     WHERE rn = 1
),
-- compute_preview's own pick, which joins PLANS, so it skips exactly the subscriptions the rating
-- pick keeps with a NULL plan.
fee_pick AS (
    SELECT tenant_id, sub_id, plan_code, monthly_fee, fee_cand_rows, fee_tied_rows
      FROM (SELECT s.tenant_id, s.id AS sub_id, pl.code AS plan_code, pl.monthly_fee,
                   ROW_NUMBER() OVER (PARTITION BY s.tenant_id
                                      ORDER BY s.starts_on DESC, s.id DESC) AS rn,
                   COUNT(*) OVER (PARTITION BY s.tenant_id) AS fee_cand_rows,
                   COUNT(*) OVER (PARTITION BY s.tenant_id, s.starts_on) AS fee_tied_rows
              FROM subscriptions s, plans pl, prm p
             WHERE pl.id = s.plan_id
               AND s.starts_on <= p.pe
               AND (s.ends_on IS NULL OR s.ends_on >= p.ps))
     WHERE rn = 1
),
usg AS (
    SELECT u.tenant_id, SUM(NVL(u.units, 0)) AS used_units, COUNT(*) AS events_in_window
      FROM usage_events u, prm p
     WHERE TO_CHAR(u.occurred_at, 'YYYYMMDD') >= TO_CHAR(p.ps, 'YYYYMMDD')
       AND TO_CHAR(u.occurred_at, 'YYYYMMDD') <= TO_CHAR(p.pe, 'YYYYMMDD')
     GROUP BY u.tenant_id
),
-- compute_rating's three-month rollover bank, strictly earlier periods only.
pri AS (
    SELECT rp.tenant_id, SUM(NVL(rr.rollover_units, 0)) AS prior_units
      FROM rating_results rr, rating_periods rp, prm p
     WHERE rp.id = rr.period_id
       AND rp.period_start < p.ps
       AND rp.period_start >= ADD_MONTHS(p.ps, -3)
     GROUP BY rp.tenant_id
),
cred AS (
    SELECT cn.tenant_id, SUM(cn.remaining_amount) AS g_credit, COUNT(*) AS open_notes
      FROM credit_notes cn
     WHERE cn.remaining_amount > 0
     GROUP BY cn.tenant_id
),
base AS (
    SELECT t.id AS tenant_id, s.id AS rating_sub_id, s.status_cd, s.suspended_on,
           NVL(s.cand_rows, 0) AS cand_rows, NVL(s.tied_rows, 0) AS tied_rows,
           f.sub_id AS fee_sub_id, f.plan_code AS g_plan_code, f.monthly_fee AS g_plan_fee,
           NVL(f.fee_cand_rows, 0) AS fee_cand_rows, NVL(f.fee_tied_rows, 0) AS fee_tied_rows,
           pl.included_units AS v_included, pl.overage_rate AS v_rate,
           NVL(u.used_units, 0) AS used_units, NVL(u.events_in_window, 0) AS events_in_window,
           NVL(pr.prior_units, 0) AS prior_units,
           NVL(t.tax_exempt_yn, 'N') AS v_exempt,
           NVL(c.g_credit, 0) AS g_credit, NVL(c.open_notes, 0) AS open_notes,
           p.ps, p.pe
      FROM tenants t
     CROSS JOIN prm p
      LEFT JOIN sub_pick s ON s.tenant_id = t.id
      LEFT JOIN fee_pick f ON f.tenant_id = t.id
      LEFT JOIN plans pl ON pl.id = s.plan_id
      LEFT JOIN usg u ON u.tenant_id = t.id
      LEFT JOIN pri pr ON pr.tenant_id = t.id
      LEFT JOIN cred c ON c.tenant_id = t.id
),
capped AS (
    SELECT b.*, LEAST(NVL(2 * v_included, prior_units), prior_units) AS prior_capped FROM base b
),
rated AS (
    SELECT c.*, v_included AS quota_units,
           LEAST(prior_capped, NVL(v_included * 2, prior_capped)) AS computed_rollover
      FROM capped c
),
billed AS (
    SELECT r.*, GREATEST(NVL(used_units - computed_rollover - v_included, 0), 0) AS billable_pre
      FROM rated r
),
tiered AS (
    SELECT b.*, LEAST(billable_pre, 101) AS first_tier,
           GREATEST(billable_pre - 101, 0) AS second_tier
      FROM billed b
),
priced AS (
    SELECT t.*, ROUND(first_tier * v_rate + second_tier * v_rate * 1.5, 2) AS overage_pre
      FROM tiered t
),
prorated AS (
    SELECT p.*,
           CASE WHEN status_cd = 20 AND suspended_on IS NOT NULL
                     AND suspended_on BETWEEN ps AND pe THEN 1 ELSE 0 END AS suspended_flag,
           CASE WHEN status_cd = 20 AND suspended_on IS NOT NULL
                     AND suspended_on BETWEEN ps AND pe
                THEN ROUND(billable_pre * ((pe - suspended_on + 1) / (pe - ps + 1)))
                ELSE billable_pre END AS billable_units,
           CASE WHEN status_cd = 20 AND suspended_on IS NOT NULL
                     AND suspended_on BETWEEN ps AND pe
                THEN ROUND(overage_pre * ((pe - suspended_on + 1) / (pe - ps + 1)), 2)
                ELSE overage_pre END AS g_overage
      FROM priced p
),
-- g_tax := DECODE(v_exempt, 'Y', 0, (g_plan_fee + g_overage) * TAX_RATE)
taxed AS (
    SELECT p.*, DECODE(v_exempt, 'Y', 0, (g_plan_fee + g_overage) * {TAX_RATE}) AS g_tax
      FROM prorated p
),
-- v_charge_cap := ROUND(g_plan_fee + g_overage + g_tax, 2); the two tax lines are g_tax / 2 each,
-- left unrounded by the preview cursor.
capd AS (
    SELECT t.*, ROUND(g_plan_fee + g_overage + g_tax, 2) AS v_charge_cap, t.g_tax / 2 AS tax_half
      FROM taxed t
),
-- v_credit_app := LEAST(g_credit, NVL(v_charge_cap, g_credit))
app AS (
    SELECT c.*, LEAST(g_credit, NVL(v_charge_cap, g_credit)) AS v_credit_app FROM capd c
),
-- The issue loop's accumulation over the five preview lines: plan and usage into v_subtotal, the
-- two tax lines into v_tax, each added as ROUND(v_amount, 2).
hdr AS (
    SELECT a.*,
           ROUND(ROUND(g_plan_fee, 2) + ROUND(g_overage, 2), 2) AS v_subtotal,
           ROUND(ROUND(a.tax_half, 2) + ROUND(a.tax_half, 2), 2) AS v_tax,
           {F_MD5_UUID.format(x="tenant_id || TO_CHAR(ps, 'YYYY-MM-DD')")} AS period_id
      FROM app a
),
inv AS (
    SELECT h.*, {F_MD5_UUID.format(x="period_id || 'invoice'")} AS invoice_id
      FROM hdr h
)
"""

PREVIEW_SQL = (
    PREVIEW_BODY
    + """
SELECT tenant_id, period_id, invoice_id, rating_sub_id, fee_sub_id,
       cand_rows, tied_rows, fee_cand_rows, fee_tied_rows, events_in_window, open_notes,
       g_plan_code, g_plan_fee, g_overage, v_exempt, g_tax, tax_half, v_charge_cap,
       g_credit, v_credit_app, v_subtotal, v_tax,
       ROUND(v_subtotal + v_tax - v_credit_app, 2) AS v_total,
       ROUND(g_tax, 2) AS tax_if_rounded_once,
       v_rate, quota_units, used_units, computed_rollover,
       GREATEST(quota_units - used_units, 0) AS persisted_rollover,
       first_tier, second_tier, billable_units, suspended_flag
  FROM inv
 ORDER BY tenant_id
"""
)

# The burn-down, evaluated by Oracle over the same ordered cursor sp_issue_invoice opens. The
# recurrence is expressed as an ordered window rather than an aggregate because the counter is
# decremented by each note's pre-update balance, which is exactly what lets it over-apply (D-12).
CREDIT_BURN_SQL = (
    PREVIEW_BODY
    + """,
notes AS (
    SELECT cn.tenant_id, cn.id AS note_id, cn.issued_on, cn.remaining_amount,
           ROW_NUMBER() OVER (PARTITION BY cn.tenant_id
                              ORDER BY cn.issued_on, cn.id) AS seq_no,
           NVL(SUM(cn.remaining_amount) OVER (PARTITION BY cn.tenant_id
                                              ORDER BY cn.issued_on, cn.id
                                              ROWS BETWEEN UNBOUNDED PRECEDING
                                                       AND 1 PRECEDING), 0) AS consumed_before
      FROM credit_notes cn
     WHERE cn.remaining_amount > 0
),
run AS (
    SELECT n.tenant_id, i.invoice_id, n.note_id, n.seq_no, n.issued_on, n.remaining_amount,
           i.v_credit_app,
           GREATEST(i.v_credit_app - n.consumed_before, 0) AS running_before
      FROM notes n, inv i
     WHERE i.tenant_id = n.tenant_id
)
SELECT tenant_id, invoice_id, note_id, seq_no,
       TO_CHAR(issued_on, 'YYYY-MM-DD') AS issued_on,
       remaining_amount AS remaining_before,
       running_before,
       CASE WHEN running_before <= 0 THEN 0
            ELSE remaining_amount - GREATEST(remaining_amount - running_before, 0) END AS applied,
       CASE WHEN running_before <= 0 THEN remaining_amount
            ELSE GREATEST(remaining_amount - running_before, 0) END AS remaining_after,
       CASE WHEN running_before <= 0 THEN running_before
            ELSE GREATEST(running_before - remaining_amount, 0) END AS running_after,
       CASE WHEN running_before <= 0 THEN 1 ELSE 0 END AS skipped
  FROM run
 ORDER BY tenant_id, seq_no
"""
)

EXISTING_INVOICES_SQL = """
SELECT i.id, i.tenant_id, i.period_id,
       TO_CHAR(i.issued_at, 'YYYY-MM-DD HH24:MI:SS') AS issued_at,
       i.subtotal, i.tax, i.total, i.status_cd,
       (SELECT c.code_desc FROM codes c
         WHERE c.code_type = 'INV_STATUS' AND c.code_val = TO_CHAR(i.status_cd)) AS status_desc
  FROM invoices i
 ORDER BY i.tenant_id, i.id
"""

EXISTING_LINES_SQL = """
SELECT l.id, l.invoice_id, l.line_no, l.line_type, l.description, l.amount
  FROM invoice_lines l
 ORDER BY l.invoice_id, l.line_no
"""

EXISTING_CREDIT_NOTES_SQL = """
SELECT cn.id, cn.tenant_id, TO_CHAR(cn.issued_on, 'YYYY-MM-DD') AS issued_on,
       cn.amount, cn.remaining_amount
  FROM credit_notes cn
 ORDER BY cn.tenant_id, cn.issued_on, cn.id
"""

# fn_invoice_lines, the source's own cursor, for transcript INVOICE-006.
INVOICE_LINES_OF_SQL = """
SELECT l.line_no, l.line_type, l.description, l.amount
  FROM invoice_lines l
 WHERE l.invoice_id = :invoice_id
 ORDER BY l.line_no
"""

COUNTS_SQL = """
SELECT (SELECT COUNT(*) FROM tenants),
       (SELECT COUNT(*) FROM subscriptions),
       (SELECT COUNT(*) FROM plans),
       (SELECT COUNT(*) FROM usage_events),
       (SELECT COUNT(*) FROM credit_notes),
       (SELECT COUNT(*) FROM invoices),
       (SELECT COUNT(*) FROM invoice_lines),
       (SELECT COUNT(*) FROM rating_periods),
       (SELECT COUNT(*) FROM rating_results),
       (SELECT COUNT(*) FROM customer_master),
       (SELECT COUNT(*) FROM entity_attr_value),
       (SELECT COUNT(*) FROM invoice_line)
  FROM dual
"""

COUNT_KEYS = (
    "tenants",
    "subscriptions",
    "plans",
    "usage_events",
    "credit_notes",
    "invoices",
    "invoice_lines",
    "rating_periods",
    "rating_results",
    "customer_master",
    "entity_attr_value",
    "invoice_line",
)

# ACC-MERGE-KEY: the target's key derivation is asserted against the source function itself, not
# against a second copy of the formula. The line id is the invoice id concatenated with the line
# number, the same shape sp_issue_invoice's INSERT builds.
SAMPLE_KEYS_SQL = """
SELECT t.id,
       pkg_ow_util.f_md5_uuid(t.id || TO_CHAR(TO_DATE(:ps, 'YYYY-MM-DD'), 'YYYY-MM-DD')) AS period_id,
       pkg_ow_util.f_md5_uuid(
           pkg_ow_util.f_md5_uuid(t.id || TO_CHAR(TO_DATE(:ps, 'YYYY-MM-DD'), 'YYYY-MM-DD'))
           || 'invoice') AS invoice_id,
       pkg_ow_util.f_md5_uuid(
           pkg_ow_util.f_md5_uuid(
               pkg_ow_util.f_md5_uuid(t.id || TO_CHAR(TO_DATE(:ps, 'YYYY-MM-DD'), 'YYYY-MM-DD'))
               || 'invoice') || TO_CHAR(1)) AS line1_id
  FROM (SELECT id FROM tenants ORDER BY id) t
 WHERE ROWNUM <= 10
"""

# The tax arithmetic, evaluated by Oracle on synthetic amounts: the two unrounded halves against the
# single ROUND(g_tax, 2) a tidier implementation would have written. Read-only, over dual, so it
# measures the engine's own half-away-from-zero behaviour without touching a source row.
TAX_HALVES_SQL = f"""
WITH cases AS (
    SELECT 1 AS ord, TO_NUMBER(:a1) AS base_amount FROM dual
    UNION ALL SELECT 2, TO_NUMBER(:a2) FROM dual
    UNION ALL SELECT 3, TO_NUMBER(:a3) FROM dual
),
taxed AS (
    SELECT c.ord, c.base_amount, c.base_amount * {TAX_RATE} AS g_tax FROM cases c
)
SELECT ord, base_amount, g_tax, g_tax / 2 AS tax_half,
       ROUND(g_tax / 2, 2) + ROUND(g_tax / 2, 2) AS tax_two_unrounded_halves,
       ROUND(g_tax, 2) AS tax_if_rounded_once
  FROM taxed
 ORDER BY ord
"""


def _rows(cur, sql: str, **binds) -> list[tuple]:
    cur.execute(sql, binds) if binds else cur.execute(sql)
    return cur.fetchall()


def snapshot(period_start: str, period_end: str, tax_probe_amounts: list[str]) -> dict:
    """One read-only session: source counts, the invoice Oracle computes, and its stored rows."""
    if len(tax_probe_amounts) != 3:
        raise ValueError("TAX_HALVES_SQL is bound to exactly three cases")
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")

        counts = dict(zip(COUNT_KEYS, (int(c) for c in _rows(cur, COUNTS_SQL)[0])))

        invoices = {}
        for r in _rows(cur, PREVIEW_SQL, ps=period_start, pe=period_end):
            invoices[r[0]] = {
                "tenant_id": r[0],
                "period_id": r[1],
                "invoice_id": r[2],
                "rating_subscription_id": r[3],
                "fee_subscription_id": r[4],
                "subscription_candidates": int(r[5]),
                "subscription_tied_rows": int(r[6]),
                "fee_candidates": int(r[7]),
                "fee_tied_rows": int(r[8]),
                "usage_events_in_window": int(r[9]),
                "open_credit_notes": int(r[10]),
                "plan_code": r[11],
                "plan_fee": money(r[12]),
                "overage_amount": money(r[13]),
                "tax_exempt_yn": r[14],
                "tax_computed": None if r[15] is None else str(decimal.Decimal(r[15])),
                "tax_half": None if r[16] is None else str(decimal.Decimal(r[16])),
                "charge_cap": money(r[17]),
                "credit_offered": money(r[18]),
                "credit_applied": money(r[19]),
                "subtotal": money(r[20]),
                "tax": money(r[21]),
                "total": money(r[22]),
                "tax_if_rounded_once": money(r[23]),
                "overage_rate": rate(r[24]),
                "quota_units": count(r[25]),
                "used_units": count(r[26]),
                "computed_rollover_units": count(r[27]),
                "persisted_rollover_units": count(r[28]),
                "first_tier_units": count(r[29]),
                "second_tier_units": count(r[30]),
                "billable_units": count(r[31]),
                "suspension_prorated": bool(int(r[32])),
            }

        burn = [
            {
                "tenant_id": r[0],
                "invoice_id": r[1],
                "credit_note_id": r[2],
                "seq_no": int(r[3]),
                "issued_on": r[4],
                "remaining_before": money(r[5]),
                "credit_running_before": money(r[6]),
                "applied_amount": money(r[7]),
                "remaining_after": money(r[8]),
                "credit_running_after": money(r[9]),
                "skipped_by_exit_when": bool(int(r[10])),
            }
            for r in _rows(cur, CREDIT_BURN_SQL, ps=period_start, pe=period_end)
        ]

        existing_invoices = [
            {
                "id": r[0],
                "tenant_id": r[1],
                "period_id": r[2],
                "issued_at": r[3],
                "subtotal": money(r[4]),
                "tax": money(r[5]),
                "total": money(r[6]),
                "status_cd": int(r[7]),
                "status_desc": r[8],
            }
            for r in _rows(cur, EXISTING_INVOICES_SQL)
        ]
        existing_lines = [
            {
                "id": r[0],
                "invoice_id": r[1],
                "line_no": int(r[2]),
                "line_type": r[3],
                "description": r[4],
                "amount": money(r[5]),
            }
            for r in _rows(cur, EXISTING_LINES_SQL)
        ]
        credit_notes = [
            {
                "id": r[0],
                "tenant_id": r[1],
                "issued_on": r[2],
                "amount": money(r[3]),
                "remaining_amount": money(r[4]),
            }
            for r in _rows(cur, EXISTING_CREDIT_NOTES_SQL)
        ]
        sample_keys = [
            {"tenant_id": r[0], "period_id": r[1], "invoice_id": r[2], "line1_id": r[3]}
            for r in _rows(cur, SAMPLE_KEYS_SQL, ps=period_start)
        ]
        tax_probe = [
            {
                "base_amount": money(r[1]),
                "tax_computed": str(decimal.Decimal(r[2])),
                "tax_half": str(decimal.Decimal(r[3])),
                "tax_two_unrounded_halves": money(r[4]),
                "tax_if_rounded_once": money(r[5]),
            }
            for r in _rows(
                cur,
                TAX_HALVES_SQL,
                a1=tax_probe_amounts[0],
                a2=tax_probe_amounts[1],
                a3=tax_probe_amounts[2],
            )
        ]
        banner = _rows(cur, "SELECT banner_full FROM v$version")[0][0]
        conn.rollback()

    return {
        "oracle_banner": banner,
        "source_counts": counts,
        "invoices": invoices,
        "credit_burn": burn,
        "existing_invoices": existing_invoices,
        "existing_lines": existing_lines,
        "credit_notes": credit_notes,
        "sample_keys": sample_keys,
        "tax_halves_probe": tax_probe,
        "oracle_source_sha": oracle_source_sha(),
        "service": os.getenv("DB_SERVICE", "FREEPDB1"),
    }


def lines_of_invoice(invoice_id: str) -> list[dict]:
    """fn_invoice_lines for one invoice, as the source's own cursor returns it."""
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        rows = _rows(cur, INVOICE_LINES_OF_SQL, invoice_id=invoice_id)
        conn.rollback()
    return [
        {"line_no": int(r[0]), "line_type": r[1], "description": r[2], "amount": money(r[3])}
        for r in rows
    ]
