# Databricks notebook source
# MAGIC %md
# MAGIC # bronze_hist — CUSTOMER_MASTER_HIST / SUBSCRIPTIONS_HIST
# MAGIC
# MAGIC The billing estate records every update and delete of a customer account and
# MAGIC of a subscription in a companion `_HIST` table. Those rows are not an audit
# MAGIC sidecar: `HIST_OP = 'DEL'` means the account is gone from `CUSTOMER_MASTER`,
# MAGIC so its last known state — balances, addresses, contact history — survives
# MAGIC only here. This notebook migrates both tables in full, every row, and keeps
# MAGIC rows whose customer no longer exists (D-17).
# MAGIC
# MAGIC What it does, and what it deliberately does not do:
# MAGIC
# MAGIC * `HIST_DT` is a `VARCHAR2` in the estate's `DD-MON-YY HH24:MI:SS` spelling.
# MAGIC   It is parsed explicitly, two-digit year into the current century (D-05),
# MAGIC   time component preserved to the second (T7). A value no dictionary format
# MAGIC   can parse quarantines the row as `BAD_DATE` (D-06) — it is never nulled
# MAGIC   away the way `f_str2dt` does in source.
# MAGIC * The other `VARCHAR2(9)` date columns copied into the customer history are
# MAGIC   carried through as source text, byte for byte. Bronze preserves the estate's
# MAGIC   values; parsing those columns belongs to the unit that owns
# MAGIC   `CUSTOMER_MASTER`.
# MAGIC * Every column gets an explicit target type taken from the source data
# MAGIC   dictionary (D-23/T6); money is `DECIMAL(14,2)` and no value travels through
# MAGIC   a float. A value that does not fit its pinned type quarantines as
# MAGIC   `NUMERIC_OVERFLOW` rather than being widened or rounded.
# MAGIC * Restart safety is a `MERGE` on `ns` plus a deterministic key built with the
# MAGIC   estate's own `f_md5_uuid` (D-14), so a second identical run is a no-op.
# MAGIC * No capture trigger is recreated and no new `_HIST` row is ever written by
# MAGIC   the target. Change history from here forward is Delta history.

# COMMAND ----------

import json
import re

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")

UNIT = "bronze_hist"
NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SCHEMA = "bronze"

if not re.fullmatch(r"[a-z0-9_]{1,24}", NS):
    raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {NS!r}")
if not CATALOG.startswith("ow_tp"):
    raise ValueError(f"refusing to write outside the ow_tp catalog: {CATALOG!r}")

LANDING = f"{LANDING_ROOT}/{NS}/{UNIT}"
TARGETS = {
    "customer_master_hist": f"{CATALOG}.{SCHEMA}.customer_master_hist",
    "subscriptions_hist": f"{CATALOG}.{SCHEMA}.subscriptions_hist",
}
QUARANTINE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"

# The rejection codes are a closed set. A cause not listed here stops the unit
# so a code can be added centrally, rather than being folded into a catch-all.
QUARANTINE_CODES = ("BAD_DATE", "KEY_NULL", "KEY_DUPLICATE", "NUMERIC_OVERFLOW", "ENC_INVALID")
QUARANTINE_HALT_RATE = 0.05

# COMMAND ----------

# MAGIC %md
# MAGIC ## Source shape
# MAGIC
# MAGIC The landing manifest carries the source data dictionary for both tables, so
# MAGIC the target types below are the source's own precision and scale rather than
# MAGIC an inference from the data. A column the estate has that this unit does not
# MAGIC know about is schema drift no one declared: the load fails on it instead of
# MAGIC ignoring it.

# COMMAND ----------

# Column counts as declared in the estate's schema, checked against the manifest
# before anything is written.
EXPECTED_COLUMN_COUNT = {"customer_master_hist": 158, "subscriptions_hist": 10}

# The natural key of each source table. HIST_ID is a sequence surrogate (D-15):
# it is carried through and asserted unique, never regenerated and never compared
# by value.
NATURAL_KEY = {"customer_master_hist": "hist_id", "subscriptions_hist": "hist_id"}

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# HIST_DT parse, spelled out rather than delegated to a pattern string:
#   * the two-digit year maps into the current century, 26 -> 2026 (D-05). A bare
#     to_timestamp(s, 'dd-MMM-yy') would apply Java's 80-year pivot instead and
#     silently move history decades.
#   * the month abbreviation is matched literally, so the result does not depend
#     on the session locale.
#   * the time component is kept to the second (T7).
#   * anything the pattern does not match, or that is structurally impossible
#     (31-FEB), yields NULL and the row quarantines as BAD_DATE.
_MONTH_CASE = " ".join(f"WHEN '{m}' THEN '{i + 1:02d}'" for i, m in enumerate(MONTHS))
HIST_DT_TS_EXPR = f"""
CASE WHEN hist_dt RLIKE '^[0-9]{{2}}-[A-Za-z]{{3}}-[0-9]{{2}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}$' THEN
  try_to_timestamp(
    concat(
      cast(2000 + cast(substr(hist_dt, 8, 2) AS INT) AS STRING), '-',
      CASE upper(substr(hist_dt, 4, 3)) {_MONTH_CASE} END, '-',
      substr(hist_dt, 1, 2), ' ', substr(hist_dt, 11, 8)
    ),
    'yyyy-MM-dd HH:mm:ss')
END
""".strip()

# COMMAND ----------


def f_md5_uuid(expr: str) -> str:
    """`pkg_ow_util.f_md5_uuid` reimplemented verbatim (D-14).

    MD5 of the input, lowercase hex, sliced 8-4-4-4-12. The estate derives every
    generated primary key this way, and reusing it is what makes a MERGE-based
    restart safe: the same source row always produces the same target key.
    """
    return (
        f"concat_ws('-', substr(lower(md5({expr})), 1, 8), substr(lower(md5({expr})), 9, 4), "
        f"substr(lower(md5({expr})), 13, 4), substr(lower(md5({expr})), 17, 4), "
        f"substr(lower(md5({expr})), 21, 12))"
    )


def merge_operation_metrics(table: str) -> dict:
    """Row counts Delta recorded for the MERGE that just ran.

    A rerun that changes nothing must show zeroes here; the numbers come from
    the table's own history, not from the notebook's bookkeeping.
    """
    row = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]
    metrics = row["operationMetrics"] or {}
    return {
        "version": row["version"],
        "operation": row["operation"],
        "rows_inserted": int(metrics.get("numTargetRowsInserted", 0)),
        "rows_updated": int(metrics.get("numTargetRowsUpdated", 0)),
        "rows_deleted": int(metrics.get("numTargetRowsDeleted", 0)),
    }


def read_manifest() -> dict:
    text = "".join(
        row.value for row in spark.read.text(f"{LANDING}/manifest.json", wholetext=True).collect()
    )
    return json.loads(text)


def source_columns(manifest: dict, table: str) -> list[dict]:
    columns = manifest["tables"][table]["columns"]
    if len(columns) != EXPECTED_COLUMN_COUNT[table]:
        raise ValueError(
            f"{table}: source presents {len(columns)} columns, this unit is declared for "
            f"{EXPECTED_COLUMN_COUNT[table]}. Undeclared schema drift stops the unit."
        )
    return columns


def typed_expr(column: dict) -> str:
    """Cast a landed source value into its pinned target type.

    try_cast, not cast: a value that does not fit is a row to account for, not an
    exception that loses the whole batch.
    """
    name, target = column["name"], column["target_type"]
    if target == "STRING":
        return f"`{name}`"
    return f"try_cast(`{name}` AS {target})"


def ddl_columns(columns: list[dict]) -> str:
    body = ",\n  ".join(f"`{c['name']}` {c['target_type']}" for c in columns)
    return body


# COMMAND ----------

# MAGIC %md
# MAGIC ## Target tables
# MAGIC
# MAGIC Clustered on the natural key plus `ns` (D-22): the estate's 25 indexes served
# MAGIC an access pattern that does not survive the move, so they are not ported
# MAGIC one for one.

# COMMAND ----------


def ensure_target(table: str, columns: list[dict]) -> None:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TARGETS[table]} (
          ns STRING NOT NULL COMMENT 'Migration namespace this row belongs to',
          hist_uid STRING NOT NULL COMMENT 'f_md5_uuid(ns|table|hist_id): deterministic MERGE key (D-14)',
          {ddl_columns(columns)},
          hist_dt_ts TIMESTAMP COMMENT 'HIST_DT parsed under D-05/D-06, seconds preserved',
          hist_customer_absent BOOLEAN COMMENT 'Customer no longer present in CUSTOMER_MASTER at extract time',
          row_hash STRING NOT NULL COMMENT 'sha2 of the source row as landed; lets a rerun skip unchanged rows',
          source_table STRING NOT NULL,
          source_file STRING NOT NULL,
          loaded_at TIMESTAMP NOT NULL COMMENT 'When this row last changed, not when the job last ran'
        )
        USING DELTA
        CLUSTER BY (ns, hist_id)
        COMMENT 'Legacy {table.upper()} migrated as a first-class table (D-17): HIST_OP UPD/DEL preserved, rows for deleted customers retained.'
    """)


def ensure_quarantine() -> None:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {QUARANTINE} (
          ns STRING NOT NULL,
          quarantine_uid STRING NOT NULL COMMENT 'f_md5_uuid(ns|source_table|hist_id)',
          source_table STRING NOT NULL,
          source_file STRING NOT NULL,
          natural_key STRING COMMENT 'Declared natural key value of the rejected row',
          quarantine_reason STRING NOT NULL COMMENT 'One code from .migration/11_quarantine_codes.md',
          quarantine_detail STRING,
          row_hash STRING NOT NULL COMMENT 'sha2 of the source row as landed',
          raw_payload STRING NOT NULL COMMENT 'Source row exactly as landed, so it can be replayed after a dictionary fix',
          quarantined_at TIMESTAMP NOT NULL
        )
        USING DELTA
        CLUSTER BY (ns, source_table)
        COMMENT 'Rejected bronze_hist rows. Quarantine is accounting, not disposal: loaded + quarantined = source.'
    """)


# COMMAND ----------

# MAGIC %md
# MAGIC ## Load
# MAGIC
# MAGIC Validation runs before the write and assigns exactly one reason code per
# MAGIC rejected row, in a fixed precedence: a row with no usable key cannot be
# MAGIC merged at all, so `KEY_NULL` and `KEY_DUPLICATE` outrank a bad date, which in
# MAGIC turn outranks a value that does not fit its pinned numeric type.

# COMMAND ----------


def load_table(table: str, columns: list[dict], manifest: dict) -> dict:
    key = NATURAL_KEY[table]
    source_file = f"{LANDING}/{manifest['tables'][table]['file']}"
    names = [c["name"] for c in columns]

    # Everything is read as text and cast here, so the file never decides a type.
    raw_schema = ", ".join(f"`{n}` STRING" for n in names)
    raw = spark.read.schema(raw_schema).json(source_file)
    raw.createOrReplaceTempView("hist_raw")
    source_rows = spark.table("hist_raw").count()

    numeric = [c for c in columns if c["target_type"].startswith("DECIMAL")]
    temporal = [c for c in columns if c["target_type"] == "TIMESTAMP"]

    # A DATE column that will not cast is not a case the closed reason-code set
    # covers: the extract writes them in one canonical form, so a failure here is
    # a source or transport change that must be reported, not quarantined.
    if temporal:
        bad_temporal = " OR ".join(
            f"(`{c['name']}` IS NOT NULL AND try_cast(`{c['name']}` AS TIMESTAMP) IS NULL)" for c in temporal
        )
        offenders = spark.sql(f"SELECT count(*) AS n FROM hist_raw WHERE {bad_temporal}").collect()[0]["n"]
        if offenders:
            raise ValueError(
                f"{table}: {offenders} row(s) carry a DATE value that will not cast. No code in "
                ".migration/11_quarantine_codes.md covers this; stopping so one can be added centrally."
            )

    overflow = " OR ".join(
        f"(`{c['name']}` IS NOT NULL AND try_cast(`{c['name']}` AS {c['target_type']}) IS NULL)" for c in numeric
    ) or "false"

    raw_payload = "to_json(struct(" + ", ".join(f"`{n}`" for n in names) + "))"
    classified = spark.sql(f"""
        WITH keyed AS (
          SELECT *,
                 count(*) OVER (PARTITION BY `{key}`) AS key_occurrences,
                 size(collect_set({raw_payload}) OVER (PARTITION BY `{key}`)) AS distinct_payloads
            FROM hist_raw
        )
        SELECT *,
               {HIST_DT_TS_EXPR} AS hist_dt_ts,
               CASE
                 WHEN `{key}` IS NULL OR try_cast(`{key}` AS DECIMAL(38,0)) IS NULL THEN 'KEY_NULL'
                 WHEN key_occurrences > 1 AND distinct_payloads > 1 THEN 'KEY_DUPLICATE'
                 WHEN hist_dt IS NOT NULL AND ({HIST_DT_TS_EXPR}) IS NULL THEN 'BAD_DATE'
                 WHEN {overflow} THEN 'NUMERIC_OVERFLOW'
               END AS quarantine_reason,
               {raw_payload} AS raw_payload
          FROM keyed
    """)
    classified.createOrReplaceTempView("hist_classified")

    # Two rows on the same key with the *same* payload are not a KEY_DUPLICATE --
    # the code covers colliding payloads -- but they would make the MERGE
    # ambiguous, and the source declares this key unique. Stop rather than pick.
    identical_dupes = spark.sql(
        "SELECT count(*) AS n FROM hist_classified WHERE key_occurrences > 1 AND distinct_payloads = 1"
    ).collect()[0]["n"]
    if identical_dupes:
        raise ValueError(
            f"{table}: {identical_dupes} row(s) repeat the natural key with an identical payload, which the "
            "source's primary key forbids and no code in .migration/11_quarantine_codes.md covers. Stopping."
        )

    quarantined_rows = spark.sql(
        "SELECT count(*) AS n FROM hist_classified WHERE quarantine_reason IS NOT NULL"
    ).collect()[0]["n"]
    loaded_rows = source_rows - quarantined_rows

    unknown = [
        r["quarantine_reason"]
        for r in spark.sql(
            "SELECT DISTINCT quarantine_reason FROM hist_classified WHERE quarantine_reason IS NOT NULL"
        ).collect()
        if r["quarantine_reason"] not in QUARANTINE_CODES
    ]
    if unknown:
        raise ValueError(f"{table}: rejection reason(s) outside the closed code set: {unknown}")

    if source_rows and quarantined_rows / source_rows > QUARANTINE_HALT_RATE:
        raise ValueError(
            f"HALT {table}: quarantined {quarantined_rows}/{source_rows} rows "
            f"({quarantined_rows / source_rows:.2%}) exceeds the {QUARANTINE_HALT_RATE:.0%} ceiling. "
            "Reporting green over the surviving population is the failure this ceiling exists to prevent."
        )

    uid = f_md5_uuid(f"concat_ws('|', '{NS}', '{table}', `{key}`)")
    typed = ",\n               ".join(f"{typed_expr(c)} AS `{c['name']}`" for c in columns)

    # Customers absent from CUSTOMER_MASTER are flagged, never filtered: the
    # history row is the only surviving record of a closed account.
    if table == "customer_master_hist":
        spark.read.schema("cust_id STRING").json(f"{LANDING}/customer_master_keys.json") \
            .selectExpr("cust_id").distinct().createOrReplaceTempView("live_customer_keys")
        absent = "k.live_cust_id IS NULL"
        absent_join = ("LEFT JOIN (SELECT cust_id AS live_cust_id FROM live_customer_keys) k "
                       "ON k.live_cust_id = s.cust_id")
    else:
        absent = "CAST(NULL AS BOOLEAN)"
        absent_join = ""

    spark.sql(f"""
        CREATE OR REPLACE TEMP VIEW hist_load AS
        SELECT '{NS}' AS ns,
               {uid} AS hist_uid,
               {typed},
               hist_dt_ts,
               {absent} AS hist_customer_absent,
               sha2(raw_payload, 256) AS row_hash,
               '{table}' AS source_table,
               '{source_file}' AS source_file,
               current_timestamp() AS loaded_at
          FROM hist_classified s
          {absent_join}
         WHERE quarantine_reason IS NULL
    """)

    target_columns = ["ns", "hist_uid"] + names + [
        "hist_dt_ts", "hist_customer_absent", "row_hash", "source_table", "source_file", "loaded_at",
    ]
    # The matched branch is guarded on row_hash, so a rerun over identical input
    # writes nothing at all rather than rewriting every row with a fresh
    # loaded_at. That is what makes the no-op claim checkable in Delta history.
    updates = ",\n              ".join(f"t.`{c}` = s.`{c}`" for c in target_columns)
    inserts = ", ".join(f"`{c}`" for c in target_columns)
    spark.sql(f"""
        MERGE INTO {TARGETS[table]} t
        USING hist_load s
           ON t.ns = s.ns AND t.hist_uid = s.hist_uid
         WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET
              {updates}
         WHEN NOT MATCHED THEN INSERT ({inserts}) VALUES ({', '.join(f's.`{c}`' for c in target_columns)})
    """)
    merge_metrics = merge_operation_metrics(TARGETS[table])

    # The payload hash is part of the key, not a fallback for a missing one:
    # KEY_DUPLICATE rows share a non-null natural key by definition, so keying
    # on the key alone would collapse them into one quarantine row and leave a
    # rerun's MERGE matching several source rows to the same target row.
    quarantine_uid = f_md5_uuid(
        f"concat_ws('|', '{NS}', '{table}', coalesce(`{key}`, '<nokey>'), sha2(raw_payload, 256))"
    )
    spark.sql(f"""
        MERGE INTO {QUARANTINE} t
        USING (
          SELECT '{NS}' AS ns,
                 {quarantine_uid} AS quarantine_uid,
                 '{table}' AS source_table,
                 '{source_file}' AS source_file,
                 `{key}` AS natural_key,
                 quarantine_reason,
                 CASE quarantine_reason
                   WHEN 'BAD_DATE' THEN concat('HIST_DT=', coalesce(hist_dt, '<null>'))
                   ELSE NULL
                 END AS quarantine_detail,
                 sha2(raw_payload, 256) AS row_hash,
                 raw_payload,
                 current_timestamp() AS quarantined_at
            FROM hist_classified
           WHERE quarantine_reason IS NOT NULL
        ) s
           ON t.ns = s.ns AND t.quarantine_uid = s.quarantine_uid
         WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET *
         WHEN NOT MATCHED THEN INSERT *
    """)

    target_rows = spark.sql(
        f"SELECT count(*) AS n FROM {TARGETS[table]} WHERE ns = '{NS}'"
    ).collect()[0]["n"]
    reasons = {
        r["quarantine_reason"]: r["n"]
        for r in spark.sql(f"""
            SELECT quarantine_reason, count(*) AS n
              FROM {QUARANTINE} WHERE ns = '{NS}' AND source_table = '{table}'
             GROUP BY quarantine_reason
        """).collect()
    }
    return {
        "source_rows": source_rows,
        "loaded_rows": loaded_rows,
        "quarantined_rows": quarantined_rows,
        "target_rows_for_ns": target_rows,
        "quarantine_by_reason": reasons,
        "merge_metrics": merge_metrics,
        "quarantine_merge_metrics": merge_operation_metrics(QUARANTINE),
        "source_file": source_file,
        "source_sha256": manifest["tables"][table]["sha256"],
    }


# COMMAND ----------

manifest = read_manifest()
if manifest["ns"] != NS or manifest["unit"] != UNIT:
    raise ValueError(f"manifest is for {manifest['unit']}/{manifest['ns']}, this run is {UNIT}/{NS}")

ensure_quarantine()
summary = {"unit": UNIT, "ns": NS, "manifest_generated_at": manifest["generated_at"], "tables": {}}
for table in TARGETS:
    columns = source_columns(manifest, table)
    ensure_target(table, columns)
    summary["tables"][table] = load_table(table, columns, manifest)

# Empty in, empty out: an empty source still produces a run and a report rather
# than a skipped unit.
summary["accounting_holds"] = all(
    t["loaded_rows"] + t["quarantined_rows"] == t["source_rows"] for t in summary["tables"].values()
)
if not summary["accounting_holds"]:
    raise ValueError(f"loaded + quarantined != source: {json.dumps(summary['tables'])}")

print(json.dumps(summary, indent=2))
dbutils.notebook.exit(json.dumps(summary))
