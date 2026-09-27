"""CUSTBILL Lakeflow pipeline (SDP).

Bronze: whole-table landing parquet -> streaming tables.
Silver: custbill_records = translated legacy EXTRACT_SQL with expectations.
Quarantine: rows failing any expectation, with reject_reasons.
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = globals().get("spark") or SparkSession.getActiveSession()

LANDING = "/Volumes/ow_tp/mig_20260927c_bronze/custbill_landing"

BRONZE = "ow_tp.mig_20260927c_bronze"
SILVER = "ow_tp.mig_20260927c_silver"
QUAR = "ow_tp.mig_20260927c_quarantine"


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:  # noqa: BLE001
        return default


EXPECTATIONS = {
    "valid_cust_no": "cust_no IS NOT NULL",
    "valid_cust_name": "cust_name IS NOT NULL",
    "valid_invoice_dt": "period_end IS NOT NULL",
    "valid_total_amt": "total_amt IS NOT NULL AND abs(total_amt) <= 9999999999.99",
    "valid_currency": "currency = 'USD'",
}


@dp.table(name=f"{BRONZE}.invoice_header", table_properties={"delta.feature.timestampNtz": "supported"})
def invoice_header():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .load(f"{LANDING}/invoice_header/"))


@dp.table(name=f"{BRONZE}.invoice_line", table_properties={"delta.feature.timestampNtz": "supported"})
def invoice_line():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .load(f"{LANDING}/invoice_line/"))


@dp.table(name=f"{BRONZE}.customer_master", table_properties={"delta.feature.timestampNtz": "supported"})
def customer_master():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .load(f"{LANDING}/customer_master/"))


@dp.table(name=f"{BRONZE}.entity_attr_value", table_properties={"delta.feature.timestampNtz": "supported"})
def entity_attr_value():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .load(f"{LANDING}/entity_attr_value/"))


@dp.temporary_view(name="custbill_candidates")
def custbill_candidates():
    batch_no = int(_conf("custbill.batch_no", "85559852"))
    admin_tenant_id = _conf(
        "custbill.admin_tenant_id", "a0000000-0000-0000-0000-000000000001")
    h = spark.read.table(f"{BRONZE}.invoice_header")
    c = spark.read.table(f"{BRONZE}.customer_master")
    base = (h.join(c, h.cust_id == c.cust_id)
             .filter((h.batch_no == batch_no) | (h.tenant_id == admin_tenant_id))
             .select(
                 h.invoice_id,
                 c.cust_no,
                 c.cust_name,
                 h.invoice_dt,
                 F.to_date(F.upper(h.invoice_dt), "dd-MMM-yy").alias("period_end"),
                 h.total_amt,
                 F.lit("USD").alias("currency"),
                 F.when(h.total_amt < 0, F.lit("02"))
                  .otherwise(F.lit("01")).alias("record_type")))
    if _conf("custbill.inject_bad_row", "false").lower() == "true":
        bad = spark.createDataFrame(
            [(
                "fixture-bad-row-00000000-0000-0000-0000-000000000001",
                None,
                "FIXTURE BAD ROW",
                "31-FEB-99",
                None,
                None,
                "XXX",
                "01",
            )],
            schema="invoice_id string, cust_no string, cust_name string, "
                   "invoice_dt string, period_end date, total_amt decimal(14,2), "
                   "currency string, record_type string",
        )
        base = base.unionByName(bad)
    return base


@dp.materialized_view(name=f"{SILVER}.custbill_records")
@dp.expect_or_drop("valid_cust_no", EXPECTATIONS["valid_cust_no"])
@dp.expect_or_drop("valid_cust_name", EXPECTATIONS["valid_cust_name"])
@dp.expect_or_drop("valid_invoice_dt", EXPECTATIONS["valid_invoice_dt"])
@dp.expect_or_drop("valid_total_amt", EXPECTATIONS["valid_total_amt"])
@dp.expect_or_drop("valid_currency", EXPECTATIONS["valid_currency"])
def custbill_records():
    return (spark.read.table("custbill_candidates")
            .orderBy("period_end", "cust_no", "invoice_id"))


@dp.materialized_view(name=f"{QUAR}.custbill_rejects")
def custbill_rejects():
    df = spark.read.table("custbill_candidates")
    reasons = []
    for cond in EXPECTATIONS.values():
        reasons.append(F.when(~F.expr(f"({cond})"), F.lit(cond)))
    keep = F.expr(" AND ".join(f"({c})" for c in EXPECTATIONS.values()))
    return (df.filter(~keep)
            .withColumn("reject_reasons", F.array_compact(F.array(*reasons)))
            .withColumn("quarantined_at", F.current_timestamp()))
