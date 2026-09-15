#!/usr/bin/env python3
"""Unit p1-billing-audit-log (U-19), read half: snapshot BILLING_AUDIT_LOG to Parquet.

This is the only program of the unit that opens a legacy connection, and it holds no
target credential: the factory guard refuses a single program that both reads the legacy
estate and writes a migration target, and the split also lets the read be replayed against
the local fixture without a Databricks credential in the process.

The read is `SET TRANSACTION READ ONLY` plus one `SELECT`. Nothing else is sent.

The table is empty in the source today, so the snapshot's value is its schema: the column
types come from the cursor description, not from the rows, and a zero-row snapshot still
describes all four columns. `LOG_ID` is `NUMBER(12)`, which overflows int4, so it travels
as int64; `LOGGED_AT` is an Oracle `DATE`, which carries a time part and no zone, so it
travels as a microsecond timestamp and lands as `TIMESTAMP_NTZ` (plan decision P1-D3).
`fetch_decimals` keeps any NUMBER exact rather than routing it through a float.

usage:
  python3 databricks/migration/silver/billing_audit_log_extract.py --out /tmp/bal.parquet
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE_SCHEMA = "ow_billing"
SOURCE_TABLE = "billing_audit_log"
COLUMNS = ("log_id", "logged_at", "module", "message")

# python-oracledb returns NUMBER as a float unless this is set; a float would round the
# exact values the recon compares.
oracledb.defaults.fetch_decimals = True

ARROW_SCHEMA = pa.schema([
    ("log_id", pa.int64()),
    ("logged_at", pa.timestamp("us")),
    ("module", pa.string()),
    ("message", pa.string()),
])


def oracle_conn(secret_var: str):
    parts = json.loads(os.environ[secret_var])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def cell(value):
    if isinstance(value, oracledb.LOB):
        return value.read()
    return value


def arrow_table(rows: list[tuple]) -> pa.Table:
    log_id = [None if r[0] is None else int(r[0]) for r in rows]
    logged_at = []
    for row in rows:
        value = row[1]
        logged_at.append(value if value is None or isinstance(value, datetime)
                         else datetime.combine(value, datetime.min.time()))
    module = [None if r[2] is None else str(cell(r[2])) for r in rows]
    message = [None if r[3] is None else str(cell(r[3])) for r in rows]
    return pa.table([log_id, logged_at, module, message], schema=ARROW_SCHEMA)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret", default="OW_TP_ORACLE_RO",
                    help="ENV VAR NAME holding the read-only source secret JSON")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    select = (f"SELECT {', '.join(COLUMNS)} "
              f"FROM {SOURCE_SCHEMA}.{SOURCE_TABLE} ORDER BY log_id")
    with oracle_conn(args.secret) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(select)
        rows = cur.fetchall()
        # The identity contract the trigger and sequence carry: the target has to start
        # above every key already in the source.
        max_log_id = max((int(r[0]) for r in rows if r[0] is not None), default=0)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table(rows), args.out)
    print(json.dumps({"table": f"{SOURCE_SCHEMA}.{SOURCE_TABLE}", "rows": len(rows),
                      "max_log_id": max_log_id, "parquet": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
