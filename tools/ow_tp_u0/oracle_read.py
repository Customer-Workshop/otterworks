from __future__ import annotations

import oracledb


TABLES = {
    "CODES": ("ow_billing.codes", ["code_type", "code_val", "code_desc"]),
    "PLANS": (
        "ow_billing.plans",
        ["id", "code", "tier_cd", "monthly_fee", "included_units", "overage_rate", "active_yn"],
    ),
    "TENANTS": ("ow_billing.tenants", ["id", "name", "tax_exempt_yn", "status_cd"]),
    "BILLING_AUDIT_LOG": (
        "ow_billing.billing_audit_log",
        ["log_id", "logged_at", "module", "message"],
    ),
}


def _rows_from_cursor(cursor) -> list[tuple]:
    return [tuple(row) for row in cursor.fetchall()]


def read_pinned(conn: oracledb.Connection) -> tuple[int, dict[str, list[tuple]]]:
    cur = conn.cursor()
    cur.execute("SELECT current_scn FROM v$database")
    scn = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT
          CURSOR(SELECT CODE_TYPE, CODE_VAL, CODE_DESC
                   FROM OW_BILLING.CODES AS OF SCN :scn
                 ORDER BY CODE_TYPE, CODE_VAL),
          CURSOR(SELECT ID, CODE, TIER_CD, MONTHLY_FEE, INCLUDED_UNITS, OVERAGE_RATE, ACTIVE_YN
                   FROM OW_BILLING.PLANS AS OF SCN :scn
                 ORDER BY ID),
          CURSOR(SELECT ID, NAME, TAX_EXEMPT_YN, STATUS_CD
                   FROM OW_BILLING.TENANTS AS OF SCN :scn
                 ORDER BY ID),
          CURSOR(SELECT LOG_ID, LOGGED_AT, MODULE, MESSAGE
                   FROM OW_BILLING.BILLING_AUDIT_LOG AS OF SCN :scn
                 ORDER BY LOG_ID)
        FROM dual
        """,
        scn=scn,
    )
    cursors = cur.fetchone()
    values: dict[str, list[tuple]] = {}
    for name, nested in zip(TABLES, cursors):
        values[name] = _rows_from_cursor(nested)
        nested.close()
    cur.close()
    return scn, values
