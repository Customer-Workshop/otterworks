"""Publish the dunning-risk score from Delta gold to Lakebase (ow_tp / billing).

Reads the three gold tables over the existing serverless SQL warehouse and replaces the
contents of their Lakebase counterparts inside a single transaction, so the dunning process
either sees the whole previous scoring run or the whole new one and never a half-loaded
queue.

Run it as:

    python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w0 \\
        -- python3 databricks/scoring/dunning_risk/sync_to_lakebase.py

The branch is an argument to the DSN helper, which refuses any target that is not in
.migration/allowed_targets.json. This script never names a branch and never holds a
credential: it reads the DSN the helper puts in the child environment. Structure is created
by databricks/migration/lakebase/ow_tp_dunning_risk_score.sql, applied separately through
apply_sql.py; this script only moves rows.
"""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal

import psycopg
import requests

WAREHOUSE = "565cd2fd713738c4"

# (gold table, Lakebase table, columns as they are selected and inserted)
TABLES = [
    (
        "ow_tp.gold.dunning_risk_rules",
        "billing.dunning_risk_rules",
        ["seq", "rule_id", "signal", "feature", "condition", "points", "rationale"],
        None,
    ),
    (
        "ow_tp.gold.dunning_risk_invoice",
        "billing.dunning_risk_invoice",
        [
            "invoice_id", "invoice_no", "cust_id", "tenant_id", "status_cd",
            "legacy_dunning_eligible", "total_amt", "invoice_dt_parsed AS invoice_dt",
            "due_dt_parsed AS due_dt", "due_before_invoice_dt", "age_days", "risk_score",
            "risk_band", "reason_codes", "unscored_signals", "as_of_dt",
            "built_at AS scored_at",
        ],
        None,
    ),
    (
        "ow_tp.gold.dunning_risk_account",
        "billing.dunning_risk_account",
        [
            "cust_id", "tenant_id", "open_invoice_cnt", "dunnable_invoice_cnt", "open_amt",
            "oldest_open_age_days", "worst_invoice_id", "risk_score", "risk_band",
            "reason_codes", "unscored_signals", "lifetime_overdue_rate", "credit_hold_yn",
            "vip_yn", "dunning_exempt_yn", "tenure_days", "as_of_dt",
            "built_at AS scored_at",
        ],
        # accounts with nothing open are not a dunning decision; publishing them would make
        # the read model four times larger and entirely of rows the caller filters out.
        "risk_band <> 'NO_OPEN_ITEMS'",
    ),
]

ARRAY_COLUMNS = {"reason_codes", "unscored_signals"}
BOOL_COLUMNS = {"legacy_dunning_eligible", "due_before_invoice_dt"}
DECIMAL_COLUMNS = {"total_amt", "open_amt", "lifetime_overdue_rate"}


def _warehouse_token() -> str:
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    resp = requests.post(
        f"{host}/oidc/v1/token",
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        auth=(os.environ["DATABRICKS_CLIENT_ID"], os.environ["DATABRICKS_CLIENT_SECRET"]),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _read_gold(token: str, sql: str) -> tuple[list[str], list[list]]:
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={
            "warehouse_id": WAREHOUSE,
            "statement": sql,
            "wait_timeout": "50s",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    while payload["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3)
        payload = requests.get(
            f"{host}/api/2.0/sql/statements/{payload['statement_id']}",
            headers=headers,
            timeout=60,
        ).json()
    if payload["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"{sql[:60]}...: {payload['status']}")
    columns = [c["name"] for c in payload["manifest"]["schema"]["columns"]]

    # A result larger than one chunk arrives as a first chunk plus a link to the next. Taking
    # only the first would truncate the queue silently, so walk the whole chain and check the
    # total against the manifest before anything is published.
    chunk = payload.get("result", {}) or {}
    rows = list(chunk.get("data_array") or [])
    while chunk.get("next_chunk_internal_link"):
        nxt = requests.get(
            f"{host}{chunk['next_chunk_internal_link']}", headers=headers, timeout=120
        )
        nxt.raise_for_status()
        chunk = nxt.json()
        rows.extend(chunk.get("data_array") or [])

    expected = payload["manifest"].get("total_row_count")
    if expected is not None and len(rows) != expected:
        raise RuntimeError(
            f"{sql[:60]}...: read {len(rows)} rows but the manifest reports {expected}"
        )
    return columns, rows


def _table_versions(token: str) -> dict[str, int]:
    """Current Delta version of each gold table, read in one statement."""
    sql = " UNION ALL ".join(
        f"SELECT '{gold}' AS tbl, max(version) AS v FROM (DESCRIBE HISTORY {gold})"
        for gold, _, _, _ in TABLES
    )
    _, rows = _read_gold(token, sql)
    return {tbl: int(v) for tbl, v in rows}


def coerce(column: str, value):
    """JSON_ARRAY hands everything back as a string. Put the types back."""
    if value is None:
        return None
    if column in ARRAY_COLUMNS:
        # JSON_ARRAY renders an array column as its JSON text
        import json

        return json.loads(value)
    if column in BOOL_COLUMNS:
        return value.lower() == "true"
    if column in DECIMAL_COLUMNS:
        return Decimal(value)
    return value


def main() -> int:
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        print(
            "OW_TP_LAKEBASE_DSN is not set. Run this through "
            "databricks/migration/lakebase/with_lakebase_dsn.py.",
            file=sys.stderr,
        )
        return 2

    token = _warehouse_token()

    # The three gold tables are rebuilt by three separate job tasks, so reading them with
    # three separate statements could pair new invoice scores with old rule points. Pin every
    # read to the versions observed at one instant, and refuse to publish if a rebuild landed
    # while we were reading — that snapshot may itself be half a run.
    versions = _table_versions(token)
    staged = []
    for gold, target, columns, predicate in TABLES:
        select = f"SELECT {', '.join(columns)} FROM {gold} VERSION AS OF {versions[gold]}"
        if predicate:
            select += f" WHERE {predicate}"
        names, rows = _read_gold(token, select)
        staged.append((target, names, rows))
        print(f"read {len(rows)} rows from {gold} v{versions[gold]}")

    moved = {t: v for t, v in _table_versions(token).items() if versions[t] != v}
    if moved:
        raise RuntimeError(
            "a scoring run rebuilt "
            + ", ".join(sorted(moved))
            + " while this publish was reading; nothing was written. Rerun once it finishes."
        )

    # One transaction for all three tables. TRUNCATE is transactional in Postgres, so a
    # reader mid-load keeps seeing the previous run's queue until this commits.
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            for target, names, rows in staged:
                cur.execute(f"TRUNCATE TABLE {target}")
                if not rows:
                    continue
                placeholders = ", ".join(["%s"] * len(names))
                stmt = f"INSERT INTO {target} ({', '.join(names)}) VALUES ({placeholders})"
                cur.executemany(
                    stmt,
                    [[coerce(n, v) for n, v in zip(names, row)] for row in rows],
                )
                print(f"loaded {len(rows)} rows into {target}")
        conn.commit()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for target, _, rows in staged:
            cur.execute(f"SELECT count(*) FROM {target}")
            actual = cur.fetchone()[0]
            if actual != len(rows):
                raise RuntimeError(f"{target}: expected {len(rows)} rows, found {actual}")
            print(f"verified {target}: {actual} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
