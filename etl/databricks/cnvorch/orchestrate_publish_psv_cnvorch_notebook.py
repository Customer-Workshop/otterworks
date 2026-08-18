# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_orchestrate_cnvorch / publish_psv — third task of the run_all conversion
# MAGIC
# MAGIC The explicit, verified replacement for the legacy filesystem handoff
# MAGIC (parse wrote `$ROOT/parsed/*.psv`; finance read them 5 cron-minutes later
# MAGIC and hoped they were complete). This task renders the silver slice back
# MAGIC into the exact legacy PSV record bytes per source file — the same
# MAGIC rendering the cnvparse unit's committed `cnvparse_silver_psv` view uses
# MAGIC for its parity checks — and REPLACES the finance input directory's
# MAGIC artifact set: stale `CUSTBILL*.psv` files are removed first, so a rerun
# MAGIC can never feed finance dead data. Each published artifact is read back
# MAGIC and byte-verified after the write.
# MAGIC
# MAGIC Empty input: clears stale artifacts and leaves the input directory
# MAGIC present (write-empty-result).

# COMMAND ----------

import os
import re

dbutils.widgets.text("ns", "cnvorch")
NS = dbutils.widgets.get("ns")
if not re.fullmatch(r"[a-z0-9_]{1,24}", NS):
    raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {NS!r}")

SILVER = f"ow_tp.silver.custbill_parsed_{NS}"
PARSED_DIR = f"/Volumes/ow_tp/bronze/landing/{NS}/finance_report/parsed"

# COMMAND ----------

# Legacy record rendering, identical to the cnvparse unit's cnvparse_silver_psv
# view (concat_ws('|', cust_id, cust_name, yyyy-MM-dd date, cents as x.xx,
# currency, record_type)); ordered by line_no to reproduce the legacy file
# order byte-for-byte, not just as a set.
rows = spark.sql(
    f"""SELECT source_file, line_no,
               concat_ws('|',
                 cust_id,
                 cust_name,
                 date_format(bill_date, 'yyyy-MM-dd'),
                 concat(cast(amount_cents DIV 100 AS STRING), '.',
                        lpad(cast(amount_cents % 100 AS STRING), 2, '0')),
                 currency,
                 record_type
               ) AS psv_line
        FROM {SILVER}
        ORDER BY source_file, line_no"""
).collect()

artifacts: dict[str, list[str]] = {}
for r in rows:
    name = r["source_file"]
    if name.endswith(".dat"):
        name = name[: -len(".dat")]
    artifacts.setdefault(f"{name}.psv", []).append(r["psv_line"])

# COMMAND ----------

os.makedirs(PARSED_DIR, exist_ok=True)

stale = [
    n for n in os.listdir(PARSED_DIR)
    if n.startswith("CUSTBILL") and n.endswith(".psv") and n not in artifacts
]
for name in stale:
    os.remove(os.path.join(PARSED_DIR, name))
    print(f"removed stale handoff artifact {name}")

for name, lines in sorted(artifacts.items()):
    data = ("\n".join(lines) + "\n").encode("latin-1")
    path = os.path.join(PARSED_DIR, name)
    with open(path, "wb") as fh:
        fh.write(data)
    with open(path, "rb") as fh:
        written = fh.read()
    if written != data:
        raise IOError(f"post-write verification failed for {path}")
    print(f"published {name} ({len(lines)} records, {len(data)} bytes)")

if not artifacts:
    print(f"empty silver slice: {PARSED_DIR} left present with no CUSTBILL*.psv artifacts")
