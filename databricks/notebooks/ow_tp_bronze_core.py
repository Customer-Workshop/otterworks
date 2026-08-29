# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_bronze_core
# MAGIC
# MAGIC Bronze load of the OW_BILLING normalised core (13 tables) into `ow_tp.bronze.*`,
# MAGIC plus `ow_tp.bronze.quarantine_bronze_core`.
# MAGIC
# MAGIC Behaviour is fixed by `docs/tech-partnerships/contracts/bronze_core.json` and the
# MAGIC Oracle -> Databricks dictionary in `.migration/09_semantic_dictionary.md`:
# MAGIC
# MAGIC * every column is landed as text and cast to a **declared** target type
# MAGIC   (D-23/T6: no unbounded `NUMBER` may land as `DOUBLE`; money is `DECIMAL(14,2)`),
# MAGIC * `NULL` and `''` stay distinct, no trimming, no normalisation (encoding policy),
# MAGIC * rejects carry one reason from the closed set in `.migration/11_quarantine_codes.md`
# MAGIC   with `ns`, source table and the raw source payload,
# MAGIC * `loaded_rows + quarantined_rows == source_rows` per table, quarantine > 5% halts,
# MAGIC * loads are `MERGE` on the natural key plus `ns`, so a second identical run is a no-op,
# MAGIC * validation is per batch (`trigger_granularity: per-batch`), not per row.
# MAGIC
# MAGIC The column/type contract lives in `databricks/ddl/bronze_core_spec.json`, deployed next
# MAGIC to this notebook; the extractor and the recon read the same file, so the pinned types
# MAGIC cannot drift between load and reconciliation.

# COMMAND ----------

import json
import os

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "bronze")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/bronze_core_spec.json")
dbutils.widgets.text("batch_id", "")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()

if not NS:
    raise ValueError("ns is required: every target row and every volume path is ns-scoped")
if CATALOG != "ow_tp":
    raise ValueError("this unit only reads and writes the ow_tp catalog")

UNIT = "bronze_core"
LANDING = f"{LANDING_ROOT}/{NS}/{UNIT}"
QUARANTINE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"

if not BATCH_ID:
    BATCH_ID = (
        spark.sql("SELECT date_format(current_timestamp(), 'yyyyMMddHHmmss')").collect()[0][0]
    )


def _load_spec(path: str) -> dict:
    """Spec is deployed as a workspace file; fall back to the copy in the landing folder."""
    candidates = [path, f"{LANDING}/_spec.json"]
    for cand in candidates:
        try:
            with open(cand, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            continue
    raise FileNotFoundError(f"bronze_core spec not found at any of {candidates}")


SPEC = _load_spec(SPEC_PATH)
TABLES = SPEC["tables"]
REASONS = set(SPEC["quarantine_reasons"])
print(f"ns={NS} landing={LANDING} batch_id={BATCH_ID} tables={len(TABLES)}")

# COMMAND ----------

# MAGIC %md ## Target DDL
# MAGIC
# MAGIC Liquid clustering on the natural key plus `ns` (D-22). No index port, no ZORDER.
# MAGIC `CREATE TABLE IF NOT EXISTS` only: this unit never drops or replaces a shared table,
# MAGIC and `tenants`/`subscriptions` are written again by a later wave.

# COMMAND ----------

TS_FMT = SPEC["extract_formats"]["ts"]
DATE_FMT = SPEC["extract_formats"]["date"]
SPARK_TS_FMT = "yyyy-MM-dd HH:mm:ss.SSSSSS"
SPARK_DATE_FMT = "yyyy-MM-dd HH:mm:ss"
NUMERIC_CLASSES = {"code", "count", "money", "rate", "surrogate"}
MONEY_CLASSES = {"money", "rate"}
TEMPORAL_CLASSES = {"date", "ts"}


def q(name: str) -> str:
    return f"`{name}`"


def full_name(target: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{target}"


def ensure_target(tbl: dict) -> None:
    cols = ",\n  ".join(
        f"{q(c['name'])} {c['target_type']}" for c in tbl["columns"]
    )
    cluster = ", ".join([q(k) for k in tbl["key"]] + ["`ns`"])
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {full_name(tbl['target'])} (
          {cols},
          `ns` STRING NOT NULL,
          `_source_table` STRING NOT NULL,
          `_loaded_at` TIMESTAMP NOT NULL
        )
        USING DELTA
        CLUSTER BY ({cluster})
        COMMENT 'OW_BILLING.{tbl["source"]} bronze image, one row per source row per ns.'
        """
    )


spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {QUARANTINE} (
      `ns` STRING NOT NULL,
      `source_table` STRING NOT NULL,
      `source_key` STRING,
      `source_row_hash` STRING NOT NULL,
      `quarantine_reason` STRING NOT NULL,
      `raw_payload` STRING NOT NULL,
      `detected_at` TIMESTAMP NOT NULL,
      `batch_id` STRING NOT NULL
    )
    USING DELTA
    CLUSTER BY (`ns`, `source_table`, `quarantine_reason`)
    COMMENT 'Replayable rejects for bronze_core. One reason per row, from the closed set.'
    """
)

for tbl in TABLES:
    ensure_target(tbl)

# billing_audit_log is data only: parity is not claimed on it (D-20) and the retired
# JOB_PURGE_AUDIT_LOG retention becomes a table property rather than a job.
spark.sql(
    f"""
    ALTER TABLE {full_name('billing_audit_log')} SET TBLPROPERTIES (
      'ow_tp.retention_days' = '90',
      'ow_tp.parity_scope' = 'excluded',
      'delta.logRetentionDuration' = 'interval 90 days',
      'delta.deletedFileRetentionDuration' = 'interval 90 days'
    )
    """
)

# COMMAND ----------

# MAGIC %md ## Row-level validation
# MAGIC
# MAGIC One reason per rejected row, evaluated in a fixed order so the reason is deterministic.
# MAGIC Only codes from `.migration/11_quarantine_codes.md` are emitted; a cause with no code in
# MAGIC that closed set halts the run instead of being folded into a neighbouring code.

# COMMAND ----------


def raw_view(tbl: dict) -> str:
    """Land the extract as text: no inferred types, so nothing can silently become DOUBLE."""
    from pyspark.sql.types import StringType, StructField, StructType

    schema = StructType([StructField(c["name"], StringType(), True) for c in tbl["columns"]])
    path = f"{LANDING}/{tbl['source'].lower()}.json"
    df = (
        spark.read.schema(schema)
        .option("mode", "FAILFAST")
        .option("multiLine", "false")
        .json(path)
    )
    view = f"raw_{tbl['target']}"
    df.createOrReplaceTempView(view)
    return view


def manifest(tbl: dict) -> dict:
    with open(f"{LANDING}/{tbl['source'].lower()}.manifest.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


def check_no_schema_drift(tbl: dict) -> None:
    """An undeclared source column fails the unit (malformed_record_policy)."""
    src_cols = [c.lower() for c in manifest(tbl)["source_columns"]]
    spec_cols = [c["name"].lower() for c in tbl["columns"]]
    if src_cols != spec_cols:
        raise RuntimeError(
            f"schema drift on OW_BILLING.{tbl['source']}: source={src_cols} spec={spec_cols}; "
            "an undeclared source column is a correctness event, not something to ignore"
        )


def numeric_shape(col: str) -> str:
    return rf"{q(col)} RLIKE '^-?[0-9]+(\\.[0-9]+)?$'"


def reason_expr(tbl: dict) -> str:
    """CASE returning the single quarantine reason for a row, or NULL when the row is clean."""
    whens = []

    text_cols = [c["name"] for c in tbl["columns"] if c["class"] in ("text", "flag")]
    if text_cols:
        enc = " OR ".join(f"{q(c)} LIKE '%\\ufffd%'" for c in text_cols)
        whens.append(f"WHEN {enc} THEN 'ENC_INVALID'")

    key_null = " OR ".join(f"{q(k)} IS NULL" for k in tbl["key"])
    whens.append(f"WHEN {key_null} THEN 'KEY_NULL'")

    for c in tbl["columns"]:
        if c["class"] not in TEMPORAL_CLASSES:
            continue
        fmt = SPARK_TS_FMT if c["class"] == "ts" else SPARK_DATE_FMT
        shaped = rf"{q(c['name'])} RLIKE '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}} '"
        whens.append(
            f"WHEN {q(c['name'])} IS NOT NULL "
            f"AND try_to_timestamp({q(c['name'])}, '{fmt}') IS NULL "
            f"THEN CASE WHEN {shaped} THEN 'DATE_INVALID' ELSE 'BAD_DATE' END"
        )

    for c in tbl["columns"]:
        if c["class"] not in NUMERIC_CLASSES:
            continue
        col, target = q(c["name"]), c["target_type"]
        non_numeric = "AMT_NON_NUMERIC" if c["class"] in MONEY_CLASSES else "NUMERIC_OVERFLOW"
        whens.append(
            f"WHEN {col} IS NOT NULL AND NOT ({numeric_shape(c['name'])}) THEN '{non_numeric}'"
        )
        # Fits the declared type exactly, or it is an overflow / silent rescale.
        whens.append(
            f"WHEN {col} IS NOT NULL AND (try_cast({col} AS {target}) IS NULL "
            f"OR cast(try_cast({col} AS {target}) AS DECIMAL(38,10)) "
            f"<> cast({col} AS DECIMAL(38,10))) THEN 'NUMERIC_OVERFLOW'"
        )

    for chk in SPEC["code_checks"]:
        if chk["table"] != tbl["target"]:
            continue
        whens.append(f"WHEN NOT `_code_ok__{chk['column']}` THEN '{chk['reason']}'")

    whens.append("WHEN `_key_dup_cnt` > 1 THEN 'KEY_DUPLICATE'")
    return "CASE " + " ".join(whens) + " ELSE NULL END"


def annotated_cte(tbl: dict, view: str) -> str:
    """Adds the per-batch context a reason needs: key duplication and code validity."""
    key_expr = ", ".join(q(k) for k in tbl["key"])
    code_cols, joins = [], []
    for i, chk in enumerate(SPEC["code_checks"]):
        if chk["table"] != tbl["target"]:
            continue
        alias = f"cd{i}"
        code_cols.append(
            f"({alias}.`code_val` IS NOT NULL) AS `_code_ok__{chk['column']}`"
        )
        joins.append(
            f"LEFT JOIN {full_name('codes')} {alias} "
            f"ON {alias}.`ns` = '{NS}' AND {alias}.`code_type` = '{chk['code_type']}' "
            f"AND {alias}.`code_val` = try_cast(r.{q(chk['column'])} AS INT)"
        )
    extra = ("," + ",".join(code_cols)) if code_cols else ""
    return (
        f"SELECT r.*, count(*) OVER (PARTITION BY {key_expr}) AS `_key_dup_cnt`{extra} "
        f"FROM {view} r " + " ".join(joins)
    )


def cast_expr(c: dict) -> str:
    col = q(c["name"])
    if c["class"] == "ts":
        return f"try_to_timestamp({col}, '{SPARK_TS_FMT}')"
    if c["class"] == "date":
        return f"try_to_timestamp({col}, '{SPARK_DATE_FMT}')"
    if c["class"] in NUMERIC_CLASSES:
        return f"cast({col} AS {c['target_type']})"
    return col  # text and flags pass through byte-for-byte, padding and '' included

# COMMAND ----------

# MAGIC %md ## Load
# MAGIC
# MAGIC `MERGE` on the natural key plus `ns`. The update clause only fires when a payload column
# MAGIC actually differs (null-safe `<=>`), so an identical rerun reports zero updated and zero
# MAGIC inserted rows. `_loaded_at` is set on insert only, and is never part of the comparison.

# COMMAND ----------

results = {}


def load_table(tbl: dict) -> dict:
    target, source = tbl["target"], tbl["source"]
    check_no_schema_drift(tbl)
    view = raw_view(tbl)
    src_rows = spark.table(view).count()
    declared_rows = manifest(tbl)["source_rows"]
    if src_rows != declared_rows:
        raise RuntimeError(
            f"{source}: landed {src_rows} rows, extractor declared {declared_rows}"
        )

    raw_cols = ", ".join(q(c["name"]) for c in tbl["columns"])
    ann = annotated_cte(tbl, view)
    reason = reason_expr(tbl)
    key_concat = " || '|' || ".join(f"coalesce({q(k)}, '<null>')" for k in tbl["key"])
    payload = f"to_json(struct({raw_cols}))"

    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW judged_{target} AS
        WITH annotated AS ({ann})
        SELECT *, {reason} AS `_reason`, {payload} AS `_raw_payload`
        FROM annotated
        """
    )
    counts = {
        r["_reason"]: r["n"]
        for r in spark.sql(
            f"SELECT `_reason`, count(*) AS n FROM judged_{target} GROUP BY `_reason`"
        ).collect()
    }
    bad_reasons = {r for r in counts if r is not None and r not in REASONS}
    if bad_reasons:
        raise RuntimeError(f"{source}: reason(s) outside the closed set: {sorted(bad_reasons)}")
    quarantined = sum(n for r, n in counts.items() if r is not None)

    # Rejects: idempotent by (ns, source_table, row hash, reason) so a rerun re-adds nothing.
    spark.sql(
        f"""
        MERGE INTO {QUARANTINE} t
        USING (
          SELECT
            '{NS}' AS `ns`,
            'OW_BILLING.{source}' AS `source_table`,
            {key_concat} AS `source_key`,
            md5(`_raw_payload`) AS `source_row_hash`,
            `_reason` AS `quarantine_reason`,
            `_raw_payload` AS `raw_payload`,
            current_timestamp() AS `detected_at`,
            '{BATCH_ID}' AS `batch_id`
          FROM judged_{target}
          WHERE `_reason` IS NOT NULL
        ) s
        ON t.`ns` = s.`ns` AND t.`source_table` = s.`source_table`
           AND t.`source_row_hash` = s.`source_row_hash`
           AND t.`quarantine_reason` = s.`quarantine_reason`
        WHEN NOT MATCHED THEN INSERT *
        """
    )

    typed = ", ".join(f"{cast_expr(c)} AS {q(c['name'])}" for c in tbl["columns"])
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW clean_{target} AS
        SELECT {typed}, '{NS}' AS `ns`, 'OW_BILLING.{source}' AS `_source_table`
        FROM judged_{target} WHERE `_reason` IS NULL
        """
    )
    loaded = spark.table(f"clean_{target}").count()
    if loaded + quarantined != src_rows:
        raise RuntimeError(
            f"{source}: {loaded} + {quarantined} != {src_rows} (ACC-QUAR accounting)"
        )
    if src_rows and quarantined / src_rows > 0.05:
        raise RuntimeError(
            f"STOPA-QUARANTINE {source}: {quarantined}/{src_rows} rejected "
            f"({100.0 * quarantined / src_rows:.2f}% > 5%); unit halts for escalation"
        )

    frozen = {
        f["column"]: f["value"]
        for f in SPEC["frozen_status"]
        if f["table"] == target
    }
    payload_cols = [c["name"] for c in tbl["columns"] if c["name"] not in tbl["key"]]

    def merged_value(name: str) -> str:
        if name in frozen:
            # trg_sub_no_uncancel: a cancelled row can never leave the cancelled state.
            return f"CASE WHEN t.{q(name)} = {frozen[name]} THEN {frozen[name]} ELSE s.{q(name)} END"
        return f"s.{q(name)}"

    on = " AND ".join([f"t.{q(k)} = s.{q(k)}" for k in tbl["key"]] + ["t.`ns` = s.`ns`"])
    differs = " OR ".join(
        f"NOT (t.{q(c)} <=> {merged_value(c)})" for c in payload_cols
    ) or "false"
    set_clause = ", ".join(f"t.{q(c)} = {merged_value(c)}" for c in payload_cols)
    insert_cols = [c["name"] for c in tbl["columns"]] + ["ns", "_source_table", "_loaded_at"]
    insert_vals = [f"s.{q(c['name'])}" for c in tbl["columns"]] + [
        "s.`ns`",
        "s.`_source_table`",
        "current_timestamp()",
    ]
    metrics = spark.sql(
        f"""
        MERGE INTO {full_name(target)} t
        USING clean_{target} s
        ON {on}
        WHEN MATCHED AND ({differs}) THEN UPDATE SET {set_clause}
        WHEN NOT MATCHED THEN INSERT ({", ".join(q(c) for c in insert_cols)})
          VALUES ({", ".join(insert_vals)})
        """
    ).collect()[0].asDict()

    res = {
        "source_table": f"OW_BILLING.{source}",
        "source_rows": src_rows,
        "loaded_rows": loaded,
        "quarantined_rows": quarantined,
        "quarantine_by_reason": {r: n for r, n in counts.items() if r is not None},
        "merge_rows_inserted": int(metrics.get("num_inserted_rows", 0)),
        "merge_rows_updated": int(metrics.get("num_updated_rows", 0)),
        "merge_rows_deleted": int(metrics.get("num_deleted_rows", 0)),
        "target_rows_ns": spark.sql(
            f"SELECT count(*) c FROM {full_name(target)} WHERE `ns` = '{NS}'"
        ).collect()[0]["c"],
        "parity_scope": bool(tbl["parity"]),
    }
    print(json.dumps({target: res}))
    return res


for tbl in TABLES:
    results[tbl["target"]] = load_table(tbl)

# COMMAND ----------

# MAGIC %md ## Source rules with no reason code, and the type pins
# MAGIC
# MAGIC `trg_usage_events_check` also rejects `units <= 0`. The closed reason set has no code for
# MAGIC it, so a non-zero count stops the unit for central triage (D-16) rather than borrowing a
# MAGIC code. `ANOM-NUMBER-UNBOUNDED` is detected here from the declared spec and verified against
# MAGIC the types Unity Catalog actually created.

# COMMAND ----------

halts = []
for chk in SPEC["positive_checks"]:
    n = spark.sql(
        f"SELECT count(*) c FROM judged_{chk['table']} "
        f"WHERE `_reason` IS NULL AND cast({q(chk['column'])} AS DECIMAL(38,0)) <= 0"
    ).collect()[0]["c"]
    if n:
        halts.append(
            f"{chk['table']}.{chk['column']} <= 0 on {n} row(s): {chk['source']} rejects these "
            "and no reason code in .migration/11_quarantine_codes.md covers it"
        )
print("positive_checks_violations:", halts)

unpinned = [
    {
        "column": f"OW_BILLING.{t['source']}.{c['name']}",
        "oracle_type": c["oracle_type"],
        "target_type": c["target_type"],
        "class": c["class"],
    }
    for t in TABLES
    for c in t["columns"]
    if not c["scale_declared"]
]

actual_types = {
    f"{r['table_name']}.{r['column_name']}": r["full_data_type"]
    for r in spark.sql(
        f"""
        SELECT table_name, column_name, full_data_type
        FROM {CATALOG}.information_schema.columns
        WHERE table_schema = '{SCHEMA}'
          AND table_name IN ({", ".join(chr(39) + t['target'] + chr(39) for t in TABLES)})
        """
    ).collect()
}
floats = {k: v for k, v in actual_types.items() if v.lower() in ("double", "float")}
money_types = {
    f"{t['target']}.{c['name']}": actual_types.get(f"{t['target']}.{c['name']}")
    for t in TABLES
    for c in t["columns"]
    if c["class"] == "money"
}
bad_money = {k: v for k, v in money_types.items() if v != "decimal(14,2)"}
if floats or bad_money:
    halts.append(f"ACC-MONEY/ACC-TYPES: float columns={floats} non-DECIMAL(14,2) money={bad_money}")

anomaly = {
    "id": "ANOM-NUMBER-UNBOUNDED",
    "detected": bool(unpinned),
    "detector": "spec vs ow_tp.information_schema.columns after load",
    "unpinned_scale_source_columns": len(unpinned),
    "columns": unpinned,
    "money_target_types": money_types,
    "float_columns_in_unit": floats,
}
print(json.dumps(anomaly, indent=2)[:4000])

# COMMAND ----------

# MAGIC %md ## Run summary
# MAGIC
# MAGIC Written to the landing volume under `<ns>/bronze_core/_runs/` so the recon reads measured
# MAGIC output instead of anything hand-written, and printed for the job run log.

# COMMAND ----------

summary = {
    "unit": UNIT,
    "job": SPEC["job_name"],
    "ns": NS,
    "batch_id": BATCH_ID,
    "catalog": CATALOG,
    "schema": SCHEMA,
    "landing": LANDING,
    "trigger_granularity": SPEC.get("trigger_granularity", "per-batch"),
    "tables": results,
    "totals": {
        "source_rows": sum(r["source_rows"] for r in results.values()),
        "loaded_rows": sum(r["loaded_rows"] for r in results.values()),
        "quarantined_rows": sum(r["quarantined_rows"] for r in results.values()),
    },
    "planted_anomaly_detections": [anomaly],
    "halts": halts,
}

os.makedirs(f"{LANDING}/_runs", exist_ok=True)
with open(f"{LANDING}/_runs/{BATCH_ID}.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2, sort_keys=True)

print(json.dumps(summary["totals"]))
if halts:
    raise RuntimeError("bronze_core halted: " + " | ".join(halts))
dbutils.notebook.exit(json.dumps({"batch_id": BATCH_ID, "totals": summary["totals"]}))
