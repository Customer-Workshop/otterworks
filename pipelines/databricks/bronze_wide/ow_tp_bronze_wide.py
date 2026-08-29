# Databricks notebook source
# MAGIC %md
# MAGIC # bronze_wide — OW_BILLING wide/denormalised surfaces -> `ow_tp.bronze`
# MAGIC
# MAGIC Loads the four wide tables the billing estate's nightly batch chain maintains
# MAGIC (`CUSTOMER_MASTER` at its full 155-column declared width, the typeless
# MAGIC `ENTITY_ATTR_VALUE` EAV store, and the denormalised `INVOICE_LINE` /
# MAGIC `INVOICE_HEADER` reporting copies) from the unit landing area into Delta, plus
# MAGIC `quarantine_bronze_wide`.
# MAGIC
# MAGIC Rules implemented here, per `.migration/09_semantic_dictionary.md`:
# MAGIC * **D-05/D-06/T4** — `VARCHAR2(9)` free-text dates parse as `DD-MON-YY` with the
# MAGIC   current century (`'31-DEC-99'` -> 2099). Unparseable values quarantine the row
# MAGIC   (`BAD_DATE`); structurally parseable but impossible dates quarantine as
# MAGIC   `DATE_INVALID`. Nothing is silently nulled and nothing is dropped.
# MAGIC * **D-14** — `f_md5_uuid` reimplemented verbatim (lowercased MD5 hex sliced
# MAGIC   8-4-4-4-12) and used for the quarantine row key.
# MAGIC * **D-16** — the `trg_customer_master_seq` rules (`CUST_NAME_UPPER = UPPER(CUST_NAME)`,
# MAGIC   `ROW_VERSION_NO` defaults via `NVL(...,1)`) are retained as pipeline logic.
# MAGIC * **D-23/T6** — every numeric column is pinned to the source's declared decimal
# MAGIC   type; no `DOUBLE` on any money lineage.
# MAGIC * **D-25/T8/T9** — text passes through unchanged: `CHAR` blank padding is preserved
# MAGIC   and NULL stays distinct from the empty string.
# MAGIC * PII is landed in cleartext and restricted with Unity Catalog column masks.
# MAGIC
# MAGIC Restart safety: `MERGE` on the declared natural key plus `ns`, gated on a row hash,
# MAGIC so a second identical run writes nothing.

# COMMAND ----------

import json
from datetime import datetime, timezone

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import DoubleType, FloatType

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "bronze")

NS = dbutils.widgets.get("ns").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").rstrip("/")
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
UNIT = "bronze_wide"
UNIT_ROOT = f"{LANDING_ROOT}/{NS}/{UNIT}"
QUARANTINE_TABLE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"

if not NS:
    raise ValueError("ns is required; every row and every path is namespaced")

# Natural MERGE key per source table (declared, stable — T10).
NATURAL_KEY = {
    "CUSTOMER_MASTER": "CUST_ID",
    "ENTITY_ATTR_VALUE": "EAV_ID",
    "INVOICE_LINE": "LINE_ID",
    "INVOICE_HEADER": "INVOICE_ID",
}
CSV_COLUMNS = {
    "CUSTOMER_MASTER": ["RELATED_ACCT_IDS", "CHILD_ACCT_IDS", "PROMO_CODES_CSV"],
    "INVOICE_LINE": ["GL_ACCT_CSV"],
}
PII_COLUMNS = {
    "CUSTOMER_MASTER": [
        "CUST_NAME", "CUST_NAME_UPPER", "LEGAL_NAME", "DBA_NAME",
        "ADDR_LINE_1", "ADDR_LINE_2", "ADDR_LINE_3", "ADDR_LINE_4",
        "ADDR_LINE_5", "ADDR_LINE_6", "CITY", "ZIP",
        "MAIL_ADDR_LINE_1", "MAIL_ADDR_LINE_2", "MAIL_ADDR_LINE_3",
        "MAIL_ADDR_LINE_4", "MAIL_ADDR_LINE_5", "MAIL_ADDR_LINE_6",
        "MAIL_CITY", "MAIL_ZIP",
        "PHONE1", "PHONE2", "PHONE3", "PHONE4", "FAX",
        "EMAIL_1", "EMAIL_2", "EMAIL_3", "CONTACT_NOTES",
    ],
    "INVOICE_LINE": ["CUST_NAME"],
}
MASK_FUNCTION = f"{CATALOG}.{SCHEMA}.ow_tp_bw_mask_pii"
PII_READER_TABLE = f"{CATALOG}.{SCHEMA}.ow_tp_bw_pii_readers"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}

# Reason codes are closed (.migration/11_quarantine_codes.md); highest priority first.
REASON_PRIORITY = ["KEY_NULL", "KEY_DUPLICATE", "ENC_INVALID",
                   "NUMERIC_OVERFLOW", "DATE_INVALID", "BAD_DATE"]

manifest = json.loads(open(f"{UNIT_ROOT}/_manifest.json").read())
print(json.dumps({"ns": NS, "source": manifest["source"],
                  "source_rows": {t: v["rows"] for t, v in manifest["tables"].items()}},
                 indent=2))

# COMMAND ----------
# MAGIC %md ## Helpers

# COMMAND ----------


def f_md5_uuid(value_col):
    """D-14: MD5 of the input, lowercased hex, sliced 8-4-4-4-12."""
    h = F.lower(F.md5(value_col))
    return F.concat_ws(
        "-",
        F.substring(h, 1, 8), F.substring(h, 9, 4), F.substring(h, 13, 4),
        F.substring(h, 17, 4), F.substring(h, 21, 12),
    )


def canonical(col_name: str, dtype) -> "F.Column":
    """Engine-neutral text form of a value, used for row hashing.

    NULL becomes U+0002 so it stays distinguishable from the empty string (T9);
    decimals render at their declared scale; dates render as ISO seconds.
    """
    c = F.col(col_name)
    t = dtype.simpleString()
    if t.startswith("decimal"):
        rendered = c.cast("string")
    elif t in ("timestamp", "timestamp_ntz", "date"):
        rendered = F.date_format(c, "yyyy-MM-dd HH:mm:ss")
    else:
        rendered = c
    return F.when(c.isNull(), F.lit("\u0002")).otherwise(rendered)


def chunk_columns(declared: list[dict], max_declared: int = 3000):
    """Group columns so each group's concatenation stays inside Oracle's
    4000-byte SQL VARCHAR2 limit; the identical grouping is used on both sides."""
    groups, current, width = [], [], 0
    for col in declared:
        w = col["length"] if col["type"] in ("VARCHAR2", "CHAR") else 40
        if current and width + w > max_declared:
            groups.append(current)
            current, width = [], 0
        current.append(col)
        width += w
    if current:
        groups.append(current)
    return groups


def row_hash_expr(df: DataFrame, declared: list[dict]):
    """Full-width row fingerprint: md5 per column group, then md5 of the groups.

    Chunked so the same expression is expressible in Oracle SQL, which lets recon
    compare every column — including the masked PII ones — without reading
    cleartext out of the lakehouse."""
    types = {f.name: f.dataType for f in df.schema.fields}
    group_hashes = []
    for group in chunk_columns(declared):
        group_hashes.append(
            F.md5(F.concat_ws("\u0001",
                              *[canonical(c["name"], types[c["name"]]) for c in group]))
        )
    return F.md5(F.concat_ws("\u0001", *group_hashes))


def date_classification(col_name: str):
    """Returns (parsed_date_col, reason_col) for a VARCHAR2(9) DD-MON-YY column."""
    raw = F.col(col_name)
    up = F.upper(raw)
    dd = F.regexp_extract(up, r"^(\d{2})-([A-Z]{3})-(\d{2})$", 1)
    mon = F.regexp_extract(up, r"^(\d{2})-([A-Z]{3})-(\d{2})$", 2)
    yy = F.regexp_extract(up, r"^(\d{2})-([A-Z]{3})-(\d{2})$", 3)
    shaped = dd != ""
    month_map = F.create_map(*[x for k, v in MONTHS.items()
                               for x in (F.lit(k), F.lit(v))])
    mnum = month_map[mon]
    # Non-matching values never reach a cast: under ANSI semantics casting the
    # empty capture group would abort the load instead of quarantining the row.
    safe = lambda c: F.when(shaped, c).otherwise(F.lit("0")).cast("int")  # noqa: E731
    # T4/D-05: two-digit years are always the current century.
    year = F.lit(2000) + safe(yy)
    day = safe(dd)
    leap = ((year % 4 == 0) & (year % 100 != 0)) | (year % 400 == 0)
    dim = (F.when(mnum.isin(1, 3, 5, 7, 8, 10, 12), F.lit(31))
            .when(mnum.isin(4, 6, 9, 11), F.lit(30))
            .when(mnum == 2, F.when(leap, F.lit(29)).otherwise(F.lit(28))))
    real = shaped & mnum.isNotNull() & (day >= 1) & (day <= dim)
    parsed = F.when(
        real,
        F.to_date(F.format_string("%04d-%02d-%02d", year, mnum, day), "yyyy-MM-dd"),
    )
    reason = (F.when(raw.isNull(), F.lit(None))
               .when(real, F.lit(None))
               .when(shaped & mnum.isNotNull(), F.lit("DATE_INVALID"))
               .otherwise(F.lit("BAD_DATE")))
    return parsed, reason


def first_reason(pairs):
    """Collapse per-column findings into one code per row, priority ordered."""
    expr = F.lit(None).cast("string")
    detail = F.lit(None).cast("string")
    for code in reversed(REASON_PRIORITY):
        for column, reason_col in pairs:
            hit = reason_col == F.lit(code)
            expr = F.when(hit, F.lit(code)).otherwise(expr)
            detail = F.when(hit, F.lit(column)).otherwise(detail)
    return expr, detail


# COMMAND ----------
# MAGIC %md ## Date parser probe (D-05 / T4 evidence)
# MAGIC
# MAGIC Runs the same `date_classification` code path the load uses over a fixed set of
# MAGIC values so the century window and the two date reason codes are measured output
# MAGIC rather than a claim.  Compared in recon against `pkg_ow_util.f_str2dt` in the
# MAGIC source database.

# COMMAND ----------

PROBE_VALUES = ["31-DEC-99", "01-JAN-00", "28-FEB-25", "29-FEB-24",
                "31-FEB-24", "29-FEB-23", "00-XXX-00", "99-999-99",
                "1/1/1900", "N/A", "12-13-201", "  -   -  "]
probe_df = spark.createDataFrame([(v,) for v in PROBE_VALUES], "SIGNUP_DT string")
_parsed, _reason = date_classification("SIGNUP_DT")
parser_probe = {
    r["SIGNUP_DT"]: {"parsed": (r["parsed"].isoformat() if r["parsed"] else None),
                     "reason": r["reason"]}
    for r in probe_df.select("SIGNUP_DT",
                             _parsed.alias("parsed"),
                             _reason.alias("reason")).collect()
}
print(json.dumps(parser_probe, indent=2))

# COMMAND ----------
# MAGIC %md ## Load

# COMMAND ----------


def build(table: str):
    declared = manifest["tables"][table]["schema"]
    key = NATURAL_KEY[table]
    src_cols = [c["name"] for c in declared]
    date_cols = [c["name"] for c in declared
                 if c["type"] == "VARCHAR2" and c["length"] == 9 and "_DT" in c["name"]]
    money_cols = [c["name"] for c in declared
                  if c["type"] == "NUMBER" and c.get("scale") == 2]

    df = spark.read.parquet(f"{UNIT_ROOT}/{table.lower()}")
    missing = [c for c in src_cols if c not in df.columns]
    if missing or len(df.columns) != len(src_cols):
        raise ValueError(f"{table}: landed width {len(df.columns)} != declared "
                         f"{len(src_cols)} (missing {missing})")
    for f in df.schema.fields:
        if isinstance(f.dataType, (DoubleType, FloatType)):
            raise ValueError(f"{table}.{f.name} landed as {f.dataType}; "
                             "D-23/T6 forbid a float path on a source NUMBER")

    df = df.withColumn("row_hash", row_hash_expr(df, declared))

    # D-16: trigger-resident rules retained as pipeline logic.
    trigger_divergence = 0
    if table == "CUSTOMER_MASTER":
        trigger_divergence = df.filter(
            (~F.upper(F.col("CUST_NAME")).eqNullSafe(F.col("CUST_NAME_UPPER")))
            | F.col("ROW_VERSION_NO").isNull()
        ).count()
        df = (df
              .withColumn("CUST_NAME_UPPER", F.upper(F.col("CUST_NAME")))
              .withColumn("ROW_VERSION_NO", F.coalesce(F.col("ROW_VERSION_NO"), F.lit(1))))

    findings = []

    # KEY_NULL / KEY_DUPLICATE (D-14: the MERGE key must be resolvable).
    findings.append((key, F.when(F.col(key).isNull(), F.lit("KEY_NULL"))))
    dup = (df.groupBy(key).agg(F.countDistinct("row_hash").alias("variants"),
                               F.count(F.lit(1)).alias("occurrences")))
    dup_keys = dup.filter((F.col("occurrences") > 1)).select(key, "variants")
    df = df.join(F.broadcast(dup_keys), on=key, how="left")
    findings.append((key, F.when(F.col("variants").isNotNull(), F.lit("KEY_DUPLICATE"))))

    # D-25: text arrives AL32UTF8 and passes through unchanged; a value carrying the
    # Unicode replacement character means the byte stream did not decode.
    for c in [f.name for f in df.schema.fields
              if f.dataType.simpleString() == "string" and f.name in src_cols]:
        findings.append((c, F.when(F.col(c).contains("\ufffd"), F.lit("ENC_INVALID"))))

    # D-23/T6: a source value that does not fit its pinned decimal type.
    for c in money_cols:
        findings.append((c, F.when(F.abs(F.col(c)) >= F.lit(10 ** 12),
                                   F.lit("NUMERIC_OVERFLOW"))))

    # D-05/D-06/T3/T4: free-text dates.
    parsed_cols = {}
    for c in date_cols:
        parsed, reason = date_classification(c)
        parsed_cols[f"{c}_PARSED"] = parsed
        findings.append((c, reason))

    reason_col, detail_col = first_reason(findings)
    df = df.withColumn("_reason", reason_col).withColumn("_detail", detail_col)

    payload = F.to_json(F.struct(*[F.col(c).cast("string").alias(c) for c in src_cols]))
    quarantined = (df.filter(F.col("_reason").isNotNull())
                     .select(
                         f_md5_uuid(F.concat_ws("|", F.lit(NS), F.lit(table),
                                                F.col(key).cast("string"),
                                                F.col("_reason"), F.col("row_hash"))
                                    ).alias("quarantine_id"),
                         F.lit(NS).alias("ns"),
                         F.lit(UNIT).alias("unit"),
                         F.lit(f"OW_BILLING.{table}").alias("source_table"),
                         F.col(key).cast("string").alias("source_key"),
                         F.col("_reason").alias("quarantine_reason"),
                         F.col("_detail").alias("quarantine_detail"),
                         payload.alias("raw_payload"),
                         F.col("row_hash").alias("row_hash")))

    loaded = df.filter(F.col("_reason").isNull())
    for name, expr in parsed_cols.items():
        loaded = loaded.withColumn(name, expr)
    for c in CSV_COLUMNS.get(table, []):
        # ANOM-GL-ACCT-CSV: the multi-value column is carried verbatim; only the
        # token count is derived beside it so the anomaly is measurable.
        loaded = loaded.withColumn(
            f"{c}_TOKEN_COUNT",
            F.when(F.col(c).isNull(), F.lit(None).cast("int"))
             .otherwise(F.size(F.split(F.col(c), ",", -1))))
    if table == "ENTITY_ATTR_VALUE":
        # ANOM-EAV-TYPELESS: values stay strings; the flag records that a typed
        # value is sitting in an untyped column.
        loaded = loaded.withColumn(
            "ATTR_VALUE_NUMERIC_LIKE",
            F.col("ATTR_VALUE").rlike(r"^\s*-?\d+(\.\d+)?\s*$"))

    derived = [c for c in loaded.columns
               if c not in src_cols and c not in ("_reason", "_detail", "variants")]
    loaded = (loaded.select(*src_cols, *derived)
                    .withColumn("ns", F.lit(NS))
                    .withColumn("src_extracted_at",
                                F.lit(manifest["source"]["extracted_at"]).cast("timestamp"))
                    .withColumn("loaded_at", F.current_timestamp()))
    loaded = loaded.toDF(*[c.lower() for c in loaded.columns])
    return loaded, quarantined, {
        "source_rows": manifest["tables"][table]["rows"],
        "date_columns": len(date_cols),
        "money_columns": money_cols,
        "trigger_rule_divergences": trigger_divergence,
    }


def merge(name: str, df: DataFrame, key_cols: list[str]) -> dict:
    """Insert new rows, update changed ones, never delete.

    There is deliberately no `WHEN NOT MATCHED BY SOURCE` clause: the MERGE only
    ever touches keys present in this run's input, so an empty input for one `ns`
    is a no-op and cannot remove another namespace's slice.
    """
    if not spark.catalog.tableExists(name):
        df.limit(0).write.format("delta").saveAsTable(name)
    view = f"src_{name.split('.')[-1]}"
    df.createOrReplaceTempView(view)
    on = " AND ".join(f"t.{c} = s.{c}" for c in key_cols)
    update = ", ".join(f"t.{c} = s.{c}" for c in df.columns
                       if c not in key_cols and c != "loaded_at")
    spark.sql(f"""
        MERGE INTO {name} t
        USING {view} s ON {on}
        WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET {update}
        WHEN NOT MATCHED THEN INSERT *
    """)
    metrics = (spark.sql(f"DESCRIBE HISTORY {name} LIMIT 1")
                    .select("operationMetrics").collect()[0][0])
    return {k: int(v) for k, v in metrics.items()
            if k in ("numTargetRowsInserted", "numTargetRowsUpdated",
                     "numTargetRowsDeleted", "numOutputRows")}


# COMMAND ----------

results = {}
quarantine_frames = []
for table, (target, key) in {
    "CUSTOMER_MASTER": ("customer_master", "CUST_ID"),
    "ENTITY_ATTR_VALUE": ("entity_attr_value", "EAV_ID"),
    "INVOICE_LINE": ("invoice_line", "LINE_ID"),
    "INVOICE_HEADER": ("invoice_header", "INVOICE_ID"),
}.items():
    loaded, quarantined, info = build(table)
    full = f"{CATALOG}.{SCHEMA}.{target}"
    loaded_rows = loaded.count()
    quarantined_rows = quarantined.count()
    info["loaded_rows"] = loaded_rows
    info["quarantined_rows"] = quarantined_rows
    if loaded_rows + quarantined_rows != info["source_rows"]:
        raise ValueError(f"{table}: {loaded_rows} + {quarantined_rows} != "
                         f"{info['source_rows']} — quarantine accounting must be exact")
    rate = quarantined_rows / max(info["source_rows"], 1) * 100.0
    info["quarantine_rate_pct"] = round(rate, 4)
    if rate > 5.0:
        raise ValueError(f"STOP/quarantine-threshold: {table} quarantined "
                         f"{rate:.2f}% of source rows (limit 5%)")
    info["merge_metrics"] = merge(full, loaded, ["ns", key.lower()])
    quarantine_frames.append(quarantined.withColumn("loaded_at", F.current_timestamp()))
    results[table] = info
    print(table, json.dumps(info))

# COMMAND ----------

q = quarantine_frames[0]
for extra in quarantine_frames[1:]:
    q = q.unionByName(extra)
results["quarantine_merge_metrics"] = merge(QUARANTINE_TABLE, q, ["ns", "quarantine_id"])

# COMMAND ----------
# MAGIC %md ## PII column masks (ACC-PII-MASK)

# COMMAND ----------

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {PII_READER_TABLE} (principal STRING)
    COMMENT 'Principals allowed to read bronze_wide PII cleartext'
""")
spark.sql(f"""
    CREATE OR REPLACE FUNCTION {MASK_FUNCTION}(v STRING)
    RETURNS STRING
    COMMENT 'Column mask: cleartext only for principals registered as bronze_wide PII readers'
    RETURN CASE
        WHEN v IS NULL THEN NULL
        WHEN current_user() IN (SELECT principal FROM {PII_READER_TABLE}) THEN v
        ELSE '***REDACTED***'
    END
""")
for table, cols in PII_COLUMNS.items():
    target = f"{CATALOG}.{SCHEMA}.{table.lower()}"
    existing = {r["col_name"] for r in spark.sql(f"DESCRIBE TABLE {target}").collect()}
    for c in cols:
        if c.lower() not in existing:
            raise ValueError(f"{target}: PII column {c} missing from target")
        try:
            spark.sql(f"ALTER TABLE {target} ALTER COLUMN {c.lower()} DROP MASK")
        except Exception:  # no mask attached yet
            pass
        spark.sql(f"ALTER TABLE {target} ALTER COLUMN {c.lower()} "
                  f"SET MASK {MASK_FUNCTION}")
results["pii_masked_columns"] = {t: len(c) for t, c in PII_COLUMNS.items()}

# COMMAND ----------

summary = {
    "unit": UNIT,
    "ns": NS,
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "source": manifest["source"],
    "tables": results,
    "parser_probe": parser_probe,
}
print(json.dumps(summary, indent=2, default=str))
dbutils.notebook.exit(json.dumps(summary, default=str))
