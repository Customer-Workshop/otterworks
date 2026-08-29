"""Read-only Oracle side of the silver_plans recon.

Everything here is a `SELECT`. `pkg_plans.sp_change_plan` **mutates** `SUBSCRIPTIONS`, so it is
never called: it is re-expressed as read-only SQL and evaluated by **Oracle**, the same way
`silver_rating` and `silver_invoicing` handled their procedures. That limit is stated in the recon
report's `unverified_paths`, and the five pinned transcripts in `procs/oracle/transcripts/plans/`
are what tie these statements to the real engine.

Letting the source engine evaluate the re-expression is the point. The behaviours that decide the
answer here — `TO_DATE('31-DEC-99','DD-MON-YY')`'s two-digit-year pivot, `NVL`, `DECODE`'s null-safe
equality, `GREATEST` null propagation, `DATE - 1` day arithmetic with its time component, the
`p.id (+) = s.plan_id` outer join direction, and `ROWNUM` without a total order — are evaluated
under Oracle's own NLS settings rather than re-guessed in Python.

The session is opened with autocommit off and rolled back on the way out, and the only PL/SQL
called is `pkg_ow_util.f_md5_uuid`, which reads `dual`.
"""

from __future__ import annotations

import decimal
import hashlib
import json
import os
import pathlib

import oracledb

ROOT = pathlib.Path(__file__).resolve().parents[3]
ORACLE_DB_DIR = ROOT / "services" / "legacy-billing" / "db" / "oracle"

COUNTS_SQL = """
SELECT (SELECT COUNT(*) FROM tenants),
       (SELECT COUNT(*) FROM plans),
       (SELECT COUNT(*) FROM subscriptions),
       (SELECT COUNT(*) FROM usage_events),
       (SELECT COUNT(*) FROM codes)
  FROM dual
"""

# fn_list_plans, verbatim: NVL(active_yn,'N') = 'Y' (a NULL active_yn is inactive) and
# ORDER BY monthly_fee, code. ROWNUM is the position the function's cursor hands back.
LIST_PLANS_SQL = """
SELECT ROWNUM AS list_seq, id, code, tier_cd, tier, monthly_fee, included_units, overage_rate
  FROM (SELECT p.id, p.code, p.tier_cd,
               DECODE(p.tier_cd, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS tier,
               p.monthly_fee, p.included_units, p.overage_rate
          FROM plans p
         WHERE NVL(p.active_yn, 'N') = 'Y'
         ORDER BY p.monthly_fee, p.code)
"""

# The whole PLANS table, which is what the target loads: the function's filter is carried as
# columns there, so the accounting identity holds on the source table itself.
ALL_PLANS_SQL = """
SELECT p.id, p.code, p.tier_cd,
       DECODE(p.tier_cd, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS tier,
       p.monthly_fee, p.included_units, p.overage_rate, p.active_yn,
       NVL(p.active_yn, 'N') AS active_nvl,
       CASE WHEN NVL(p.active_yn, 'N') = 'Y' THEN 1 ELSE 0 END AS listed
  FROM plans p
 ORDER BY p.id
"""

ALL_SUBS_SQL = """
SELECT s.id, s.tenant_id, s.plan_id,
       TO_CHAR(s.starts_on, 'YYYY-MM-DD HH24:MI:SS') AS starts_on,
       TO_CHAR(s.ends_on, 'YYYY-MM-DD HH24:MI:SS') AS ends_on,
       s.status_cd,
       TO_CHAR(s.suspended_on, 'YYYY-MM-DD HH24:MI:SS') AS suspended_on
  FROM subscriptions s
 ORDER BY s.id
"""

# fn_entitlement's returned cursor, in the source's own shape: tenants ⋈ subscriptions with
# p.id (+) = s.plan_id, the (ends_on IS NULL OR ends_on >= p_on) predicate, ORDER BY starts_on DESC
# and one row out. ROWNUM <= 1 over a non-total order is replaced by the pinned D-08 tie-break, and
# the candidate and tie counts come back so the tie population is measured, not assumed.
ENTITLEMENT_SQL = """
SELECT tenant_id, subscription_id, plan_id, plan_code, tier, monthly_fee, included_units,
       subscription_status, status_cd,
       TO_CHAR(effective_on, 'YYYY-MM-DD HH24:MI:SS') AS effective_on,
       TO_CHAR(starts_on, 'YYYY-MM-DD HH24:MI:SS') AS starts_on,
       TO_CHAR(ends_on, 'YYYY-MM-DD HH24:MI:SS') AS ends_on,
       cand_rows, tied_rows, cursor_covers, sentinel_covers
  FROM (SELECT t.id AS tenant_id, s.id AS subscription_id, s.plan_id, p.code AS plan_code,
               DECODE(p.tier_cd, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS tier,
               p.monthly_fee, p.included_units,
               DECODE(s.status_cd, 10, 'active', 20, 'suspended', 30, 'cancelled',
                      'UNKNOWN') AS subscription_status,
               s.status_cd,
               GREATEST(s.starts_on, prm.p_on) AS effective_on,
               s.starts_on, s.ends_on,
               ROW_NUMBER() OVER (PARTITION BY t.id
                                  ORDER BY s.starts_on DESC, s.id DESC) AS rn,
               COUNT(*) OVER (PARTITION BY t.id) AS cand_rows,
               COUNT(*) OVER (PARTITION BY t.id, s.starts_on) AS tied_rows,
               1 AS cursor_covers,
               CASE WHEN NVL(s.ends_on, TO_DATE('31-DEC-99', 'DD-MON-YY')) >= prm.p_on
                    THEN 1 ELSE 0 END AS sentinel_covers
          FROM tenants t, subscriptions s, plans p,
               (SELECT TO_DATE(:p_on, 'YYYY-MM-DD') AS p_on FROM dual) prm
         WHERE s.tenant_id = t.id
           AND p.id (+) = s.plan_id
           AND t.id IS NOT NULL
           AND s.starts_on <= prm.p_on
           AND (s.ends_on IS NULL OR s.ends_on >= prm.p_on))
 WHERE rn = 1
 ORDER BY tenant_id
"""

# The package-global lookup, which is a *different* statement with a *different* predicate: the
# D-05 sentinel and a bare ROWNUM = 1 with no ORDER BY at all. The walk then reconstructs what the
# globals hold: g_last_tenant_id is assigned before the SELECT INTO, and WHEN OTHERS THEN NULL
# swallows NO_DATA_FOUND, so a tenant whose lookup finds nothing keeps the plan code assigned by the
# last tenant whose lookup did find one. Tenants are walked in the declared order (tenant id).
GLOBAL_WALK_SQL = """
WITH prm AS (SELECT TO_DATE(:p_on, 'YYYY-MM-DD') AS p_on FROM dual),
g AS (SELECT tenant_id, plan_code, subscription_id, cand_rows
        FROM (SELECT s.tenant_id, p.code AS plan_code, s.id AS subscription_id,
                     ROW_NUMBER() OVER (PARTITION BY s.tenant_id
                                        ORDER BY s.starts_on DESC, s.id DESC) AS rn,
                     COUNT(*) OVER (PARTITION BY s.tenant_id) AS cand_rows
                FROM subscriptions s, plans p, prm
               WHERE p.id (+) = s.plan_id
                 AND s.starts_on <= prm.p_on
                 AND NVL(s.ends_on, TO_DATE('31-DEC-99', 'DD-MON-YY')) >= prm.p_on)
       WHERE rn = 1),
w AS (SELECT t.id AS tenant_id,
             ROW_NUMBER() OVER (ORDER BY t.id) AS seq,
             CASE WHEN g.tenant_id IS NULL THEN 0 ELSE 1 END AS matched,
             g.plan_code, NVL(g.cand_rows, 0) AS cand_rows
        FROM tenants t, g
       WHERE g.tenant_id (+) = t.id),
w2 AS (SELECT w.*,
              MAX(CASE WHEN matched = 1 THEN seq END) OVER (
                  ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS last_seq
         FROM w)
SELECT w2.tenant_id, w2.seq, w2.matched, w2.plan_code, w2.cand_rows,
       prev.plan_code AS stale_plan_code,
       CASE WHEN w2.matched = 0 AND w2.last_seq IS NOT NULL THEN 1 ELSE 0 END AS stale_mismatch
  FROM w2, w prev
 WHERE prev.seq (+) = w2.last_seq
 ORDER BY w2.seq
"""

# What the two predicates cover, per tenant, so their disagreement is a measured number.
PREDICATE_POP_SQL = """
WITH prm AS (SELECT TO_DATE(:p_on, 'YYYY-MM-DD') AS p_on FROM dual)
SELECT (SELECT COUNT(*) FROM tenants),
       (SELECT COUNT(DISTINCT s.tenant_id) FROM subscriptions s, prm
         WHERE s.starts_on <= prm.p_on
           AND NVL(s.ends_on, TO_DATE('31-DEC-99', 'DD-MON-YY')) >= prm.p_on),
       (SELECT COUNT(DISTINCT s.tenant_id) FROM subscriptions s, prm
         WHERE s.starts_on <= prm.p_on
           AND (s.ends_on IS NULL OR s.ends_on >= prm.p_on)),
       (SELECT COUNT(*) FROM subscriptions s, prm
         WHERE s.starts_on <= prm.p_on
           AND CASE WHEN (s.ends_on IS NULL OR s.ends_on >= prm.p_on) THEN 1 ELSE 0 END
             <> CASE WHEN NVL(s.ends_on, TO_DATE('31-DEC-99', 'DD-MON-YY')) >= prm.p_on
                     THEN 1 ELSE 0 END),
       (SELECT COUNT(*) FROM subscriptions s, plans p
         WHERE p.id (+) = s.plan_id AND p.id IS NULL),
       (SELECT COUNT(*) FROM subscriptions WHERE ends_on IS NULL),
       (SELECT COUNT(*) FROM (SELECT tenant_id, starts_on FROM subscriptions
                               GROUP BY tenant_id, starts_on HAVING COUNT(*) > 1))
  FROM dual
"""

# sp_change_plan, re-expressed. The cursor's population (ends_on IS NULL AND starts_on <
# p_effective_on — strictly less than), the per-row close-out
# (ends_on = p_effective_on - 1, status_cd = DECODE(r.status_cd, 30, 30, 10)) and the row the
# EXECUTE IMMEDIATE inserts, keyed by the source's own pkg_ow_util.f_md5_uuid. Nothing is updated:
# the procedure's *result* is projected, per request, by Oracle.
CHANGE_PLAN_SQL = """
WITH req AS (
    SELECT jt.tenant_id, jt.plan_id, TO_DATE(jt.effective_on, 'YYYY-MM-DD') AS effective_on
      FROM JSON_TABLE(:requests, '$[*]'
               COLUMNS (tenant_id VARCHAR2(36) PATH '$.tenant_id',
                        plan_id VARCHAR2(36) PATH '$.plan_id',
                        effective_on VARCHAR2(10) PATH '$.effective_on')) jt
),
closed AS (
    SELECT s.id, s.tenant_id, s.plan_id, s.starts_on, s.status_cd AS status_before,
           r.effective_on, r.plan_id AS change_plan_id,
           r.effective_on - 1 AS new_ends_on,
           DECODE(s.status_cd, 30, 30, 10) AS new_status_cd
      FROM subscriptions s, req r
     WHERE s.tenant_id = r.tenant_id
       AND s.ends_on IS NULL
       AND s.starts_on < r.effective_on
),
newrow AS (
    SELECT pkg_ow_util.f_md5_uuid(
               r.tenant_id || r.plan_id || TO_CHAR(r.effective_on, 'YYYY-MM-DD')) AS id,
           r.tenant_id, r.plan_id, r.effective_on AS starts_on, 10 AS status_cd
      FROM req r
)
SELECT 'closed' AS kind, c.id, c.tenant_id, c.plan_id,
       TO_CHAR(c.starts_on, 'YYYY-MM-DD HH24:MI:SS') AS starts_on,
       TO_CHAR(c.new_ends_on, 'YYYY-MM-DD HH24:MI:SS') AS ends_on,
       c.status_before, c.new_status_cd AS status_cd,
       TO_CHAR(c.effective_on, 'YYYY-MM-DD HH24:MI:SS') AS effective_on,
       c.change_plan_id
  FROM closed c
UNION ALL
SELECT 'inserted', n.id, n.tenant_id, n.plan_id,
       TO_CHAR(n.starts_on, 'YYYY-MM-DD HH24:MI:SS'), NULL, NULL, n.status_cd,
       TO_CHAR(n.starts_on, 'YYYY-MM-DD HH24:MI:SS'), n.plan_id
  FROM newrow n
 ORDER BY 3, 5, 2
"""

# The end state of SUBSCRIPTIONS for the requested tenants, as the procedure would leave it:
# untouched rows, closed rows with their new values, and the inserted row. This is what the
# PLANS-004/005 transcripts pin.
CHANGE_PLAN_END_STATE_SQL = """
WITH req AS (
    SELECT jt.tenant_id, jt.plan_id, TO_DATE(jt.effective_on, 'YYYY-MM-DD') AS effective_on
      FROM JSON_TABLE(:requests, '$[*]'
               COLUMNS (tenant_id VARCHAR2(36) PATH '$.tenant_id',
                        plan_id VARCHAR2(36) PATH '$.plan_id',
                        effective_on VARCHAR2(10) PATH '$.effective_on')) jt
),
closed AS (
    SELECT s.id, r.effective_on - 1 AS new_ends_on,
           DECODE(s.status_cd, 30, 30, 10) AS new_status_cd
      FROM subscriptions s, req r
     WHERE s.tenant_id = r.tenant_id
       AND s.ends_on IS NULL
       AND s.starts_on < r.effective_on
)
SELECT tenant_id, id, plan_id, starts_on, ends_on, status_cd, origin FROM (
    SELECT s.tenant_id, s.id, s.plan_id,
           TO_CHAR(s.starts_on, 'YYYY-MM-DD HH24:MI:SS') AS starts_on,
           TO_CHAR(NVL(c.new_ends_on, s.ends_on), 'YYYY-MM-DD HH24:MI:SS') AS ends_on,
           NVL(c.new_status_cd, s.status_cd) AS status_cd,
           CASE WHEN c.id IS NULL THEN 'unchanged' ELSE 'closed' END AS origin,
           s.starts_on AS ord
      FROM subscriptions s, closed c, req r
     WHERE c.id (+) = s.id
       AND s.tenant_id = r.tenant_id
    UNION ALL
    SELECT r.tenant_id,
           pkg_ow_util.f_md5_uuid(
               r.tenant_id || r.plan_id || TO_CHAR(r.effective_on, 'YYYY-MM-DD')),
           r.plan_id, TO_CHAR(r.effective_on, 'YYYY-MM-DD HH24:MI:SS'), NULL, 10, 'inserted',
           r.effective_on
      FROM req r
)
 ORDER BY tenant_id, ord, id
"""

# The re-apply exposure of item 7: the id the second call would insert already exists, and the
# INSERT has no DUP_VAL_ON_INDEX handler, so the close-outs commit and then ORA-00001 raises.
REAPPLY_SQL = """
WITH req AS (
    SELECT jt.tenant_id, jt.plan_id, TO_DATE(jt.effective_on, 'YYYY-MM-DD') AS effective_on
      FROM JSON_TABLE(:requests, '$[*]'
               COLUMNS (tenant_id VARCHAR2(36) PATH '$.tenant_id',
                        plan_id VARCHAR2(36) PATH '$.plan_id',
                        effective_on VARCHAR2(10) PATH '$.effective_on')) jt
)
SELECT COUNT(*) AS requests,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM subscriptions s
                              WHERE s.id = pkg_ow_util.f_md5_uuid(
                                  r.tenant_id || r.plan_id
                                  || TO_CHAR(r.effective_on, 'YYYY-MM-DD')))
                THEN 1 ELSE 0 END) AS ids_already_present
  FROM req r
"""

# Dialect probes, over dual: the source engine's own answers for the expressions the port had to
# translate. Read-only and independent of the seeded data.
DIALECT_SQL = """
SELECT TO_CHAR(TO_DATE('31-DEC-99', 'DD-MON-YY'), 'YYYY-MM-DD') AS sentinel,
       CASE WHEN GREATEST(CAST(NULL AS DATE), TO_DATE(:p_on, 'YYYY-MM-DD')) IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS greatest_null,
       DECODE(NULL, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS decode_null_tier,
       DECODE(4, 1, 'starter', 2, 'growth', 3, 'scale', 'UNKNOWN') AS decode_unmapped_tier,
       DECODE(30, 10, 'active', 20, 'suspended', 30, 'cancelled', 'UNKNOWN') AS decode_cancelled,
       DECODE(30, 30, 30, 10) AS closeout_status_cancelled,
       DECODE(20, 30, 30, 10) AS closeout_status_suspended,
       DECODE(10, 30, 30, 10) AS closeout_status_active,
       TO_CHAR(TO_DATE(:eff, 'YYYY-MM-DD') - 1, 'YYYY-MM-DD HH24:MI:SS') AS eff_minus_one,
       TO_CHAR(TO_DATE('2026-03-01 06:30:00', 'YYYY-MM-DD HH24:MI:SS') - 1,
               'YYYY-MM-DD HH24:MI:SS') AS eff_minus_one_with_time,
       CASE WHEN NVL(NULL, 'N') = 'Y' THEN 'listed' ELSE 'not listed' END AS null_active_yn
  FROM dual
"""

# ACC-MERGE-KEY: the target's key derivation is compared against the source function itself.
SAMPLE_KEYS_SQL = """
SELECT r.tenant_id, r.plan_id, TO_CHAR(r.effective_on, 'YYYY-MM-DD') AS effective_on,
       pkg_ow_util.f_md5_uuid(
           r.tenant_id || r.plan_id || TO_CHAR(r.effective_on, 'YYYY-MM-DD')) AS new_subscription_id
  FROM (SELECT jt.tenant_id, jt.plan_id, TO_DATE(jt.effective_on, 'YYYY-MM-DD') AS effective_on
          FROM JSON_TABLE(:requests, '$[*]'
                   COLUMNS (tenant_id VARCHAR2(36) PATH '$.tenant_id',
                            plan_id VARCHAR2(36) PATH '$.plan_id',
                            effective_on VARCHAR2(10) PATH '$.effective_on')) jt) r
 ORDER BY r.tenant_id
"""


def oracle_source_sha() -> str:
    """Same recipe as procs/harness/oracle_record.py:oracle_source_sha()."""
    digest = hashlib.sha256()
    for path in sorted(ORACLE_DB_DIR.rglob("*.sql")):
        digest.update(str(path.relative_to(ORACLE_DB_DIR)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _number_handler(cursor, name, default_type, size, precision, scale):
    """Every NUMBER comes back as an exact Decimal: no float ever touches money."""
    if default_type == oracledb.DB_TYPE_NUMBER:
        return cursor.var(decimal.Decimal, arraysize=cursor.arraysize)
    return None


def _required_env(name: str) -> str:
    """Credentials come from the environment by name; this file never carries a value."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set: export the OW_BILLING credential named {name} "
            f"(see .migration/07_access_checklist.md) before running the recon"
        )
    return value


def connect():
    return oracledb.connect(
        user=_required_env("DB_USER"),
        password=_required_env("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "52521")),
        service_name=os.getenv("DB_SERVICE", "FREEPDB1"),
        tcp_connect_timeout=10,
    )


def money(value) -> str | None:
    if value is None:
        return None
    return str(decimal.Decimal(value).quantize(decimal.Decimal("0.01")))


def count(value) -> str | None:
    if value is None:
        return None
    return str(decimal.Decimal(value).quantize(decimal.Decimal("1")))


def rate(value) -> str | None:
    if value is None:
        return None
    return str(decimal.Decimal(value).quantize(decimal.Decimal("0.000001")))


def _rows(cur, sql: str, **binds) -> list[tuple]:
    cur.execute(sql, binds) if binds else cur.execute(sql)
    return cur.fetchall()


# The spec's request-derivation rule, evaluated on the source: one request per tenant whose cursor
# finds a covering subscription, for the next plan after the tenant's covering plan in fn_list_plans
# order, cyclically. The notebook derives the same set from bronze and the recon compares the two.
DERIVE_REQUESTS_SQL = """
WITH prm AS (SELECT TO_DATE(:p_on, 'YYYY-MM-DD') AS p_on FROM dual),
listed AS (
    SELECT p.id,
           ROW_NUMBER() OVER (ORDER BY p.monthly_fee, p.code) AS seq,
           COUNT(*) OVER () AS n
      FROM plans p
     WHERE NVL(p.active_yn, 'N') = 'Y'
),
covering AS (
    SELECT tenant_id, plan_id
      FROM (SELECT t.id AS tenant_id, s.plan_id,
                   ROW_NUMBER() OVER (PARTITION BY t.id
                                      ORDER BY s.starts_on DESC, s.id DESC) AS rn
              FROM tenants t, subscriptions s, prm
             WHERE s.tenant_id = t.id
               AND s.starts_on <= prm.p_on
               AND (s.ends_on IS NULL OR s.ends_on >= prm.p_on))
     WHERE rn = 1
)
SELECT c.tenant_id, nxt.id AS plan_id
  FROM covering c, listed cur, listed nxt
 WHERE cur.id = c.plan_id
   AND nxt.seq = MOD(cur.seq, cur.n) + 1
 ORDER BY c.tenant_id
"""


def derive_requests(entitlement_on: str, effective_on: str, overrides: list[dict]) -> list[dict]:
    """The run's sp_change_plan request population, derived from the source by the spec's rule.

    Read-only. `overrides` are the transcript-pinned requests, which replace the derived request
    for their tenant; a tenant with no covering subscription gets no request either way.
    """
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")
        derived = [
            {"tenant_id": r[0], "plan_id": r[1], "effective_on": effective_on}
            for r in _rows(cur, DERIVE_REQUESTS_SQL, p_on=entitlement_on)
        ]
        conn.rollback()
    covered = {r["tenant_id"] for r in derived}
    pinned = [
        {
            "tenant_id": o["tenant_id"],
            "plan_id": o["plan_id"],
            "effective_on": o["effective_on"],
            "pinned_by_transcript": o["transcript"],
        }
        for o in overrides
        if o["tenant_id"] in covered
    ]
    pinned_tenants = {r["tenant_id"] for r in pinned}
    rest = [
        {**r, "pinned_by_transcript": None} for r in derived if r["tenant_id"] not in pinned_tenants
    ]
    return sorted(pinned + rest, key=lambda r: (r["tenant_id"], r["effective_on"]))


def snapshot(entitlement_on: str, requests: list[dict]) -> dict:
    """One read-only session: counts, fn_list_plans, fn_entitlement, and sp_change_plan's result.

    `requests` is the run's declared plan-change population,
    `[{"tenant_id": ..., "plan_id": ..., "effective_on": "YYYY-MM-DD"}]`, evaluated here by Oracle
    without touching a row.
    """
    req_json = json.dumps(
        [
            {
                "tenant_id": r["tenant_id"],
                "plan_id": r["plan_id"],
                "effective_on": r["effective_on"],
            }
            for r in requests
        ]
    )
    effective_dates = sorted({r["effective_on"] for r in requests})
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        # '31-DEC-99' is month-name parsing: the sentinel must not depend on the session language.
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")

        counts = _rows(cur, COUNTS_SQL)[0]
        source_counts = dict(
            zip(
                ("tenants", "plans", "subscriptions", "usage_events", "codes"),
                (int(c) for c in counts),
            )
        )

        list_plans = [
            {
                "list_seq": int(r[0]),
                "id": r[1],
                "code": r[2],
                "tier_cd": None if r[3] is None else int(r[3]),
                "tier": r[4],
                "monthly_fee": money(r[5]),
                "included_units": count(r[6]),
                "overage_rate": rate(r[7]),
            }
            for r in _rows(cur, LIST_PLANS_SQL)
        ]
        all_plans = [
            {
                "id": r[0],
                "code": r[1],
                "tier_cd": None if r[2] is None else int(r[2]),
                "tier": r[3],
                "monthly_fee": money(r[4]),
                "included_units": count(r[5]),
                "overage_rate": rate(r[6]),
                "active_yn": r[7],
                "active_nvl": r[8],
                "listed_by_fn_list_plans": bool(int(r[9])),
            }
            for r in _rows(cur, ALL_PLANS_SQL)
        ]
        all_subs = [
            {
                "id": r[0],
                "tenant_id": r[1],
                "plan_id": r[2],
                "starts_on": r[3],
                "ends_on": r[4],
                "status_cd": None if r[5] is None else int(r[5]),
                "suspended_on": r[6],
            }
            for r in _rows(cur, ALL_SUBS_SQL)
        ]

        entitlements = {}
        for r in _rows(cur, ENTITLEMENT_SQL, p_on=entitlement_on):
            entitlements[r[0]] = {
                "tenant_id": r[0],
                "subscription_id": r[1],
                "plan_id": r[2],
                "plan_code": r[3],
                "tier": r[4],
                "monthly_fee": money(r[5]),
                "included_units": count(r[6]),
                "subscription_status": r[7],
                "status_cd": None if r[8] is None else int(r[8]),
                "effective_on": r[9],
                "starts_on": r[10],
                "ends_on": r[11],
                "candidate_rows": int(r[12]),
                "tied_starts_on_rows": int(r[13]),
                "cursor_predicate_covers": bool(int(r[14])),
                "sentinel_predicate_covers": bool(int(r[15])),
                "plan_null_extended": r[2] is not None and r[3] is None,
            }

        global_walk = [
            {
                "tenant_id": r[0],
                "global_iteration_seq": int(r[1]),
                "global_lookup_matched": bool(int(r[2])),
                "global_lookup_plan_code": r[3],
                "global_lookup_candidate_rows": int(r[4]),
                "stale_global_plan_code": r[5],
                "stale_global_mismatch": bool(int(r[6])),
            }
            for r in _rows(cur, GLOBAL_WALK_SQL, p_on=entitlement_on)
        ]

        pop = _rows(cur, PREDICATE_POP_SQL, p_on=entitlement_on)[0]
        populations = {
            "tenants": int(pop[0]),
            "tenants_covered_sentinel_predicate": int(pop[1]),
            "tenants_covered_cursor_predicate": int(pop[2]),
            "subscription_rows_where_the_two_predicates_disagree": int(pop[3]),
            "subscriptions_with_a_missing_plan_row": int(pop[4]),
            "subscriptions_with_a_null_ends_on": int(pop[5]),
            "tenant_starts_on_groups_with_a_tie": int(pop[6]),
        }

        change_rows = [
            {
                "kind": r[0],
                "id": r[1],
                "tenant_id": r[2],
                "plan_id": r[3],
                "starts_on": r[4],
                "ends_on": r[5],
                "status_cd_before": None if r[6] is None else int(r[6]),
                "status_cd": None if r[7] is None else int(r[7]),
                "effective_on": r[8],
                "change_plan_id": r[9],
            }
            for r in _rows(cur, CHANGE_PLAN_SQL, requests=req_json)
        ]
        end_state = [
            {
                "tenant_id": r[0],
                "id": r[1],
                "plan_id": r[2],
                "starts_on": r[3],
                "ends_on": r[4],
                "status_cd": None if r[5] is None else int(r[5]),
                "origin": r[6],
            }
            for r in _rows(cur, CHANGE_PLAN_END_STATE_SQL, requests=req_json)
        ]
        reapply = _rows(cur, REAPPLY_SQL, requests=req_json)[0]
        sample_keys = [
            {
                "tenant_id": r[0],
                "plan_id": r[1],
                "effective_on": r[2],
                "new_subscription_id": r[3],
            }
            for r in _rows(cur, SAMPLE_KEYS_SQL, requests=req_json)
        ]

        dialect_rows = {}
        for eff in effective_dates or [entitlement_on]:
            d = _rows(cur, DIALECT_SQL, p_on=entitlement_on, eff=eff)[0]
            dialect_rows[eff] = {
                "sentinel_TO_DATE_31_DEC_99": d[0],
                "GREATEST_null_and_a_date": d[1],
                "DECODE_null_tier_cd": d[2],
                "DECODE_unmapped_tier_cd": d[3],
                "DECODE_cancelled_status": d[4],
                "closeout_status_from_30": int(d[5]),
                "closeout_status_from_20": int(d[6]),
                "closeout_status_from_10": int(d[7]),
                "effective_on_minus_one_day": d[8],
                "effective_on_with_time_minus_one_day": d[9],
                "null_active_yn_is": d[10],
            }

        banner = _rows(cur, "SELECT banner_full FROM v$version")[0][0]
        conn.rollback()

    closed_rows = [r for r in change_rows if r["kind"] == "closed"]
    change_populations = {
        "requests": int(reapply[0]),
        "subscriptions_closed_by_the_loop": len(closed_rows),
        "suspended_to_active_flips": sum(
            1 for r in closed_rows if r["status_cd_before"] == 20 and r["status_cd"] == 10
        ),
        "cancelled_subscriptions_visited": sum(
            1 for r in closed_rows if r["status_cd_before"] == 30
        ),
        "cancelled_preserved": sum(
            1 for r in closed_rows if r["status_cd_before"] == 30 and r["status_cd"] == 30
        ),
        "closeout_ends_on_carrying_a_time_component": sum(
            1 for r in closed_rows if r["ends_on"] and not r["ends_on"].endswith("00:00:00")
        ),
        "new_subscriptions": sum(1 for r in change_rows if r["kind"] == "inserted"),
        "new_ids_already_present_in_the_source": int(reapply[1] or 0),
    }
    # The strict `<` in the cursor: an open subscription starting on or after the effective date is
    # not closed and overlaps the row the procedure inserts.
    by_tenant_eff = {(r["tenant_id"], r["effective_on"]) for r in requests}
    open_subs = [s for s in all_subs if s["ends_on"] is None]
    overlap = 0
    exact = 0
    for tenant_id, eff in by_tenant_eff:
        eff_ts = f"{eff} 00:00:00"
        for s in open_subs:
            if s["tenant_id"] != tenant_id:
                continue
            if s["starts_on"] >= eff_ts:
                overlap += 1
            if s["starts_on"] == eff_ts:
                exact += 1
    change_populations["open_subscriptions_left_overlapping_by_the_strict_less_than"] = overlap
    change_populations["open_subscriptions_starting_exactly_on_the_effective_date"] = exact

    return {
        "oracle_banner": banner,
        "oracle_source_sha": oracle_source_sha(),
        "entitlement_on": entitlement_on,
        "source_counts": source_counts,
        "list_plans": list_plans,
        "all_plans": all_plans,
        "all_subscriptions": all_subs,
        "entitlements": entitlements,
        "global_walk": global_walk,
        "populations": populations,
        "change_requests": requests,
        "change_rows": change_rows,
        "change_end_state": end_state,
        "change_populations": change_populations,
        "sample_keys": sample_keys,
        "dialect": dialect_rows,
    }
