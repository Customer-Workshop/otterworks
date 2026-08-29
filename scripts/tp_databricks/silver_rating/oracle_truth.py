"""Read-only Oracle side of the silver_rating recon.

Two things are measured here and nothing is written: the rating the **source database** produces
for the population under test, and the source's own `RATING_RESULTS` rows.

The rating is obtained by re-expressing `pkg_rating.compute_rating` /
`pkg_rating.sp_finalize_rating` as one read-only SQL statement and letting **Oracle** evaluate it.
That is the point: the arithmetic that decides money — `LEAST`/`GREATEST` null propagation,
`NVL`, `ROUND` half-away-from-zero, `TO_CHAR(date,'YYYYMMDD')` string windowing, `DATE - DATE`
day arithmetic and `NUMBER` precision — is evaluated by the source engine under its own NLS
settings, so a dialect entry that Databricks and Oracle disagree about shows up as a row-level
mismatch instead of being hidden by a second Python re-implementation of the same guess.

Its limit is stated in the recon report: it is a re-expression, not the PL/SQL package itself.
The eight pinned Oracle transcripts in `procs/oracle/transcripts/rating/` are what tie this
statement to the real engine, and the batch chain is never executed against the source.
"""

from __future__ import annotations

import decimal
import hashlib
import os
import pathlib

import oracledb

ROOT = pathlib.Path(__file__).resolve().parents[3]
ORACLE_DB_DIR = ROOT / "services" / "legacy-billing" / "db" / "oracle"

# pkg_ow_util.f_md5_uuid, inlined so no package call is needed to derive a key (D-14).
F_MD5_UUID = """SUBSTR(LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5'))), 1, 8)
    || '-' || SUBSTR(LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5'))), 9, 4)
    || '-' || SUBSTR(LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5'))), 13, 4)
    || '-' || SUBSTR(LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5'))), 17, 4)
    || '-' || SUBSTR(LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5'))), 21, 12)"""

# compute_rating + sp_finalize_rating, step for step in the source's order (D-13).
RATING_SQL = f"""
WITH prm AS (
    SELECT TO_DATE(:ps, 'YYYY-MM-DD') AS ps, TO_DATE(:pe, 'YYYY-MM-DD') AS pe FROM dual
),
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
usg AS (
    SELECT u.tenant_id, SUM(NVL(u.units, 0)) AS used_units, COUNT(*) AS events_in_window
      FROM usage_events u, prm p
     WHERE TO_CHAR(u.occurred_at, 'YYYYMMDD') >= TO_CHAR(p.ps, 'YYYYMMDD')
       AND TO_CHAR(u.occurred_at, 'YYYYMMDD') <= TO_CHAR(p.pe, 'YYYYMMDD')
     GROUP BY u.tenant_id
),
pri AS (
    SELECT rp.tenant_id, SUM(NVL(rr.rollover_units, 0)) AS prior_units
      FROM rating_results rr, rating_periods rp, prm p
     WHERE rp.id = rr.period_id
       AND rp.period_start < p.ps
       AND rp.period_start >= ADD_MONTHS(p.ps, -3)
     GROUP BY rp.tenant_id
),
base AS (
    SELECT t.id AS tenant_id, s.id AS sub_id, s.status_cd, s.suspended_on,
           NVL(s.cand_rows, 0) AS cand_rows, NVL(s.tied_rows, 0) AS tied_rows,
           pl.included_units AS v_included, pl.overage_rate AS v_rate,
           NVL(u.used_units, 0) AS used_units, NVL(u.events_in_window, 0) AS events_in_window,
           NVL(pr.prior_units, 0) AS prior_units, p.ps, p.pe
      FROM tenants t
     CROSS JOIN prm p
      LEFT JOIN sub_pick s ON s.tenant_id = t.id
      LEFT JOIN plans pl ON pl.id = s.plan_id
      LEFT JOIN usg u ON u.tenant_id = t.id
      LEFT JOIN pri pr ON pr.tenant_id = t.id
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
    SELECT b.*, LEAST(billable_pre, 101) AS first_tier, GREATEST(billable_pre - 101, 0) AS second_tier
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
                ELSE overage_pre END AS overage_amount
      FROM priced p
)
SELECT tenant_id,
       {F_MD5_UUID.format(x="tenant_id || TO_CHAR(ps, 'YYYY-MM-DD')")} AS period_id,
       sub_id, cand_rows, tied_rows, events_in_window,
       v_rate, quota_units, used_units, computed_rollover,
       GREATEST(quota_units - used_units, 0) AS persisted_rollover,
       first_tier, second_tier, billable_units, overage_amount, suspended_flag
  FROM prorated
 ORDER BY tenant_id
"""

EXISTING_RESULTS_SQL = """
SELECT rr.id, rr.period_id, rr.subscription_id, rr.used_units, rr.quota_units,
       rr.rollover_units, rr.billable_units, rr.overage_amount,
       TO_CHAR(rr.created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
       rp.tenant_id, TO_CHAR(rp.period_start, 'YYYY-MM-DD') AS period_start,
       TO_CHAR(rp.period_end, 'YYYY-MM-DD') AS period_end
  FROM rating_results rr, rating_periods rp
 WHERE rp.id = rr.period_id
 ORDER BY rp.tenant_id, rp.period_start
"""

EXISTING_PERIODS_SQL = """
SELECT id, tenant_id, TO_CHAR(period_start, 'YYYY-MM-DD') AS period_start,
       TO_CHAR(period_end, 'YYYY-MM-DD') AS period_end
  FROM rating_periods
 ORDER BY tenant_id, period_start
"""

COUNTS_SQL = """
SELECT (SELECT COUNT(*) FROM tenants),
       (SELECT COUNT(*) FROM subscriptions),
       (SELECT COUNT(*) FROM plans),
       (SELECT COUNT(*) FROM usage_events),
       (SELECT COUNT(*) FROM rating_periods),
       (SELECT COUNT(*) FROM rating_results),
       (SELECT COUNT(*) FROM customer_master),
       (SELECT COUNT(*) FROM invoice_line)
  FROM dual
"""

# ACC-MERGE-KEY: the target's key derivation is asserted against the source function itself, not
# against a second copy of the formula.
SAMPLE_KEYS_SQL = """
SELECT t.id,
       pkg_ow_util.f_md5_uuid(t.id || TO_CHAR(TO_DATE(:ps, 'YYYY-MM-DD'), 'YYYY-MM-DD')) AS period_id,
       pkg_ow_util.f_md5_uuid(
           pkg_ow_util.f_md5_uuid(t.id || TO_CHAR(TO_DATE(:ps, 'YYYY-MM-DD'), 'YYYY-MM-DD'))
       ) AS result_id
  FROM (SELECT id FROM tenants ORDER BY id) t
 WHERE ROWNUM <= 10
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


def snapshot(period_start: str, period_end: str) -> dict:
    """One read-only session: source counts, the rating Oracle computes, and its stored rows."""
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")

        counts = _rows(cur, COUNTS_SQL)[0]
        source_counts = dict(
            zip(
                (
                    "tenants",
                    "subscriptions",
                    "plans",
                    "usage_events",
                    "rating_periods",
                    "rating_results",
                    "customer_master",
                    "invoice_line",
                ),
                (int(c) for c in counts),
            )
        )

        rating = {}
        for r in _rows(cur, RATING_SQL, ps=period_start, pe=period_end):
            rating[r[0]] = {
                "tenant_id": r[0],
                "period_id": r[1],
                "subscription_id": r[2],
                "subscription_candidates": int(r[3]),
                "subscription_tied_rows": int(r[4]),
                "usage_events_in_window": int(r[5]),
                "overage_rate": rate(r[6]),
                "quota_units": count(r[7]),
                "used_units": count(r[8]),
                "computed_rollover_units": count(r[9]),
                "rollover_units": count(r[10]),
                "first_tier_units": count(r[11]),
                "second_tier_units": count(r[12]),
                "billable_units": count(r[13]),
                "overage_amount": money(r[14]),
                "suspension_prorated": bool(int(r[15])),
            }

        existing_results = [
            {
                "id": r[0],
                "period_id": r[1],
                "subscription_id": r[2],
                "used_units": count(r[3]),
                "quota_units": count(r[4]),
                "rollover_units": count(r[5]),
                "billable_units": count(r[6]),
                "overage_amount": money(r[7]),
                "created_at": r[8],
                "tenant_id": r[9],
                "period_start": r[10],
                "period_end": r[11],
            }
            for r in _rows(cur, EXISTING_RESULTS_SQL)
        ]
        existing_periods = [
            {"id": r[0], "tenant_id": r[1], "period_start": r[2], "period_end": r[3]}
            for r in _rows(cur, EXISTING_PERIODS_SQL)
        ]
        sample_keys = [
            {"tenant_id": r[0], "period_id": r[1], "result_id": r[2]}
            for r in _rows(cur, SAMPLE_KEYS_SQL, ps=period_start)
        ]
        banner = _rows(cur, "SELECT banner_full FROM v$version")[0][0]
        conn.rollback()

    return {
        "oracle_banner": banner,
        "source_counts": source_counts,
        "rating": rating,
        "existing_results": existing_results,
        "existing_periods": existing_periods,
        "sample_keys": sample_keys,
        "oracle_source_sha": oracle_source_sha(),
    }
