"""Read-only Oracle side of the silver_dunning recon.

`pkg_dunning.fn_overdue_accounts` is a function over a `SYS_REFCURSOR`, so it is **called for real**
here and its rows are what the parity comparison uses. `sp_schedule_dunning` and `sp_suspend_overdue`
mutate `DUNNING_ATTEMPTS`, `TENANTS`, `SUBSCRIPTIONS` and `NOTIFICATIONS`, so they are never called:
each is re-expressed as read-only SQL and evaluated by **Oracle**, the same way waves 1-3 handled
their procedures. That limit is stated in the recon report's `unverified_paths`, and the five pinned
transcripts in `procs/oracle/transcripts/dunning/` are what tie these statements to the real engine.

Letting the source engine evaluate the re-expression is the point. The behaviours that decide the
answer — `TO_CHAR(dt,'DY','NLS_DATE_LANGUAGE=ENGLISH')` against `'SAT'`/`'SUN'` in a `DECODE`,
`TO_CHAR(...,'YYYYMMDD')` string comparison on truncated dates, `t.id (+) = i.tenant_id`'s
invoice-preserving direction, `DECODE`'s null-safe equality, `TRUNC(p_as_of) - TRUNC(CAST(issued_at
AS DATE))` day arithmetic, `NVL(MAX(attempt_no),0)+1` per invoice, and
`pkg_ow_util.f_md5_uuid(invoice_id || TO_CHAR(attempt_no))` — are evaluated under Oracle's own NLS
settings rather than re-guessed in Python.

The session is opened with autocommit off and rolled back on the way out. The only PL/SQL called is
`pkg_dunning.fn_overdue_accounts` (which opens a cursor) and `pkg_ow_util.f_md5_uuid` (which reads
`dual`); neither writes a table. `pkg_ow_util.log_msg`'s autonomous `BILLING_AUDIT_LOG` write is out
of scope per D-20 and is never triggered from here.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import os
import pathlib

import oracledb

ROOT = pathlib.Path(__file__).resolve().parents[3]
ORACLE_DB_DIR = ROOT / "services" / "legacy-billing" / "db" / "oracle"

BANNER_SQL = "SELECT banner FROM v$version WHERE ROWNUM = 1"

COUNTS_SQL = """
SELECT (SELECT COUNT(*) FROM tenants),
       (SELECT COUNT(*) FROM invoices),
       (SELECT COUNT(*) FROM invoices WHERE status_cd = 40),
       (SELECT COUNT(*) FROM subscriptions),
       (SELECT COUNT(*) FROM dunning_attempts),
       (SELECT COUNT(*) FROM notifications),
       (SELECT COUNT(*) FROM notifications WHERE kind_cd = 3),
       (SELECT COUNT(*) FROM codes)
  FROM dual
"""

# The source rows the target's own populations are reconciled against, one query per owned table.
ATTEMPTS_SQL = """
SELECT a.id, a.tenant_id, a.invoice_id, a.attempt_no,
       TO_CHAR(a.scheduled_for, 'YYYY-MM-DD') AS scheduled_for, a.status_cd,
       (SELECT c.code_desc FROM codes c
         WHERE c.code_type = 'DUN_STATUS' AND c.code_val = a.status_cd) AS status
  FROM dunning_attempts a
 ORDER BY a.invoice_id, a.attempt_no
"""

NOTIFICATIONS_SQL = """
SELECT n.id, n.tenant_id, n.kind_cd,
       TO_CHAR(n.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
       (SELECT c.code_desc FROM codes c
         WHERE c.code_type = 'NOTIF_KIND' AND c.code_val = n.kind_cd) AS kind
  FROM notifications n
 ORDER BY n.tenant_id, n.kind_cd, n.sent_at
"""

TENANTS_SQL = """
SELECT t.id, t.status_cd,
       DECODE(t.status_cd, 10, 'active', 20, 'suspended', 'UNKNOWN') AS tenant_status,
       (SELECT c.code_desc FROM codes c
         WHERE c.code_type = 'TENANT_STATUS' AND c.code_val = t.status_cd) AS status
  FROM tenants t
 ORDER BY t.id
"""

SUBSCRIPTIONS_SQL = """
SELECT s.id, s.tenant_id, s.plan_id, s.status_cd,
       TO_CHAR(s.starts_on, 'YYYY-MM-DD') AS starts_on,
       TO_CHAR(s.ends_on, 'YYYY-MM-DD') AS ends_on,
       TO_CHAR(s.suspended_on, 'YYYY-MM-DD') AS suspended_on
  FROM subscriptions s
 ORDER BY s.id
"""

# sp_schedule_dunning, re-expressed. The cursor carries no date filter at all — status_cd = 40 and
# ORDER BY issued_at, id — and the attempt number is the loop's own
# SELECT NVL(MAX(attempt_no),0)+1 ... WHERE invoice_id = inv.id, evaluated per invoice against the
# state the loop starts from. `id_exists` and `uq_exists` are what the INSERT would raise ORA-00001
# on and WHEN OTHERS THEN NULL would then hide, leaving g_scheduled_cnt short of the loop count.
SCHEDULE_EXPECT_SQL = """
WITH prm AS (SELECT TRUNC(TO_DATE(:as_of, 'YYYY-MM-DD')) AS as_of FROM dual),
shifted AS (
    SELECT prm.as_of,
           TO_CHAR(prm.as_of, 'DY', 'NLS_DATE_LANGUAGE=ENGLISH') AS dow,
           prm.as_of + DECODE(TO_CHAR(prm.as_of, 'DY', 'NLS_DATE_LANGUAGE=ENGLISH'),
                              'SAT', 2, 'SUN', 1, 0) AS next_dt
      FROM prm
),
drv AS (
    SELECT i.id AS invoice_id, i.tenant_id, i.total, i.issued_at,
           ROW_NUMBER() OVER (ORDER BY i.issued_at, i.id) AS loop_seq,
           (SELECT NVL(MAX(a.attempt_no), 0) + 1 FROM dunning_attempts a
             WHERE a.invoice_id = i.id) AS attempt_no
      FROM invoices i
     WHERE i.status_cd = 40
)
SELECT drv.loop_seq, drv.invoice_id, drv.tenant_id, drv.attempt_no,
       pkg_ow_util.f_md5_uuid(drv.invoice_id || TO_CHAR(drv.attempt_no)) AS id,
       TO_CHAR(shifted.next_dt, 'YYYY-MM-DD') AS scheduled_for,
       TO_CHAR(shifted.as_of, 'YYYY-MM-DD') AS unshifted_scheduled_for,
       shifted.dow AS source_day_of_week,
       shifted.next_dt - shifted.as_of AS weekend_shift_days,
       10 AS status_cd,
       drv.total AS invoice_total,
       TO_CHAR(drv.issued_at, 'YYYY-MM-DD HH24:MI:SS') AS invoice_issued_at,
       TRUNC(shifted.as_of) - TRUNC(CAST(drv.issued_at AS DATE)) AS days_overdue,
       CASE WHEN TO_CHAR(drv.issued_at, 'YYYYMMDD')
                 < TO_CHAR(shifted.as_of, 'YYYYMMDD') THEN 1 ELSE 0 END AS overdue_by_fn,
       (SELECT COUNT(*) FROM dunning_attempts a
         WHERE a.id = pkg_ow_util.f_md5_uuid(drv.invoice_id || TO_CHAR(drv.attempt_no)))
         AS id_exists,
       (SELECT COUNT(*) FROM dunning_attempts a
         WHERE a.invoice_id = drv.invoice_id AND a.attempt_no = drv.attempt_no) AS uq_exists,
       (SELECT COUNT(*) FROM tenants t WHERE t.id = drv.tenant_id) AS tenant_rows,
       DECODE((SELECT t.status_cd FROM tenants t WHERE t.id = drv.tenant_id),
              10, 'active', 20, 'suspended', 'UNKNOWN') AS tenant_status
  FROM drv, shifted
 ORDER BY drv.loop_seq
"""

# sp_suspend_overdue, re-expressed. The driver is the DISTINCT tenant_id of the inclusive 14-day cut,
# `is_active` is the IF v_active > 0 gate, and the notification's id and NOT EXISTS predicate are
# evaluated as the source writes them. Nothing is updated.
SUSPEND_EXPECT_SQL = """
WITH prm AS (SELECT TRUNC(TO_DATE(:as_of, 'YYYY-MM-DD')) AS as_of FROM dual),
drv AS (
    SELECT DISTINCT i.tenant_id
      FROM invoices i, prm
     WHERE i.status_cd = 40
       AND TO_CHAR(i.issued_at, 'YYYYMMDD') <= TO_CHAR(prm.as_of - 14, 'YYYYMMDD')
)
SELECT drv.tenant_id,
       (SELECT COUNT(*) FROM tenants t WHERE t.id = drv.tenant_id) AS tenant_rows,
       (SELECT COUNT(*) FROM tenants t
         WHERE t.id = drv.tenant_id AND t.status_cd = 10) AS is_active,
       (SELECT t.status_cd FROM tenants t WHERE t.id = drv.tenant_id) AS tenant_status_cd_before,
       (SELECT COUNT(*) FROM subscriptions s
         WHERE s.tenant_id = drv.tenant_id AND s.status_cd = 10) AS subs_at_10,
       (SELECT COUNT(*) FROM subscriptions s
         WHERE s.tenant_id = drv.tenant_id AND s.status_cd = 20) AS subs_at_20,
       (SELECT COUNT(*) FROM subscriptions s
         WHERE s.tenant_id = drv.tenant_id AND s.status_cd = 30) AS subs_at_30,
       pkg_ow_util.f_md5_uuid(drv.tenant_id || 'suspension' ||
           TO_CHAR(prm.as_of, 'YYYY-MM-DD')) AS notification_id,
       TO_CHAR(CAST(prm.as_of AS TIMESTAMP), 'YYYY-MM-DD HH24:MI:SS') AS notification_sent_at,
       TO_CHAR(prm.as_of, 'YYYY-MM-DD') AS suspended_on,
       (SELECT COUNT(*) FROM notifications n
         WHERE n.tenant_id = drv.tenant_id AND n.kind_cd = 3
           AND n.sent_at = CAST(prm.as_of AS TIMESTAMP)) AS notification_exists
  FROM drv, prm
 ORDER BY drv.tenant_id
"""

# The subscription rows the sweep's UPDATE would match, so the shared-table population the target
# MERGEs is compared against the source's own set rather than against the target's opinion of it.
SUSPEND_SUBS_SQL = """
WITH prm AS (SELECT TRUNC(TO_DATE(:as_of, 'YYYY-MM-DD')) AS as_of FROM dual),
drv AS (
    SELECT DISTINCT i.tenant_id
      FROM invoices i, prm
     WHERE i.status_cd = 40
       AND TO_CHAR(i.issued_at, 'YYYYMMDD') <= TO_CHAR(prm.as_of - 14, 'YYYYMMDD')
)
SELECT s.id, s.tenant_id, s.status_cd AS status_cd_before,
       TO_CHAR(s.suspended_on, 'YYYY-MM-DD') AS suspended_on_before,
       20 AS status_cd_after, TO_CHAR(prm.as_of, 'YYYY-MM-DD') AS suspended_on_after
  FROM subscriptions s, drv, prm
 WHERE s.tenant_id = drv.tenant_id
   AND s.status_cd = 10
   AND EXISTS (SELECT 1 FROM tenants t WHERE t.id = drv.tenant_id AND t.status_cd = 10)
 ORDER BY s.id
"""

# Every population the brief requires measured rather than assumed, on the live source.
POPULATIONS_SQL = """
WITH prm AS (SELECT TRUNC(TO_DATE(:as_of, 'YYYY-MM-DD')) AS as_of FROM dual)
SELECT (SELECT COUNT(*) FROM invoices i WHERE i.status_cd = 40) AS overdue_invoices,
       (SELECT COUNT(*) FROM invoices i, prm
         WHERE i.status_cd = 40
           AND TO_CHAR(i.issued_at, 'YYYYMMDD') < TO_CHAR(prm.as_of, 'YYYYMMDD'))
         AS overdue_by_fn,
       (SELECT COUNT(*) FROM invoices i, prm
         WHERE i.status_cd = 40
           AND TO_CHAR(i.issued_at, 'YYYYMMDD') = TO_CHAR(prm.as_of, 'YYYYMMDD'))
         AS same_calendar_day_invoices,
       (SELECT COUNT(*) FROM invoices i
         WHERE i.status_cd = 40
           AND NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = i.tenant_id))
         AS overdue_invoices_with_no_tenant_row,
       (SELECT COUNT(*) FROM invoices i
         WHERE i.status_cd = 40
           AND DECODE((SELECT t.status_cd FROM tenants t WHERE t.id = i.tenant_id),
                      10, 'active', 20, 'suspended', 'UNKNOWN') = 'UNKNOWN')
         AS overdue_invoices_with_unknown_tenant_status,
       (SELECT COUNT(*) FROM tenants t WHERE t.status_cd = 10) AS tenants_at_10,
       (SELECT COUNT(*) FROM tenants t WHERE t.status_cd = 20) AS tenants_at_20,
       (SELECT COUNT(*) FROM tenants t
         WHERE DECODE(t.status_cd, 10, 'active', 20, 'suspended', 'UNKNOWN') = 'UNKNOWN')
         AS tenants_with_unknown_status,
       (SELECT COUNT(*) FROM subscriptions s WHERE s.status_cd = 10) AS subscriptions_at_10,
       (SELECT COUNT(*) FROM subscriptions s WHERE s.status_cd = 20) AS subscriptions_at_20,
       (SELECT COUNT(*) FROM subscriptions s WHERE s.status_cd = 30) AS subscriptions_at_30,
       (SELECT COUNT(*) FROM dunning_attempts a
         WHERE NOT EXISTS (SELECT 1 FROM codes c
                            WHERE c.code_type = 'DUN_STATUS' AND c.code_val = a.status_cd))
         AS attempts_with_unknown_status_cd,
       (SELECT COALESCE(TO_CHAR(SUM(i.total)), '0') FROM invoices i WHERE i.status_cd = 40)
         AS overdue_total,
       (SELECT COUNT(*) FROM invoices i WHERE i.status_cd = 40 AND i.total IS NULL)
         AS overdue_total_null_rows
  FROM dual
"""

# What a *different* p_as_of adds for a tenant the sweep has already suspended: the notification's
# NOT EXISTS is keyed on (tenant_id, kind_cd, sent_at), so the same night adds nothing, while
# another night's TRUNC(p_as_of) is a different sent_at and a second row. Only tenants still at
# status_cd = 10 are reached, because the sweep's own UPDATE takes the ones it suspends out.
MULTIDATE_NOTIFICATION_SQL = """
WITH prm AS (SELECT TRUNC(TO_DATE(:as_of, 'YYYY-MM-DD')) AS as_of,
                    TRUNC(TO_DATE(:other_as_of, 'YYYY-MM-DD')) AS other_as_of FROM dual),
drv AS (
    SELECT DISTINCT i.tenant_id, prm.as_of, prm.other_as_of
      FROM invoices i, prm
     WHERE i.status_cd = 40
       AND TO_CHAR(i.issued_at, 'YYYYMMDD') <= TO_CHAR(prm.other_as_of - 14, 'YYYYMMDD')
)
SELECT drv.tenant_id,
       (SELECT COUNT(*) FROM tenants t
         WHERE t.id = drv.tenant_id AND t.status_cd = 10) AS is_active,
       (SELECT COUNT(*) FROM notifications n
         WHERE n.tenant_id = drv.tenant_id AND n.kind_cd = 3
           AND n.sent_at = CAST(drv.as_of AS TIMESTAMP)) AS has_notification_on_as_of,
       (SELECT COUNT(*) FROM notifications n
         WHERE n.tenant_id = drv.tenant_id AND n.kind_cd = 3
           AND n.sent_at = CAST(drv.other_as_of AS TIMESTAMP)) AS has_notification_on_other,
       pkg_ow_util.f_md5_uuid(drv.tenant_id || 'suspension' ||
           TO_CHAR(drv.other_as_of, 'YYYY-MM-DD')) AS other_notification_id
  FROM drv
 ORDER BY drv.tenant_id
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


def _rows(cur, sql: str, **binds) -> list[tuple]:
    cur.execute(sql, binds) if binds else cur.execute(sql)
    return cur.fetchall()


def _dicts(cur, sql: str, columns: tuple[str, ...], **binds) -> list[dict]:
    return [dict(zip(columns, r)) for r in _rows(cur, sql, **binds)]


OVERDUE_COLS = ("tenant_id", "invoice_id", "total", "days_overdue", "tenant_status")
SCHEDULE_COLS = (
    "loop_seq", "invoice_id", "tenant_id", "attempt_no", "id", "scheduled_for",
    "unshifted_scheduled_for", "source_day_of_week", "weekend_shift_days", "status_cd",
    "invoice_total", "invoice_issued_at", "days_overdue", "overdue_by_fn", "id_exists",
    "uq_exists", "tenant_rows", "tenant_status",
)
SUSPEND_COLS = (
    "tenant_id", "tenant_rows", "is_active", "tenant_status_cd_before", "subs_at_10",
    "subs_at_20", "subs_at_30", "notification_id", "notification_sent_at", "suspended_on",
    "notification_exists",
)
SUSPEND_SUB_COLS = (
    "id", "tenant_id", "status_cd_before", "suspended_on_before", "status_cd_after",
    "suspended_on_after",
)
POPULATION_COLS = (
    "overdue_invoices", "overdue_by_fn", "same_calendar_day_invoices",
    "overdue_invoices_with_no_tenant_row", "overdue_invoices_with_unknown_tenant_status",
    "tenants_at_10", "tenants_at_20", "tenants_with_unknown_status", "subscriptions_at_10",
    "subscriptions_at_20", "subscriptions_at_30", "attempts_with_unknown_status_cd",
    "overdue_total", "overdue_total_null_rows",
)
MULTIDATE_COLS = (
    "tenant_id", "is_active", "has_notification_on_as_of", "has_notification_on_other",
    "other_notification_id",
)
ATTEMPT_ROW_COLS = (
    "id", "tenant_id", "invoice_id", "attempt_no", "scheduled_for", "status_cd", "status",
)
NOTIFICATION_ROW_COLS = ("id", "tenant_id", "kind_cd", "sent_at", "kind")
TENANT_ROW_COLS = ("id", "status_cd", "tenant_status", "status")
SUBSCRIPTION_ROW_COLS = (
    "id", "tenant_id", "plan_id", "status_cd", "starts_on", "ends_on", "suspended_on",
)


def overdue_accounts(cur, as_of: str) -> list[dict]:
    """fn_overdue_accounts, actually called: the function opens the cursor and Oracle orders it."""
    # p_as_of is a DATE, so it is bound as one: a string would leave the conversion to NLS.
    ref = cur.callfunc(
        "pkg_dunning.fn_overdue_accounts",
        oracledb.DB_TYPE_CURSOR,
        [dt.datetime.strptime(as_of, "%Y-%m-%d")],
    )
    rows = [dict(zip(OVERDUE_COLS, r)) for r in ref.fetchall()]
    for row in rows:
        row["total"] = money(row["total"])
        row["days_overdue"] = int(row["days_overdue"])
    return rows


def schedule_expectation(cur, as_of: str) -> list[dict]:
    rows = _dicts(cur, SCHEDULE_EXPECT_SQL, SCHEDULE_COLS, as_of=as_of)
    for row in rows:
        for key in (
            "loop_seq", "attempt_no", "weekend_shift_days", "status_cd", "days_overdue",
            "overdue_by_fn", "id_exists", "uq_exists", "tenant_rows",
        ):
            row[key] = int(row[key])
        row["invoice_total"] = money(row["invoice_total"])
    return rows


def suspend_expectation(cur, as_of: str) -> dict:
    tenants = _dicts(cur, SUSPEND_EXPECT_SQL, SUSPEND_COLS, as_of=as_of)
    for row in tenants:
        for key in (
            "tenant_rows", "is_active", "subs_at_10", "subs_at_20", "subs_at_30",
            "notification_exists",
        ):
            row[key] = int(row[key])
        row["tenant_status_cd_before"] = (
            int(row["tenant_status_cd_before"])
            if row["tenant_status_cd_before"] is not None
            else None
        )
    subs = _dicts(cur, SUSPEND_SUBS_SQL, SUSPEND_SUB_COLS, as_of=as_of)
    for row in subs:
        row["status_cd_before"] = int(row["status_cd_before"])
        row["status_cd_after"] = int(row["status_cd_after"])
    swept = [t for t in tenants if t["is_active"] > 0]
    return {
        "candidates": tenants,
        "swept": swept,
        "skipped_not_active": [t for t in tenants if t["is_active"] == 0],
        "candidates_with_no_tenant_row": [t for t in tenants if t["tenant_rows"] == 0],
        "subscriptions_updated": subs,
        "notifications_inserted": [t for t in swept if t["notification_exists"] == 0],
        "notifications_suppressed_by_not_exists": [
            t for t in swept if t["notification_exists"] > 0
        ],
        "subscriptions_left_at_20": sum(t["subs_at_20"] for t in swept),
        "subscriptions_left_at_30": sum(t["subs_at_30"] for t in swept),
    }


def snapshot(as_of: str, other_as_of: str) -> dict:
    """One read-only Oracle session; every number the recon report quotes as the source's comes here.

    `other_as_of` is the second `p_as_of` the multi-date notification exposure is measured on. It is
    only ever read: no run of `sp_suspend_overdue` happens on either date.
    """
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")

        banner = _rows(cur, BANNER_SQL)[0][0]
        counts_row = _rows(cur, COUNTS_SQL)[0]
        counts = dict(
            zip(
                (
                    "tenants", "invoices", "invoices_overdue", "subscriptions",
                    "dunning_attempts", "notifications", "notifications_kind_3", "codes",
                ),
                (int(v) for v in counts_row),
            )
        )
        populations = _dicts(cur, POPULATIONS_SQL, POPULATION_COLS, as_of=as_of)[0]
        for key, value in list(populations.items()):
            if key == "overdue_total":
                populations[key] = money(decimal.Decimal(value))
            else:
                populations[key] = int(value)

        multidate = _dicts(
            cur, MULTIDATE_NOTIFICATION_SQL, MULTIDATE_COLS, as_of=as_of, other_as_of=other_as_of
        )
        for row in multidate:
            for key in ("is_active", "has_notification_on_as_of", "has_notification_on_other"):
                row[key] = int(row[key])

        result = {
            "oracle_banner": banner,
            "oracle_source_sha": oracle_source_sha(),
            "as_of": as_of,
            "other_as_of": other_as_of,
            "source_counts": counts,
            "populations": populations,
            "overdue_accounts": overdue_accounts(cur, as_of),
            "schedule": schedule_expectation(cur, as_of),
            "suspend": suspend_expectation(cur, as_of),
            "attempt_rows": _dicts(cur, ATTEMPTS_SQL, ATTEMPT_ROW_COLS),
            "notification_rows": _dicts(cur, NOTIFICATIONS_SQL, NOTIFICATION_ROW_COLS),
            "tenant_rows": _dicts(cur, TENANTS_SQL, TENANT_ROW_COLS),
            "subscription_rows": _dicts(cur, SUBSCRIPTIONS_SQL, SUBSCRIPTION_ROW_COLS),
            "multi_date_notification_exposure": {
                "other_as_of": other_as_of,
                "tenants_in_the_other_cutoff": len(multidate),
                "rows": multidate,
                "notifications_the_other_as_of_would_add": sum(
                    1
                    for r in multidate
                    if r["is_active"] > 0 and r["has_notification_on_other"] == 0
                ),
            },
        }
        for row in result["attempt_rows"]:
            row["attempt_no"] = int(row["attempt_no"])
            row["status_cd"] = int(row["status_cd"])
        for row in result["notification_rows"]:
            row["kind_cd"] = int(row["kind_cd"])
        for row in result["tenant_rows"]:
            row["status_cd"] = int(row["status_cd"])
        for row in result["subscription_rows"]:
            row["status_cd"] = int(row["status_cd"])
        conn.rollback()
    return result


def transcript_expectation(as_of: str) -> dict:
    """The state each DUNNING-00x transcript pins, evaluated read-only on the source for that date.

    The transcripts were recorded against a freshly seeded source, and nothing here mutates it, so
    the same statements evaluated now describe the same night.
    """
    with connect() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.outputtypehandler = _number_handler
        cur.execute("ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH'")
        result = {
            "as_of": as_of,
            "overdue_accounts": overdue_accounts(cur, as_of),
            "schedule": schedule_expectation(cur, as_of),
            "suspend": suspend_expectation(cur, as_of),
            "existing_attempt_rows": _dicts(cur, ATTEMPTS_SQL, ATTEMPT_ROW_COLS),
            "existing_notification_rows": _dicts(
                cur, NOTIFICATIONS_SQL, NOTIFICATION_ROW_COLS
            ),
        }
        for row in result["existing_attempt_rows"]:
            row["attempt_no"] = int(row["attempt_no"])
            row["status_cd"] = int(row["status_cd"])
        for row in result["existing_notification_rows"]:
            row["kind_cd"] = int(row["kind_cd"])
        conn.rollback()
    return result
