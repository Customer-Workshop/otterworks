# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_orchestrate_cnvorch / parse — second task of the run_all conversion
# MAGIC
# MAGIC Executes the merged cnvparse unit's pipeline SQL verbatim on this
# MAGIC workflow's namespace slice. The sibling SQL (deployed byte-identical
# MAGIC under `/Shared/ow_tp/cnvorch/cnvparse/` from
# MAGIC `etl/databricks/cnvparse/pipeline_parse_custbill.sql`, merged via
# MAGIC PR #1194) is parameterized here by two deterministic substitutions only:
# MAGIC the namespace token, and the landing directory (this workflow's parse
# MAGIC input is the ingest task's staged `incoming/` directory — the explicit
# MAGIC replacement for the legacy `$ROOT/incoming` filesystem handoff). No
# MAGIC parsing predicate, table shape, or quarantine decision is reimplemented.
# MAGIC
# MAGIC Chaos: `chaos=parse_failure` raises before any statement executes,
# MAGIC proving orch-02 (a failed upstream blocks publish_psv and finance and
# MAGIC leaves state untouched).
# MAGIC
# MAGIC Empty input: `read_files` cannot plan over zero files, so a batch with
# MAGIC no staged CUSTBILL*.dat branches explicitly: it runs the sibling DDL and
# MAGIC rewrites the bronze/silver/quarantine slice empty (write-empty-result),
# MAGIC mirroring the legacy chain where the glob matched nothing.

# COMMAND ----------

import re

dbutils.widgets.text("ns", "cnvorch")
dbutils.widgets.text("chaos", "")
NS = dbutils.widgets.get("ns")
CHAOS = dbutils.widgets.get("chaos")
if not re.fullmatch(r"[a-z0-9_]{1,24}", NS):
    raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {NS!r}")

if CHAOS == "parse_failure":
    raise RuntimeError(
        "chaos-parse-failure injected: failing the parse task before any write "
        "(must-detect anomaly per the run_all_orchestration-cnvorch contract)"
    )

SIBLING_SQL = "/Workspace/Shared/ow_tp/cnvorch/cnvparse/pipeline_parse_custbill.sql"
SIBLING_NS = "cnvparse"
SIBLING_LANDING = f"/Volumes/ow_tp/bronze/landing/{NS}/parse/"
INCOMING = f"/Volumes/ow_tp/bronze/landing/{NS}/sftp_ingest_poll/incoming/"

# COMMAND ----------

def split_sql_statements(text: str) -> list[str]:
    """Split multi-statement SQL on `;`, aware of `--` line comments and
    single/double-quoted literals (both occur in the sibling SQL, including
    semicolons inside them). Comments are dropped; statement bodies are kept
    verbatim."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "-" and text[i:i + 2] == "--":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


with open(SIBLING_SQL, "r", encoding="utf-8") as fh:
    sql_text = fh.read()

# Deterministic parameterization of the verbatim sibling SQL: namespace token
# first (table names, view names, landing path), then the landing directory
# redirect to the ingest task's staged incoming/ dir.
sql_text = sql_text.replace(SIBLING_NS, NS)
sql_text = sql_text.replace(SIBLING_LANDING, INCOMING)

statements = split_sql_statements(sql_text)

# COMMAND ----------

# Only a genuinely missing directory is an empty batch (fresh namespace).
# Any other listing failure (permissions, transient Files API/volume errors)
# must fail this task and block publish_psv/finance — the empty-input branch
# below is destructive (it rewrites the slice empty), and silently taking it
# on an error would be the exact fail-open behaviour this conversion retires.
files = []
try:
    files = [
        f.name for f in dbutils.fs.ls(INCOMING)
        if f.name.startswith("CUSTBILL") and f.name.endswith(".dat")
    ]
except Exception as exc:
    msg = str(exc)
    if "FileNotFoundException" in type(exc).__name__ or "FileNotFoundException" in msg \
            or "does not exist" in msg or "No such file" in msg:
        print(f"incoming dir absent ({exc}); treating as empty input")
    else:
        raise

if files:
    for stmt in statements:
        spark.sql(stmt)
    print(f"parse pipeline executed over {len(files)} staged file(s) for ns={NS}")
else:
    # Explicit empty-input branch: sibling DDL, then rewrite the slice empty.
    for stmt in statements:
        if stmt.upper().startswith("CREATE TABLE IF NOT EXISTS"):
            spark.sql(stmt)
    for table in (
        f"ow_tp.bronze.custbill_parse_raw_{NS}",
        f"ow_tp.silver.custbill_parsed_{NS}",
        f"ow_tp.silver.custbill_parse_quarantine_{NS}",
    ):
        spark.sql(f"INSERT OVERWRITE {table} SELECT * FROM {table} WHERE 1=0")
        print(f"rewrote {table} empty (write-empty-result)")

# COMMAND ----------

for table in (
    f"ow_tp.bronze.custbill_parse_raw_{NS}",
    f"ow_tp.silver.custbill_parsed_{NS}",
    f"ow_tp.silver.custbill_parse_quarantine_{NS}",
):
    count = spark.sql(f"SELECT COUNT(*) FROM {table}").collect()[0][0]
    print(f"{table} rows: {count}")
