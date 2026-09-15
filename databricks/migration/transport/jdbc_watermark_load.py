#!/usr/bin/env python3
"""Wave 0, batch w0-b: the correctness transport from Oracle into ow_tp.bronze.

D10-03 (Debezium Server on EKS -> Kinesis -> Lakeflow) is not reachable from this session:
there is no kube context and no Kinesis stream in the account, and standing that leg up is
parent-owned infrastructure. The plan's recorded condition therefore applies and this unit
ships the D-002 fallback: a read-only JDBC snapshot plus a watermark, landed as Parquet in
/Volumes/ow_tp/bronze/landing and registered as a Delta table in ow_tp.bronze. The CDC leg is
a follow-up beside this, not a blocker.

Incremental runs pass --watermark-column; rows with watermark >= the table's current maximum
are re-read and merged on the primary key. The boundary is inclusive on purpose: a strict >
silently drops rows that arrive later carrying the same timestamp as the maximum already
loaded, which Oracle's second-resolution DATE columns make common. Re-reading the boundary
costs one timestamp's worth of rows and the key MERGE makes the overlap a no-op.

Deletes: an incremental read cannot see a row the source deleted, so it stays in bronze.
A full read (no --watermark-column, or --full-refresh) stages every live key and therefore
CAN converge deletes; it removes target rows whose key is absent from the stage. The delete
pass never runs against a watermark-filtered stage, which would empty the table. Watermarked
tables need a periodic --full-refresh run to converge deletes; each run's JSON says whether
deletes were converged. A complete snapshot that reads zero rows means the source table is
empty, so the target is emptied too; an empty incremental read means nothing new arrived and
leaves the target alone; a first complete snapshot of an empty source still registers the
target table, from the source's column metadata, so it exists and holds no rows.

usage (under with_oracle_secret.py, with DATABRICKS_* in the environment):
  python3 jdbc_watermark_load.py --table codes --keys code_type,code_val
  python3 jdbc_watermark_load.py --table invoices --keys id --watermark-column updated_at
  python3 jdbc_watermark_load.py --table invoices --keys id --watermark-column updated_at \
      --full-refresh
"""
import argparse
import decimal
import io
import json
import os
import re
import sys
import uuid
from datetime import date, datetime

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq
from databricks import sql as dbsql
from databricks.sdk import WorkspaceClient

SOURCE_SCHEMA = "ow_billing"
CATALOG = "ow_tp"
SCHEMA = "bronze"
VOLUME = "/Volumes/ow_tp/bronze/landing"
WAREHOUSE = "565cd2fd713738c4"
BATCH = 10_000

# Table, key and watermark names are concatenated into Oracle and Databricks SQL, so they are
# restricted to plain unquoted identifiers. Anything else is rejected before a statement is
# built rather than escaped afterwards.
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def ident(name: str, what: str) -> str:
    n = name.strip().lower()
    if not IDENT.match(n):
        raise SystemExit(f"{what} is not a plain SQL identifier: {name!r}")
    return n


def oracle_conn():
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def sql_conn():
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=_oauth_provider())


def _oauth_provider():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return lambda: oauth_service_principal(cfg)


def cell(value):
    """Land everything lossless: money as string-free decimal, dates as-is, LOBs as text.

    Oracle NUMBER is arbitrary precision, so it travels as decimal and never as float; the
    money columns are compared exactly downstream and a float would lose that.
    """
    if isinstance(value, oracledb.LOB):
        return value.read()
    return value


def arrow_table(columns, rows):
    cols = {}
    for i, name in enumerate(columns):
        values = [cell(r[i]) for r in rows]
        sample = next((v for v in values if v is not None), None)
        if isinstance(sample, decimal.Decimal):
            typ = pa.decimal128(38, 10)
            values = [None if v is None else decimal.Decimal(v).quantize(
                decimal.Decimal("1.0000000000")) for v in values]
        elif isinstance(sample, datetime):
            typ = pa.timestamp("us")
        elif isinstance(sample, date):
            typ = pa.date32()
        elif isinstance(sample, (int,)):
            typ = pa.int64()
        elif isinstance(sample, float):
            typ = pa.float64()
        else:
            typ = pa.string()
            values = [None if v is None else str(v) for v in values]
        cols[name.lower()] = pa.array(values, type=typ)
    return pa.table(cols)


def delta_type(desc) -> str:
    """Delta type for one Oracle cursor-description column.

    Only used to register an empty table when the source has no rows; a table with rows is
    created from the Parquet stage, which carries the same decisions from arrow_table().
    """
    _, typ, _, _, precision, scale, _ = desc
    if typ is oracledb.DB_TYPE_NUMBER:
        return f"DECIMAL({precision or 38},{scale if scale is not None else 10})"
    if typ in (oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP,
               oracledb.DB_TYPE_TIMESTAMP_TZ, oracledb.DB_TYPE_TIMESTAMP_LTZ):
        return "TIMESTAMP"
    if typ in (oracledb.DB_TYPE_BINARY_DOUBLE, oracledb.DB_TYPE_BINARY_FLOAT):
        return "DOUBLE"
    return "STRING"


def read_source(table: str, watermark_column: str | None, since) -> tuple[list, list]:
    where = ""
    binds: list = []
    if watermark_column and since is not None:
        # Inclusive: rows tied with the current maximum may still be arriving. See module doc.
        where = f" WHERE {watermark_column} >= :1"
        binds = [since]
    sql = f"SELECT * FROM {SOURCE_SCHEMA}.{table}{where}"
    with oracle_conn() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, binds)
        description = list(cur.description)
        rows = cur.fetchall()
    return description, rows


def current_watermark(cur, table: str, watermark_column: str | None):
    if not watermark_column:
        return None
    cur.execute(f"SHOW TABLES IN {CATALOG}.{SCHEMA} LIKE '{table}'")
    if not cur.fetchall():
        return None
    cur.execute(f"SELECT max({watermark_column}) FROM {CATALOG}.{SCHEMA}.{table}")
    return cur.fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--keys", required=True, help="comma-separated primary key columns")
    ap.add_argument("--watermark-column")
    ap.add_argument("--full-refresh", action="store_true",
                    help="read every row and delete target keys the source no longer has")
    args = ap.parse_args()
    table = ident(args.table, "--table")
    keys = [ident(k, "--keys") for k in args.keys.split(",")]
    watermark_column = (ident(args.watermark_column, "--watermark-column")
                        if args.watermark_column else None)

    with sql_conn() as conn, conn.cursor() as cur:
        since = (None if args.full_refresh
                 else current_watermark(cur, table, watermark_column))
        description, rows = read_source(table, watermark_column, since)
        columns = [d[0] for d in description]
        # The stage holds every live key only when nothing filtered the read.
        full_snapshot = since is None
        if not rows:
            # An empty complete snapshot means the source table is empty, which is a real
            # state the target has to reach: the table has to exist and hold no rows, so a
            # first load of an empty source registers it from the source's own column
            # metadata. An empty incremental read means nothing new arrived.
            created = emptied = False
            if full_snapshot:
                cols = ", ".join(f"{d[0].lower()} {delta_type(d)}" for d in description)
                cur.execute(f"SHOW TABLES IN {CATALOG}.{SCHEMA} LIKE '{table}'")
                if cur.fetchall():
                    cur.execute(f"DELETE FROM {CATALOG}.{SCHEMA}.{table}")
                    emptied = True
                else:
                    cur.execute(f"CREATE TABLE {CATALOG}.{SCHEMA}.{table} ({cols})")
                    created = True
            print(json.dumps({"table": table, "rows": 0, "watermark_since": str(since),
                              "full_snapshot": full_snapshot, "target_created": created,
                              "target_emptied": emptied,
                              "deletes_converged": full_snapshot}))
            return 0

        run_id = uuid.uuid4().hex
        staged = f"{VOLUME}/{table}/{run_id}.parquet"
        buf = io.BytesIO()
        pq.write_table(arrow_table(columns, rows), buf)
        buf.seek(0)
        WorkspaceClient().files.upload(staged, buf, overwrite=True)

        stage = f"{CATALOG}.{SCHEMA}.{table}__stage_{run_id}"
        cur.execute(f"CREATE TABLE {stage} AS SELECT * FROM parquet.`{staged}`")
        try:
            cur.execute(f"CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{table} "
                        f"AS SELECT * FROM {stage} WHERE 1=0")
            on = " AND ".join(f"t.{k} <=> s.{k}" for k in keys)
            delete_clause = (" WHEN NOT MATCHED BY SOURCE THEN DELETE"
                             if full_snapshot else "")
            cur.execute(
                f"MERGE INTO {CATALOG}.{SCHEMA}.{table} t USING {stage} s ON {on} "
                "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *"
                f"{delete_clause}")
            cur.execute(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{table}")
            total = cur.fetchone()[0]
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {stage}")
            # The Parquet object exists only to seed the stage table; leaving it behind
            # would grow the landing volume by one file per table per run forever.
            WorkspaceClient().files.delete(staged)

    print(json.dumps({"table": table, "source_rows": len(rows), "target_rows": total,
                      "watermark_column": watermark_column,
                      "watermark_since": str(since), "full_snapshot": full_snapshot,
                      "deletes_converged": full_snapshot,
                      "staged": staged, "staged_retained": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
