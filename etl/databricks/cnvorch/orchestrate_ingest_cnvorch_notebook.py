# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_orchestrate_cnvorch / ingest — first task of the run_all conversion
# MAGIC
# MAGIC Runs the merged cnvingest unit's notebook verbatim on this workflow's
# MAGIC namespace slice: the sibling notebook is ns-parameterized by design, so
# MAGIC composition is a `dbutils.notebook.run` of its unmodified source (deployed
# MAGIC byte-identical under `/Shared/ow_tp/cnvorch/cnvingest/` by this unit's
# MAGIC deploy script) with `ns` set to this workflow's namespace.
# MAGIC
# MAGIC Contract: docs/tech-partnerships/contracts/run_all_orchestration-cnvorch.contract.json

# COMMAND ----------

import re

dbutils.widgets.text("ns", "cnvorch")
NS = dbutils.widgets.get("ns")
if not re.fullmatch(r"[a-z0-9_]{1,24}", NS):
    raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {NS!r}")

# COMMAND ----------

# Verbatim composition of the cnvingest unit (source of truth:
# etl/databricks/cnvingest/sftp_ingest_poll_notebook.py + ingest_core.py,
# merged via PR #1195). No suppression: a failure here fails this task and
# blocks parse/publish_psv/finance via the job's depends_on edges.
result = dbutils.notebook.run(
    "/Shared/ow_tp/cnvorch/cnvingest/sftp_ingest_poll_notebook",
    1800,
    {"ns": NS},
)
print(f"ingest completed for ns={NS}: {result}")
