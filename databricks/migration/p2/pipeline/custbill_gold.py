"""Gold layer: the finance close, as a table instead of a mailed file.

Replaces the aggregation half of etl/legacy-extra/jobs/finance_excel_report.pl. The
arithmetic itself is in `custbill_close`, which runs against the captured legacy
report without a cluster; this module is the Lakeflow wrapper, and the CSV/`.xls`
half is `export/finance_close_export.py`.

Two things worth knowing before reading the query:

- it aggregates a re-split of `psv_line`, not silver's clean `currency` and
  `rec_type` columns. The report reads the rendered line, so a record whose name
  held a `|` contributes shifted fields and lands in a nonsense group. Grouping
  the clean columns would repair the defect and change the totals (C-5.1, C-7.2).
- nothing is filtered. Every silver row reaches this table, quarantined or not,
  and the only row the legacy skips is the one whose first field is empty, which
  is skipped here for the same reason (C-6.3, C-7.4).

`total_amount` is kept at full precision and rounded to cents only when the CSV is
rendered, so the rounding happens once, in the same code the parity test runs.

`sort_key` and `row_order` are the report's own ordering (`sort keys %tot` over the
byte string `"$ccy|$rt"`), materialized so that an ordering regression fails recon
instead of passing as a set match (C-7.5).
"""

import custbill_bytes
import custbill_close
import custbill_parse
from custbill_close import record_type_name
from custbill_parse import awk_numeric
from pyspark import cloudpickle
from pyspark import pipelines as dp
from pyspark.sql import Window
from pyspark.sql import functions as F

GOLD_TABLE = "ow_tp.gold.custbill_finance_close"

# Same reason as silver: the pipeline source dir is on the driver's path, not the
# Python worker's, so the closure has to carry the module rather than reference it.
cloudpickle.register_pickle_by_value(custbill_bytes)
cloudpickle.register_pickle_by_value(custbill_parse)
cloudpickle.register_pickle_by_value(custbill_close)

awk_numeric_udf = F.udf(awk_numeric, "double")
record_type_name_udf = F.udf(record_type_name, "string")


@dp.materialized_view(
    name=GOLD_TABLE,
    comment="Finance close: billing totals by currency and record type, reproducing finance_excel_report.pl including its positional re-split of the parsed line. The governed replacement for the mailed .xls.",
)
def custbill_finance_close():
    fields = F.split(F.col("psv_line"), r"\|", -1)
    positional = (
        spark.read.table("ow_tp.silver.custbill")  # noqa: F821 - injected by the pipeline
        .select(
            fields.getItem(0).alias("cust_field"),
            F.coalesce(fields.getItem(3), F.lit("")).alias("amount_field"),
            F.coalesce(fields.getItem(4), F.lit("")).alias("currency"),
            F.coalesce(fields.getItem(5), F.lit("")).alias("rec_type"),
        )
        .where(F.col("cust_field") != F.lit(""))
    )
    grouped = (
        positional.groupBy("currency", "rec_type")
        .agg(
            F.count(F.lit(1)).alias("record_count"),
            F.sum(awk_numeric_udf(F.col("amount_field")).cast("decimal(38,10)")).alias("total_amount"),
        )
        .withColumn("sort_key", F.concat_ws("|", F.col("currency"), F.col("rec_type")))
    )
    return grouped.select(
        F.row_number().over(Window.orderBy("sort_key")).cast("int").alias("row_order"),
        "sort_key",
        "currency",
        "rec_type",
        record_type_name_udf(F.col("rec_type")).alias("record_type"),
        F.col("record_count").cast("bigint").alias("record_count"),
        F.col("total_amount").cast("decimal(38,10)").alias("total_amount"),
        F.current_timestamp().alias("closed_at"),
    )
