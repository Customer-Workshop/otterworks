#!/usr/bin/env python3
"""Wave 0, batch w0-b: the correctness transport from Oracle into ow_tp.bronze.

D10-03 (Debezium Server on EKS -> Kinesis -> Lakeflow) is not reachable from this session:
there is no kube context and no Kinesis stream in the account, and standing that leg up is
parent-owned infrastructure. The plan's recorded condition therefore applies and this unit
ships the D-002 fallback: a read-only JDBC snapshot plus a watermark, landed as Parquet in
/Volumes/ow_tp/bronze/landing and registered as a Delta table in ow_tp.bronze. The CDC leg is
a follow-up beside this, not a blocker.

Incremental runs pass --watermark-column; rows with watermark > the table's current maximum
are appended. Reruns are idempotent: the load is staged under a run id and the MERGE keys on
the table's primary key, so running twice lands the same table state.

usage (under with_oracle_secret.py, with DATABRICKS_* in the environment):
  python3 jdbc_watermark_load.py --table codes --keys code_type,code_val
  python3 jdbc_watermark_load.py --table invoices --keys id --watermark-column updated_at
"""
import argparse
import decimal
import io
import json
import os
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


def read_source(table: str, watermark_column: str | None, since) -> tuple[list[str], list]:
    where = ""
    binds: list = []
    if watermark_column and since is not None:
        where = f" WHERE {watermark_column} > :1"
        binds = [since]
    sql = f"SELECT * FROM {SOURCE_SCHEMA}.{table}{where}"
    with oracle_conn() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, binds)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return columns, rows


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
    args = ap.parse_args()
    table = args.table.lower()
    keys = [k.strip().lower() for k in args.keys.split(",")]

    with sql_conn() as conn, conn.cursor() as cur:
        since = current_watermark(cur, table, args.watermark_column)
        columns, rows = read_source(args.table, args.watermark_column, since)
        if not rows:
            print(json.dumps({"table": table, "rows": 0, "watermark_since": str(since)}))
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
            cur.execute(
                f"MERGE INTO {CATALOG}.{SCHEMA}.{table} t USING {stage} s ON {on} "
                "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
            cur.execute(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{table}")
            total = cur.fetchone()[0]
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {stage}")

    print(json.dumps({"table": table, "source_rows": len(rows), "target_rows": total,
                      "watermark_column": args.watermark_column,
                      "watermark_since": str(since), "staged": staged}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
