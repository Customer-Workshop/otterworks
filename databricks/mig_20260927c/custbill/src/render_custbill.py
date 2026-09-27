# Databricks notebook source
"""Render ow_tp.mig_20260927c_silver.custbill_records to the CUSTBILL fixed-width
file, byte-identical in format to etl/legacy-extra/tools/oracle_custbill_extract.py.
"""

import hashlib
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_OUT = "/Volumes/ow_tp/mig_20260927c_bronze/custbill_out/CUSTBILL_DEMO_ORACLE.dat"
DEFAULT_MANIFEST = "ow_tp.mig_20260927c_silver.custbill_file_manifest"
DEFAULT_SOURCE = "ow_tp.mig_20260927c_silver.custbill_records"


def _ascii_text(value):
    return (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "replace")
        .decode()
    )


def _period_text(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y%m%d")  # noqa: DTZ007


def _amount_cents(value):
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def format_record(row):
    cust_no = _ascii_text(row["cust_no"])[:10].ljust(10)
    name = _ascii_text(row["cust_name"])[:30].ljust(30)
    period_end = _period_text(row["period_end"])
    cents = _amount_cents(row["total_amt"])
    if abs(cents) > 999_999_999_999:
        raise ValueError(
            f"invoice {row['invoice_id']} total exceeds CUSTBILL amount field"
        )
    record_type = "02" if cents < 0 else str(row.get("record_type") or "01")[:2].rjust(2, "0")
    record = f"{cust_no}{name}{period_end}{abs(cents):012d}USD{record_type}"
    assert len(record) == 65
    return record


def build_file_bytes(rows):
    return ("\n".join(format_record(r) for r in rows) + "\n").encode("ascii")


# COMMAND ----------

def main():
    sess = globals().get("spark")
    if sess is None:
        from pyspark.sql import SparkSession
        sess = SparkSession.getActiveSession()
    dbs = globals().get("dbutils")
    if dbs is None:  # plain spark_python_task, no notebook globals injected
        from databricks.sdk.runtime import dbutils as dbs
    params = {}
    for k, d in (("out", DEFAULT_OUT), ("manifest_table", DEFAULT_MANIFEST),
                 ("source_table", DEFAULT_SOURCE)):
        try:
            params[k] = dbs.widgets.get(k) or d
        except Exception:  # noqa: BLE001
            params[k] = d
    rows = [
        r.asDict()
        for r in sess.sql(
            f"SELECT invoice_id, cust_no, cust_name, period_end, total_amt, "
            f"record_type FROM {params['source_table']} "
            f"ORDER BY period_end, cust_no, invoice_id"
        ).collect()
    ]
    payload = build_file_bytes(rows)
    sha = hashlib.sha256(payload).hexdigest()
    dbs.fs.put(f"dbfs:{params['out']}", payload.decode("ascii"), True)
    sess.sql(
        f"CREATE OR REPLACE TABLE {params['manifest_table']} "
        "(file STRING, bytes BIGINT, sha256 STRING, generated_at TIMESTAMP)")
    sess.sql(
        f"INSERT INTO {params['manifest_table']} VALUES "
        f"('{params['out']}', {len(payload)}, '{sha}', current_timestamp())")
    print(f"wrote {params['out']} bytes={len(payload)} sha256={sha} records={len(rows)}")


if __name__ == "__main__" or "spark" in globals():
    main()
