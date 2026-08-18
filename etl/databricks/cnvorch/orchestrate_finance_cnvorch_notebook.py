# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_orchestrate_cnvorch / finance — last task of the run_all conversion
# MAGIC
# MAGIC Runs the merged cnvfinance unit's notebook verbatim on this workflow's
# MAGIC namespace slice: the sibling notebook is ns/report_date-parameterized by
# MAGIC design, so composition is a `dbutils.notebook.run` of its unmodified source
# MAGIC (deployed byte-identical under `/Shared/ow_tp/cnvorch/cnvfinance/`, next to
# MAGIC its `finance_core.py`, by this unit's deploy script). It reads the PSV
# MAGIC artifacts published by the upstream publish_psv task from
# MAGIC `/Volumes/ow_tp/bronze/landing/{ns}/finance_report/parsed/`.
# MAGIC
# MAGIC Contract: docs/tech-partnerships/contracts/run_all_orchestration-cnvorch.contract.json

# COMMAND ----------

import re

dbutils.widgets.text("ns", "cnvorch")
dbutils.widgets.text("report_date", "2026-01-15")
NS = dbutils.widgets.get("ns")
REPORT_DATE = dbutils.widgets.get("report_date")
if not re.fullmatch(r"[a-z0-9_]{1,24}", NS):
    raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {NS!r}")
if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", REPORT_DATE):
    raise ValueError(f"report_date must be YYYY-MM-DD: {REPORT_DATE!r}")

# COMMAND ----------

# Verbatim composition of the cnvfinance unit (source of truth:
# etl/databricks/cnvfinance/finance_excel_report_notebook.py + finance_core.py,
# merged via PR #1196). No suppression: a failure here fails the workflow run.
result = dbutils.notebook.run(
    "/Shared/ow_tp/cnvorch/cnvfinance/finance_excel_report_notebook",
    1800,
    {"ns": NS, "report_date": REPORT_DATE},
)
print(f"finance completed for ns={NS}, report_date={REPORT_DATE}: {result}")
