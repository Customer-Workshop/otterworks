#!/usr/bin/env python3
"""Read one legacy table read-only and write it to a local Parquet snapshot.

This is the source half of the transport. It is a separate program from the loader on
purpose: the factory guard refuses a single program that both reads the legacy source and
writes a migration target, and that split is worth keeping anyway - the read side can be
replayed from the fixture without a Databricks credential in the process.

The read is `SET TRANSACTION READ ONLY` plus one `SELECT *`. Nothing else is ever sent.

Everything lands lossless: NUMBER travels as an exact decimal (never a float, which would
silently round the money columns the recon compares exactly), a NUMBER(p,0) that fits
becomes int64, DATE and TIMESTAMP keep their time part, LOBs are read as text. Alongside
the Parquet file the extract writes a `.schema.json` sidecar with the Delta type of every
column, taken from the cursor's own metadata rather than from the rows: an empty table -
which both pipeline-1 history tables are today - still describes its full schema, so the
loader can register the target with the right columns and no rows.

    python3 oracle_snapshot_extract.py --table subscriptions_hist --out /tmp/sh
"""

from __future__ import annotations

import argparse
import decimal
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE_SCHEMA = "ow_billing"

# python-oracledb hands NUMBER back as a Python float by default, which silently rounds the
# money columns this migration compares exactly. Fetching decimals keeps every NUMBER exact.
oracledb.defaults.fetch_decimals = True

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def ident(name: str, what: str) -> str:
    n = (name or "").strip().lower()
    if not IDENT.match(n):
        raise SystemExit(f"{what} is not a plain SQL identifier: {name!r}")
    return n


def oracle_conn(secret_var: str):
    parts = json.loads(os.environ[secret_var])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def cell(value):
    if isinstance(value, oracledb.LOB):
        return value.read()
    return value


def decimal_ps(desc) -> tuple[int, int]:
    """Precision and scale for a NUMBER column, from the cursor's metadata.

    A NUMBER with no precision, or a negative scale (legal in Oracle, not in Delta), has no
    usable pair and widens to the largest exact decimal. Inferring one from the rows in the
    batch would give the same column a different target type on a different day.
    """
    precision, scale = desc[4], desc[5]
    if not precision or scale is None or scale < 0 or scale > precision or precision > 38:
        return 38, 10
    return precision, scale


def is_integer_number(desc) -> bool:
    precision, scale = desc[4], desc[5]
    return bool(precision) and scale == 0 and precision <= 18


def delta_type(desc) -> str:
    typ = desc[1]
    if typ is oracledb.DB_TYPE_NUMBER:
        if is_integer_number(desc):
            return "BIGINT"
        precision, scale = decimal_ps(desc)
        return f"DECIMAL({precision},{scale})"
    if typ in (oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP,
               oracledb.DB_TYPE_TIMESTAMP_TZ, oracledb.DB_TYPE_TIMESTAMP_LTZ):
        # Zoneless in the source; the zoneless Delta type is the one that compares equal.
        return "TIMESTAMP_NTZ"
    if typ in (oracledb.DB_TYPE_BINARY_DOUBLE, oracledb.DB_TYPE_BINARY_FLOAT):
        return "DOUBLE"
    return "STRING"


def arrow_type(desc, sample):
    if desc[1] is oracledb.DB_TYPE_NUMBER and is_integer_number(desc):
        return pa.int64()
    if desc[1] is oracledb.DB_TYPE_NUMBER or isinstance(sample, decimal.Decimal):
        precision, scale = decimal_ps(desc)
        return pa.decimal128(precision, scale)
    if isinstance(sample, datetime):
        return pa.timestamp("us")
    if isinstance(sample, date):
        return pa.date32()
    if isinstance(sample, int):
        return pa.int64()
    if isinstance(sample, float):
        return pa.float64()
    return pa.string()


def arrow_table(description, rows) -> pa.Table:
    cols = {}
    for i, desc in enumerate(description):
        values = [cell(r[i]) for r in rows]
        sample = next((v for v in values if v is not None), None)
        typ = arrow_type(desc, sample)
        if pa.types.is_decimal(typ):
            quantum = decimal.Decimal(1).scaleb(-typ.scale)
            values = [None if v is None else decimal.Decimal(v).quantize(quantum)
                      for v in values]
        elif pa.types.is_int64(typ):
            values = [None if v is None else int(v) for v in values]
        elif pa.types.is_string(typ):
            values = [None if v is None else str(v) for v in values]
        cols[desc[0].lower()] = pa.array(values, type=typ)
    return pa.table(cols)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--secret", default="OW_TP_ORACLE_RO",
                    help="ENV VAR NAME holding the read-only source secret JSON")
    ap.add_argument("--out", required=True,
                    help="path prefix; writes <out>.parquet and <out>.schema.json")
    args = ap.parse_args()
    table = ident(args.table, "--table")

    with oracle_conn(args.secret) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(f"SELECT * FROM {SOURCE_SCHEMA}.{table}")
        description = list(cur.description)
        rows = cur.fetchall()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table(description, rows), out.with_suffix(".parquet"))
    schema = [{"name": d[0].lower(), "delta_type": delta_type(d)} for d in description]
    out.with_suffix(".schema.json").write_text(json.dumps(
        {"kind": "source-snapshot", "table": table, "rows": len(rows),
         "columns": schema}, indent=2) + "\n")
    print(json.dumps({"table": table, "rows": len(rows), "columns": len(schema),
                      "parquet": str(out.with_suffix(".parquet"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
