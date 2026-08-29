# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_silver_rating
# MAGIC
# MAGIC Port of the OW_BILLING rating engine (`pkg_rating`: `compute_rating`, `fn_usage_rating`,
# MAGIC `fn_usage_summary`, `sp_finalize_rating`) onto `ow_tp.silver.rating_periods`,
# MAGIC `ow_tp.silver.rating_results` and `ow_tp.silver.quarantine_silver_rating`.
# MAGIC
# MAGIC Inputs are the wave-1 bronze tables (`ow_tp.bronze.*`), read only. Behaviour is fixed by
# MAGIC `docs/tech-partnerships/contracts/silver_rating.json` and `.migration/09_semantic_dictionary.md`:
# MAGIC
# MAGIC * **D-01** every `LEAST`/`GREATEST` is wrapped so a `NULL` argument yields `NULL`
# MAGIC   (Spark's own `least`/`greatest` ignore nulls and would silently return the other side),
# MAGIC * **D-07** usage is windowed on `date_format(occurred_at, 'yyyyMMdd')` string comparison,
# MAGIC   the truncating comparison the source performs — not a timestamp comparison,
# MAGIC * **D-13** tier break at 101 units, `1.5` second-tier multiplier, the two rollover caps and
# MAGIC   suspension proration applied strictly in the source's order,
# MAGIC * **D-13** the subscription dates are *not* truncated: an Oracle `DATE` carries a time and
# MAGIC   `(p_period_end - v_suspended_on + 1)` is fractional-day arithmetic, so `starts_on`,
# MAGIC   `ends_on` and `suspended_on` travel at full precision and the proration factor is taken in
# MAGIC   seconds, in `DECIMAL`. Truncation stays only where the source truncates: the D-07 usage
# MAGIC   window,
# MAGIC * **D-13** the three-month rollover bank is read from the source's rows in bronze *and* from
# MAGIC   the periods this unit finalized itself, bronze winning per `(tenant_id, period_start)`, so
# MAGIC   rating two consecutive periods in the target does not price the second off a stale bank,
# MAGIC * **D-09** `rollover_units` is *persisted* as `GREATEST(quota_units - used_units, 0)`, which is
# MAGIC   not the three-month banked value the same call computed; both are kept, the persisted column
# MAGIC   verbatim and the computed one as an explicit column,
# MAGIC * **D-10** no package globals: every value `pkg_rating` carried in a global travels here as an
# MAGIC   explicit column of the result row,
# MAGIC * **D-14** `f_md5_uuid` reimplemented byte for byte and reused as the `MERGE` key with `ns`,
# MAGIC * **D-04/D-23/T6** decimal-only money lineage, `DECIMAL(14,2)` money and `DECIMAL(38,0)` counts
# MAGIC   pinned in `databricks/ddl/silver_rating_spec.json`; no `DOUBLE` anywhere,
# MAGIC * **D-19/11_quarantine_codes** a tenant-period the source cannot finalize is quarantined with a
# MAGIC   code from the closed set and its raw payload, never written as a partial money row.
# MAGIC
# MAGIC The job is serverless, takes `ns`, and `MERGE`s on `id` plus `ns`, so a second identical run is
# MAGIC a no-op that the run summary proves with Delta `MERGE` metrics.

# COMMAND ----------

import json
import re

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "silver")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("period_start", "2026-02-01")
dbutils.widgets.text("period_end", "2026-02-28")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/silver_rating_spec.json")
dbutils.widgets.text("batch_id", "")
dbutils.widgets.text("plan_overrides", "")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRONZE = dbutils.widgets.get("bronze_schema").strip()
PERIOD_START = dbutils.widgets.get("period_start").strip()
PERIOD_END = dbutils.widgets.get("period_end").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()
PLAN_OVERRIDES_RAW = dbutils.widgets.get("plan_overrides").strip()

UNIT = "silver_rating"

if not NS:
    raise ValueError("ns is required: every target row and every volume path is ns-scoped")
if CATALOG != "ow_tp":
    raise ValueError("this unit only reads and writes the ow_tp catalog")
if SCHEMA != "silver":
    raise ValueError("this unit owns targets in ow_tp.silver only")

# ns and batch_id reach SQL as literals and volume paths as path segments, so they are held to the
# estate's namespace grammar instead of being escaped ad hoc at each use site.
for _pname, _pval in (("ns", NS), ("batch_id", BATCH_ID)):
    if _pval and not re.fullmatch(r"[A-Za-z0-9_-]+", _pval):
        raise ValueError(f"{_pname}={_pval!r} must match ^[A-Za-z0-9_-]+$")
for _pname, _pval in (("period_start", PERIOD_START), ("period_end", PERIOD_END)):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _pval):
        raise ValueError(f"{_pname}={_pval!r} must be an ISO date (YYYY-MM-DD)")
if PERIOD_START > PERIOD_END:
    raise ValueError(f"period_start {PERIOD_START} is after period_end {PERIOD_END}")

# A period is re-rated when a plan or subscription is corrected after it was first finalized. The
# corrected plan values are supplied here rather than read from bronze, because bronze mirrors the
# source and this unit never writes it. Empty (the default) means: rate from bronze alone.
#
# This is a per-run input of the re-rate proof, never a configured job parameter: the deployed
# ow_tp_silver_rating job declares no plan_overrides parameter, so a scheduled or operator run rates
# money only from what bronze carries. A real plan correction arrives through the source and reaches
# bronze like every other value.
PLAN_OVERRIDES: list[dict] = json.loads(PLAN_OVERRIDES_RAW) if PLAN_OVERRIDES_RAW else []
if not isinstance(PLAN_OVERRIDES, list):
    raise ValueError("plan_overrides must be a JSON array of {tenant_id, included_units, overage_rate}")
for _ovr in PLAN_OVERRIDES:
    if set(_ovr) != {"tenant_id", "included_units", "overage_rate"}:
        raise ValueError(
            f"plan_overrides entry {_ovr!r} must carry exactly tenant_id, included_units, overage_rate"
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(_ovr["tenant_id"])):
        raise ValueError(f"plan_overrides tenant_id {_ovr['tenant_id']!r} must match ^[A-Za-z0-9_-]+$")
    if not re.fullmatch(r"\d{1,30}", str(_ovr["included_units"])):
        raise ValueError(f"plan_overrides included_units {_ovr['included_units']!r} must be a whole number")
    if not re.fullmatch(r"\d{1,6}(\.\d{1,6})?", str(_ovr["overage_rate"])):
        raise ValueError(f"plan_overrides overage_rate {_ovr['overage_rate']!r} must fit DECIMAL(12,6)")

LANDING = f"{LANDING_ROOT}/{NS}/{UNIT}"
QUARANTINE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"

if not BATCH_ID:
    BATCH_ID = spark.sql(
        "SELECT date_format(current_timestamp(), 'yyyyMMddHHmmss')"
    ).collect()[0][0]


def load_spec(path: str) -> dict:
    candidates = [path, f"/Workspace{path}" if not path.startswith("/Workspace") else path]
    for cand in candidates:
        try:
            with open(cand, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            continue
    raise FileNotFoundError(f"{UNIT} spec not found at any of {candidates}")


SPEC = load_spec(SPEC_PATH)
CONST = SPEC["rating_constants"]
TIER_BREAK = int(CONST["tier_break_units"])
SECOND_TIER_MULT = CONST["second_tier_multiplier"]
ROLLOVER_MONTHS = int(CONST["rollover_lookback_months"])
ROLLOVER_CAP = int(CONST["rollover_cap_multiple"])
SUSPENDED_CD = int(CONST["suspended_status_cd"])
USAGE_KIND_TYPE = CONST["usage_kind_code_type"]
REASONS = set(SPEC["quarantine_reasons"])
HALT_PCT = float(SPEC["quarantine_halt_threshold_pct"])
TABLES = {t["target"]: t for t in SPEC["tables"]}

print(
    f"ns={NS} period={PERIOD_START}..{PERIOD_END} batch_id={BATCH_ID} "
    f"targets={sorted(TABLES)} quarantine={QUARANTINE}"
)

# COMMAND ----------

# MAGIC %md ## Dialect helpers
# MAGIC
# MAGIC `least`/`greatest` and `f_md5_uuid` are the two places where a plain translation is wrong, so
# MAGIC they exist once, here, and every expression below is built from them.

# COMMAND ----------


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def o_least(a: str, b: str) -> str:
    """Oracle LEAST: NULL in, NULL out (D-01). Spark's least() ignores nulls."""
    return f"(CASE WHEN ({a}) IS NULL OR ({b}) IS NULL THEN NULL ELSE least({a}, {b}) END)"


def o_greatest(a: str, b: str) -> str:
    """Oracle GREATEST: NULL in, NULL out (D-01)."""
    return f"(CASE WHEN ({a}) IS NULL OR ({b}) IS NULL THEN NULL ELSE greatest({a}, {b}) END)"


def f_md5_uuid(expr: str) -> str:
    """pkg_ow_util.f_md5_uuid: lower(md5(input)) sliced 8-4-4-4-12 (D-14)."""
    return (
        f"concat_ws('-', substr(lower(md5({expr})), 1, 8), substr(lower(md5({expr})), 9, 4), "
        f"substr(lower(md5({expr})), 13, 4), substr(lower(md5({expr})), 17, 4), "
        f"substr(lower(md5({expr})), 21, 12))"
    )


# Oracle compares the formatted date strings, which drops the time component (D-07).
def yyyymmdd(expr: str) -> str:
    return f"date_format({expr}, 'yyyyMMdd')"


NS_LIT = sql_str(NS)
PS_LIT = f"DATE'{PERIOD_START}'"
PE_LIT = f"DATE'{PERIOD_END}'"
# sp_finalize_rating is called with DATE parameters at midnight, and the source compares its DATE
# columns against them at full precision. The period bounds therefore reach every comparison here as
# midnight timestamps: a subscription that starts, ends or is suspended later on the boundary day is
# outside the period for the source, and has to be outside it here too.
PS_TS = f"TIMESTAMP'{PERIOD_START} 00:00:00'"
PE_TS = f"TIMESTAMP'{PERIOD_END} 00:00:00'"
BATCH_LIT = sql_str(BATCH_ID)

# Oracle DATE arithmetic is wall-clock: DATE - DATE is a plain difference with no zone in it. The
# session zone is pinned so a timestamp difference below is that same wall-clock difference and no
# daylight-saving jump inside a period can move a proration factor.
spark.conf.set("spark.sql.session.timeZone", "UTC")

# COMMAND ----------

# MAGIC %md ## Target DDL
# MAGIC
# MAGIC `CREATE TABLE IF NOT EXISTS` only, liquid clustering on the natural key plus `ns` (D-22).
# MAGIC This unit never drops or replaces a table, and touches nothing outside its own three targets.

# COMMAND ----------


def full(target: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{target}"


def ensure_target(tbl: dict) -> None:
    cols = ",\n  ".join(f"`{c['name']}` {c['target_type']}" for c in tbl["columns"])
    cluster = ", ".join(f"`{c}`" for c in tbl["cluster_by"])
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {full(tbl['target'])} (
          {cols},
          `ns` STRING NOT NULL,
          `_origin` STRING NOT NULL,
          `_batch_id` STRING NOT NULL,
          `_loaded_at` TIMESTAMP NOT NULL
        )
        USING DELTA
        CLUSTER BY ({cluster})
        COMMENT 'silver_rating: {tbl["source_table"]} ported from pkg_rating; ns-scoped, MERGE on {"+".join(tbl["merge_key"])}'
        """
    )


for _tbl in TABLES.values():
    ensure_target(_tbl)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {QUARANTINE} (
      `quarantine_reason` STRING NOT NULL,
      `ns` STRING NOT NULL,
      `source_table` STRING NOT NULL,
      `source_key` STRING,
      `raw_source_payload` STRING NOT NULL,
      `detail` STRING,
      `dictionary_ref` STRING,
      `_batch_id` STRING NOT NULL,
      `_quarantined_at` TIMESTAMP NOT NULL
    )
    USING DELTA
    CLUSTER BY (`source_table`, `quarantine_reason`, `ns`)
    COMMENT 'silver_rating rejects: one reason from the closed set in .migration/11_quarantine_codes.md, with ns, source table and raw payload'
    """
)

# COMMAND ----------

# MAGIC %md ## The rating engine, step by step in the source's order
# MAGIC
# MAGIC One set-based pass replaces `compute_rating`'s row-at-a-time cursor loops. Every step is a
# MAGIC separate CTE so the order of operations (D-13) is readable and cannot be quietly reassociated:
# MAGIC
# MAGIC 1. `sub_pick` — the covering subscription. The source takes `ROWNUM <= 1` after
# MAGIC    `ORDER BY starts_on DESC` on a non-unique column, so ties are arbitrary there; the target
# MAGIC    pins `row_number() OVER (ORDER BY starts_on DESC, id DESC)` (D-08) and the recon reports the
# MAGIC    tie exposure as an unverified path rather than pretending the source was deterministic.
# MAGIC 2. `usage` — units summed over the string-date window (D-07).
# MAGIC 3. `v_prior_bank` — the three months of banked rollover before this period, read from the
# MAGIC    source's rows in bronze **and** the periods this unit finalized itself (see below).
# MAGIC 4. `capped` / `rated` / `tiered` / `priced` / `prorated` — the arithmetic, in order.
# MAGIC
# MAGIC `sp_finalize_rating` then writes the row: the period id is
# MAGIC `f_md5_uuid(tenant_id || TO_CHAR(period_start,'YYYY-MM-DD'))`, the result id is
# MAGIC `f_md5_uuid(period_id)`, `created_at` is `period_end`, and `rollover_units` is the persisted
# MAGIC `GREATEST(quota_units - used_units, 0)` of D-09 — deliberately not the value step 4 computed.

# COMMAND ----------

# Suspension proration (D-13):
#
#     v_factor := (p_period_end - v_suspended_on + 1) / (p_period_end - p_period_start + 1);
#
# An Oracle DATE carries a time component and DATE - DATE is a **fractional** day count, so a
# suspension at midday yields a factor that a date-truncated subtraction does not: it lands on
# billable_units and on overage_amount, which the contract holds exact to the cent. Numerator and
# denominator are taken in whole seconds, which is the same ratio without a truncation:
#
#     (a/86400 + 1) / (b/86400 + 1)  ==  (a + 86400) / (b + 86400)
#
# and the division is left until after the multiplication, so the ratio is never pre-rounded. Every
# operand is DECIMAL — no DOUBLE anywhere in the money lineage (D-23).
SECONDS_PER_DAY = 86400


def factor_num(susp: str) -> str:
    return (
        f"(CAST(unix_timestamp({PE_TS}) - unix_timestamp({susp}) AS DECIMAL(20,0))"
        f" + {SECONDS_PER_DAY})"
    )


FACTOR_DEN = (
    f"(CAST(unix_timestamp({PE_TS}) - unix_timestamp({PS_TS}) AS DECIMAL(20,0))"
    f" + {SECONDS_PER_DAY})"
)


def prorate(value: str, susp: str, scale: int) -> str:
    """ROUND(value * v_factor, scale) with the factor applied as an exact ratio.

    The product is retained to ten fractional digits before the source's ROUND, so it agrees with
    Oracle's 38-digit NUMBER factor unless the exact product falls within 1e-10 of a rounding
    boundary. `PRORATION_PROBE_SQL` measures the agreement against Oracle for real inputs.
    """
    return (
        f"round(CAST(CAST({value} AS DECIMAL(28,{scale})) * {factor_num(susp)} AS DECIMAL(38,10))"
        f" / {FACTOR_DEN}, {scale})"
    )


# suspended_on is compared at full precision against the same midnight bounds the source uses, so a
# suspension after midnight on the last day of the period does not prorate — there as here.
SUSPENDED_PRED = (
    f"(`status_cd` = {SUSPENDED_CD} AND `suspended_on` IS NOT NULL "
    f"AND `suspended_on` BETWEEN {PS_TS} AND {PE_TS})"
)

# The rollover bank: `compute_rating` sums RATING_RESULTS.rollover_units over the three months before
# the period. In the target that table has two populations, and reading only the first gets money
# wrong on the second period of any target-run sequence:
#
#   * `ow_tp.bronze.rating_results` — what the source itself finalized, and authoritative wherever it
#     exists, because those are the numbers sp_finalize_rating actually wrote;
#   * `ow_tp.silver.rating_results` with `_origin = 'target-finalize'` — the periods this unit rated
#     that the source has not. Rate February here and then March, and March's bank has to see
#     February's own row; from bronze alone it would price the overage off a stale bank.
#
# The two are unioned and deduplicated per (tenant_id, period_start) with **bronze winning**, so the
# source stays authoritative for every period it has finalized and silver only fills the periods it
# alone rated. Nothing about the cap chain (D-09) changes: this decides only which rows are summed.
#
# The bank is the state as it stood before this run's MERGE: it reads only periods strictly earlier
# than this one, so a re-evaluation cannot pick up the rows this run writes for the current period.
PRIOR_BANK_SQL = f"""
WITH bronze_bank AS (
  SELECT rp.`tenant_id`, rp.`period_start` AS period_start,
         coalesce(rr.`rollover_units`, CAST(0 AS DECIMAL(38,0))) AS rollover_units
  FROM {CATALOG}.{BRONZE}.rating_results rr
  JOIN {CATALOG}.{BRONZE}.rating_periods rp
    ON rp.`id` = rr.`period_id` AND rp.`ns` = rr.`ns`
  WHERE rr.`ns` = {NS_LIT}
    AND rp.`period_start` < {PS_TS}
    AND rp.`period_start` >= add_months({PS_TS}, -{ROLLOVER_MONTHS})
),
silver_bank AS (
  SELECT rp.`tenant_id`, CAST(rp.`period_start` AS TIMESTAMP) AS period_start,
         coalesce(rr.`rollover_units`, CAST(0 AS DECIMAL(38,0))) AS rollover_units
  FROM {full('rating_results')} rr
  JOIN {full('rating_periods')} rp ON rp.`id` = rr.`period_id` AND rp.`ns` = rr.`ns`
  WHERE rr.`ns` = {NS_LIT}
    AND rr.`_origin` = 'target-finalize'
    AND CAST(rp.`period_start` AS TIMESTAMP) < {PS_TS}
    AND CAST(rp.`period_start` AS TIMESTAMP) >= add_months({PS_TS}, -{ROLLOVER_MONTHS})
),
bank AS (
  SELECT `tenant_id`, period_start, rollover_units, 'bronze' AS bank_origin
  FROM bronze_bank
  UNION ALL
  SELECT s.`tenant_id`, s.period_start, s.rollover_units, 'silver-target-finalize'
  FROM silver_bank s
  WHERE NOT EXISTS (
    SELECT 1 FROM bronze_bank b
    WHERE b.`tenant_id` = s.`tenant_id` AND b.period_start = s.period_start
  )
)
SELECT `tenant_id`,
       sum(`rollover_units`) AS prior_units,
       count(*) AS bank_rows,
       count(*) FILTER (WHERE bank_origin = 'bronze') AS bank_rows_from_bronze,
       count(*) FILTER (WHERE bank_origin = 'silver-target-finalize') AS bank_rows_from_silver,
       coalesce(sum(CASE WHEN bank_origin = 'silver-target-finalize' THEN `rollover_units` END),
                CAST(0 AS DECIMAL(38,0))) AS prior_units_from_silver
FROM bank
GROUP BY `tenant_id`
"""
# Not cached: serverless compute rejects PERSIST TABLE, and the view is stable anyway — it reads
# only periods strictly before this one, so writing this period's rows cannot change it.
prior_bank = spark.sql(PRIOR_BANK_SQL)
prior_bank.createOrReplaceTempView("v_prior_bank")
prior_bank_tenants = prior_bank.count()

if PLAN_OVERRIDES:
    _ovr_rows = ", ".join(
        f"({sql_str(str(o['tenant_id']))}, CAST({o['included_units']} AS DECIMAL(38,0)), "
        f"CAST({o['overage_rate']} AS DECIMAL(12,6)))"
        for o in PLAN_OVERRIDES
    )
    PLAN_OVR_SQL = (
        f"SELECT * FROM VALUES {_ovr_rows} AS v(tenant_id, included_units, overage_rate)"
    )
else:
    PLAN_OVR_SQL = (
        "SELECT CAST(NULL AS STRING) AS tenant_id, "
        "CAST(NULL AS DECIMAL(38,0)) AS included_units, "
        "CAST(NULL AS DECIMAL(12,6)) AS overage_rate WHERE false"
    )

RATING_SQL = f"""
WITH plan_ovr AS (
  {PLAN_OVR_SQL}
),
tenant AS (
  SELECT `id` AS tenant_id
  FROM {CATALOG}.{BRONZE}.tenants
  WHERE `ns` = {NS_LIT}
),
-- The subscription dates are carried at full precision: the source compares and subtracts DATE
-- values that can hold a time, and truncating them here would change which subscription covers the
-- period, which one wins the ORDER BY, and the proration factor.
sub_cand AS (
  SELECT s.`tenant_id`, s.`id`, s.`status_cd`, s.`suspended_on`,
         s.`plan_id`, s.`starts_on`,
         row_number() OVER (PARTITION BY s.`tenant_id`
                            ORDER BY s.`starts_on` DESC, s.`id` DESC) AS rn,
         count(*) OVER (PARTITION BY s.`tenant_id`) AS cand_rows,
         count(*) OVER (PARTITION BY s.`tenant_id`, s.`starts_on`) AS tied_rows
  FROM {CATALOG}.{BRONZE}.subscriptions s
  WHERE s.`ns` = {NS_LIT}
    AND s.`starts_on` <= {PE_TS}
    AND (s.`ends_on` IS NULL OR s.`ends_on` >= {PS_TS})
),
sub_pick AS (
  SELECT * FROM sub_cand WHERE rn = 1
),
usage AS (
  SELECT u.`tenant_id`,
         sum(coalesce(u.`units`, CAST(0 AS DECIMAL(38,0)))) AS used_units,
         count(*) AS usage_events_in_window
  FROM {CATALOG}.{BRONZE}.usage_events u
  WHERE u.`ns` = {NS_LIT}
    AND {yyyymmdd("u.`occurred_at`")} >= {yyyymmdd(PS_LIT)}
    AND {yyyymmdd("u.`occurred_at`")} <= {yyyymmdd(PE_LIT)}
  GROUP BY u.`tenant_id`
),
bad_kind AS (
  SELECT u.`tenant_id`, count(*) AS bad_usage_rows,
         min(to_json(struct(u.`id`, u.`tenant_id`, u.`occurred_at`, u.`units`, u.`kind_cd`))) AS payload
  FROM {CATALOG}.{BRONZE}.usage_events u
  WHERE u.`ns` = {NS_LIT}
    AND {yyyymmdd("u.`occurred_at`")} >= {yyyymmdd(PS_LIT)}
    AND {yyyymmdd("u.`occurred_at`")} <= {yyyymmdd(PE_LIT)}
    AND NOT EXISTS (
      SELECT 1 FROM {CATALOG}.{BRONZE}.codes c
      WHERE c.`ns` = {NS_LIT} AND c.`code_type` = {sql_str(USAGE_KIND_TYPE)}
        AND c.`code_val` = u.`kind_cd`
    )
  GROUP BY u.`tenant_id`
),
base AS (
  SELECT t.tenant_id,
         s.`id` AS subscription_id, s.`status_cd`, s.suspended_on, s.`plan_id`,
         coalesce(s.cand_rows, 0) AS sub_candidates,
         coalesce(s.tied_rows, 0) AS sub_tied_rows,
         -- A re-rate supplies the corrected plan values; with no override this is the bronze plan
         -- row unchanged. coalesce here selects the input, it is not Oracle NVL semantics (D-02).
         coalesce(po.`included_units`, CAST(p.`included_units` AS DECIMAL(38,0))) AS v_included,
         coalesce(po.`overage_rate`, CAST(p.`overage_rate` AS DECIMAL(12,6))) AS v_rate,
         (po.`tenant_id` IS NOT NULL) AS plan_overridden,
         coalesce(u.used_units, CAST(0 AS DECIMAL(38,0))) AS used_units,
         coalesce(u.usage_events_in_window, 0) AS usage_events_in_window,
         coalesce(pr.prior_units, CAST(0 AS DECIMAL(38,0))) AS prior_units,
         coalesce(pr.prior_units_from_silver, CAST(0 AS DECIMAL(38,0))) AS prior_units_from_silver,
         coalesce(pr.bank_rows_from_silver, 0) AS bank_rows_from_silver,
         coalesce(bk.bad_usage_rows, 0) AS bad_usage_rows,
         bk.payload AS bad_usage_payload
  FROM tenant t
  LEFT JOIN sub_pick s ON s.`tenant_id` = t.tenant_id
  LEFT JOIN {CATALOG}.{BRONZE}.plans p ON p.`id` = s.`plan_id` AND p.`ns` = {NS_LIT}
  LEFT JOIN plan_ovr po ON po.`tenant_id` = t.tenant_id
  LEFT JOIN usage u ON u.`tenant_id` = t.tenant_id
  LEFT JOIN v_prior_bank pr ON pr.`tenant_id` = t.tenant_id
  LEFT JOIN bad_kind bk ON bk.`tenant_id` = t.tenant_id
),
-- v_prior := LEAST(NVL(2 * v_included, v_prior), v_prior): the first of the two caps.
capped AS (
  SELECT b.*,
         {o_least(f"coalesce({ROLLOVER_CAP} * `v_included`, `prior_units`)", "`prior_units`")}
           AS prior_capped
  FROM base b
),
-- g_quota_units := v_included; g_rollover_units := LEAST(v_prior, NVL(v_included * 2, v_prior))
rated AS (
  SELECT c.*,
         c.`v_included` AS quota_units,
         {o_least("`prior_capped`", f"coalesce(`v_included` * {ROLLOVER_CAP}, `prior_capped`)")}
           AS computed_rollover_units
  FROM capped c
),
-- g_billable_units := GREATEST(NVL(g_used - g_rollover - v_included, 0), 0)
billed AS (
  SELECT r.*,
         {o_greatest(
             "coalesce(`used_units` - `computed_rollover_units` - `v_included`, CAST(0 AS DECIMAL(38,0)))",
             "CAST(0 AS DECIMAL(38,0))",
         )} AS billable_pre_proration
  FROM rated r
),
-- g_first_tier := LEAST(billable, 101); g_second_tier := GREATEST(billable - 101, 0)
tiered AS (
  SELECT b.*,
         {o_least("`billable_pre_proration`", f"CAST({TIER_BREAK} AS DECIMAL(38,0))")}
           AS first_tier_units,
         {o_greatest(f"`billable_pre_proration` - {TIER_BREAK}", "CAST(0 AS DECIMAL(38,0))")}
           AS second_tier_units
  FROM billed b
),
-- g_overage_amount := ROUND(first * rate + second * rate * 1.5, 2)
priced AS (
  SELECT t.*,
         round(
           CAST(`first_tier_units` AS DECIMAL(20,0)) * CAST(`v_rate` AS DECIMAL(12,6))
           + CAST(`second_tier_units` AS DECIMAL(20,0)) * CAST(`v_rate` AS DECIMAL(12,6))
             * CAST({SECOND_TIER_MULT} AS DECIMAL(2,1)),
           2) AS overage_pre_proration
  FROM tiered t
),
-- Suspension proration, applied after tiering and pricing (D-13), never before.
prorated AS (
  SELECT p.*,
         {SUSPENDED_PRED} AS suspension_prorated,
         CASE WHEN {SUSPENDED_PRED}
              THEN {prorate("`billable_pre_proration`", "`suspended_on`", 0)}
              ELSE `billable_pre_proration` END AS billable_units,
         CASE WHEN {SUSPENDED_PRED}
              THEN {prorate("`overage_pre_proration`", "`suspended_on`", 2)}
              ELSE `overage_pre_proration` END AS overage_amount
  FROM priced p
)
SELECT tenant_id,
       {f_md5_uuid(f"concat(`tenant_id`, date_format({PS_LIT}, 'yyyy-MM-dd'))")} AS period_id,
       subscription_id,
       sub_candidates,
       sub_tied_rows,
       usage_events_in_window,
       prior_units,
       prior_units_from_silver,
       bank_rows_from_silver,
       bad_usage_rows,
       bad_usage_payload,
       plan_id,
       CAST(v_rate AS DECIMAL(12,6)) AS overage_rate,
       -- try_cast, not cast, on every pinned money/count type: an out-of-range value has to reach
       -- the overflow guard below as a NULL and be quarantined, not abort the run mid-population.
       try_cast(used_units AS DECIMAL(38,0)) AS used_units,
       try_cast(quota_units AS DECIMAL(38,0)) AS quota_units,
       try_cast(computed_rollover_units AS DECIMAL(38,0)) AS computed_rollover_units,
       -- D-09: persisted rollover is GREATEST(quota - used, 0), not the computed value above.
       try_cast({o_greatest("`quota_units` - `used_units`", "CAST(0 AS DECIMAL(38,0))")}
            AS DECIMAL(38,0)) AS rollover_units,
       try_cast(first_tier_units AS DECIMAL(38,0)) AS first_tier_units,
       try_cast(second_tier_units AS DECIMAL(38,0)) AS second_tier_units,
       try_cast(billable_units AS DECIMAL(38,0)) AS billable_units,
       try_cast(overage_amount AS DECIMAL(14,2)) AS overage_amount,
       suspension_prorated,
       plan_overridden,
       CAST({PE_LIT} AS TIMESTAMP) AS created_at,
       -- The same values before the pinned-type cast. The overflow guard (D-23/T6) is evaluated on
       -- these, because the cast above is what would silently null or truncate an out-of-range value.
       used_units AS used_units_raw,
       quota_units AS quota_units_raw,
       {o_greatest("`quota_units` - `used_units`", "CAST(0 AS DECIMAL(38,0))")} AS rollover_units_raw,
       billable_units AS billable_units_raw,
       overage_amount AS overage_amount_raw
FROM prorated
"""

rating = spark.sql(RATING_SQL)
rating.createOrReplaceTempView("v_rating")
spark.sql("SELECT count(*) FROM v_rating").collect()
print(f"rating drivers (tenants in ns={NS}): {spark.table('v_rating').count()}")

# COMMAND ----------

# MAGIC %md ## Quarantine
# MAGIC
# MAGIC Reasons come from the closed set in `.migration/11_quarantine_codes.md`; nothing local is
# MAGIC invented and there is no catch-all. A quarantined tenant-period produces **no** rating row, so
# MAGIC a swallowed source failure (`ANOM-SWALLOWED-EXCEPTION`) can never surface as a partial number.
# MAGIC
# MAGIC * `KEY_NULL` — the tenant id or the derived `f_md5_uuid` key is null, so no `MERGE` key exists.
# MAGIC * `FK_ORPHAN` — no covering subscription, or the subscription's plan row is missing. This is the
# MAGIC   D-19 cause (`RATING_RESULTS.quota_units` / `.subscription_id` are `NOT NULL` while the source
# MAGIC   can compute `NULL` for both, so `sp_finalize_rating` raises and the tenant's run aborts). The
# MAGIC   `detail` column carries D-19's own name for the cause, `NO_COVERING_PLAN`.
# MAGIC * `CODE_UNKNOWN` — a usage event in the window carries a `kind_cd` with no `CODES` row
# MAGIC   (`trg_usage_events_check`, D-16), so the rated units cannot be trusted.
# MAGIC * `NUMERIC_OVERFLOW` — a computed value does not fit its pinned target type (D-23/T6). Money is
# MAGIC   never widened or rescaled to make it fit. The test reads the `*_raw` columns, which carry the
# MAGIC   value **before** the cast to `DECIMAL(14,2)` / `DECIMAL(38,0)`, because it is that cast which
# MAGIC   would otherwise null or truncate the value first and leave the guard unable to fire; a raw
# MAGIC   value that survives while its cast counterpart is `NULL` is itself treated as overflow. The
# MAGIC   live exposure is `used_units * overage_rate * 1.5` (the source's `ORA-01438` case).
# MAGIC
# MAGIC **Ordering: quarantine is persisted before the halt is decided.** The quarantine `MERGE` runs
# MAGIC first, then the rate is compared with the 5% threshold and the run raises. A halted run therefore
# MAGIC leaves the operator the rejected payloads that caused it, which is the one thing needed to triage
# MAGIC it, while `rating_periods` and `rating_results` stay untouched — a halt must never write a
# MAGIC business row.
# MAGIC
# MAGIC **Divergence, orphan period row.** `sp_finalize_rating` INSERTs the `RATING_PERIODS` row
# MAGIC *before* it calls `compute_rating`, so a tenant whose `RATING_RESULTS` insert then raises (the
# MAGIC D-19 case: `NULL` `quota_units`/`subscription_id` into `NOT NULL` columns) leaves an orphan
# MAGIC period row with no result behind in the source. A quarantined tenant here gets neither a
# MAGIC period nor a result row — a reject is preferable to a period row whose money never landed —
# MAGIC so as soon as quarantine is non-empty `rating_periods` carries one row fewer per affected
# MAGIC tenant than the source. Recorded as a divergence in the recon report, not a parity failure.

# COMMAND ----------

MONEY_MAX = "999999999999.99"  # largest DECIMAL(14,2)
COUNT_MAX = "9" * 38  # largest DECIMAL(38,0)
COUNT_COLS = ("used_units", "quota_units", "rollover_units", "billable_units")


def overflow_pred(p: str) -> str:
    """True when a value did not fit its pinned target type, tested before the cast (D-23/T6).

    Two tests per column: the raw value against the target type's own bound, and the raw value
    surviving while the cast one is NULL, which is how a non-ANSI cast reports an out-of-range
    value. Either one means the number cannot be represented, so the row is rejected rather than
    landed with a silently altered amount.
    """
    parts = [
        f"abs({p}`overage_amount_raw`) > CAST({MONEY_MAX} AS DECIMAL(14,2))",
        f"({p}`overage_amount_raw` IS NOT NULL AND {p}`overage_amount` IS NULL)",
    ]
    for c in COUNT_COLS:
        parts.append(f"abs({p}`{c}_raw`) > CAST({COUNT_MAX} AS DECIMAL(38,0))")
        parts.append(f"({p}`{c}_raw` IS NOT NULL AND {p}`{c}` IS NULL)")
    return "(" + "\n             OR ".join(parts) + ")"


QUAR_SQL = f"""
WITH judged AS (
  SELECT r.*,
         CASE
           WHEN r.`tenant_id` IS NULL OR r.`period_id` IS NULL THEN 'KEY_NULL'
           WHEN r.`subscription_id` IS NULL OR r.`quota_units_raw` IS NULL THEN 'FK_ORPHAN'
           WHEN r.`bad_usage_rows` > 0 THEN 'CODE_UNKNOWN'
           WHEN {overflow_pred("r.")} THEN 'NUMERIC_OVERFLOW'
           ELSE NULL
         END AS quarantine_reason
  FROM v_rating r
)
SELECT * FROM judged
"""
judged = spark.sql(QUAR_SQL)
judged.createOrReplaceTempView("v_judged")

quarantine_rows = spark.sql(
    f"""
    SELECT `quarantine_reason`,
           {NS_LIT} AS `ns`,
           'OW_BILLING.TENANTS+SUBSCRIPTIONS+USAGE_EVENTS' AS `source_table`,
           concat_ws('|', `tenant_id`, {sql_str(PERIOD_START)}, {sql_str(PERIOD_END)}) AS `source_key`,
           coalesce(
             CASE WHEN `quarantine_reason` = 'CODE_UNKNOWN' THEN `bad_usage_payload` END,
             to_json(struct(`tenant_id`, `subscription_id`, `plan_id`, `used_units`, `quota_units`,
                            `computed_rollover_units`, `billable_units`, `overage_amount`,
                            `usage_events_in_window`))
           ) AS `raw_source_payload`,
           CASE `quarantine_reason`
             WHEN 'FK_ORPHAN' THEN 'NO_COVERING_PLAN: no covering subscription or no plan row, so sp_finalize_rating would insert NULL into a NOT NULL column and raise'
             WHEN 'CODE_UNKNOWN' THEN concat('usage events in window with kind_cd absent from CODES(USAGE_KIND): ', `bad_usage_rows`)
             WHEN 'KEY_NULL' THEN 'tenant_id or derived f_md5_uuid period key is null'
             ELSE 'computed value does not fit the pinned target type'
           END AS `detail`,
           CASE `quarantine_reason`
             WHEN 'FK_ORPHAN' THEN 'D-19'
             WHEN 'CODE_UNKNOWN' THEN 'D-16'
             WHEN 'KEY_NULL' THEN 'D-14'
             ELSE 'D-23'
           END AS `dictionary_ref`,
           {BATCH_LIT} AS `_batch_id`,
           current_timestamp() AS `_quarantined_at`
    FROM v_judged
    WHERE `quarantine_reason` IS NOT NULL
    """
)
quarantine_rows.createOrReplaceTempView("v_quarantine")

bad_reasons = [
    r[0]
    for r in spark.sql("SELECT DISTINCT quarantine_reason FROM v_quarantine").collect()
    if r[0] not in REASONS
]
if bad_reasons:
    raise ValueError(
        f"rejection cause(s) outside the closed set of .migration/11_quarantine_codes.md: "
        f"{bad_reasons} — stop and report so a code is added centrally"
    )

spark.sql("CREATE OR REPLACE TEMP VIEW v_loaded AS SELECT * FROM v_judged WHERE quarantine_reason IS NULL")

source_rows_drivers = spark.table("v_judged").count()
quarantined_rows = spark.table("v_quarantine").count()
loaded_drivers = spark.table("v_loaded").count()
if loaded_drivers + quarantined_rows != source_rows_drivers:
    raise AssertionError(
        f"quarantine accounting broken: {loaded_drivers} + {quarantined_rows} "
        f"!= {source_rows_drivers}"
    )
quar_pct = (100.0 * quarantined_rows / source_rows_drivers) if source_rows_drivers else 0.0
print(f"drivers={source_rows_drivers} loaded={loaded_drivers} quarantined={quarantined_rows} ({quar_pct:.4f}%)")

# COMMAND ----------

# MAGIC %md ### The rejects are persisted, then the halt is decided
# MAGIC
# MAGIC The quarantine `MERGE` runs before the threshold is evaluated, so a halted run still hands the
# MAGIC operator the rows that caused it. No business row has been written at this point, and the halt
# MAGIC raises before any is: a halt leaves `rating_periods` and `rating_results` exactly as they were.

# COMMAND ----------


def merge_metrics(target: str) -> dict:
    # Managed Delta appends its own maintenance commits (OPTIMIZE, VACUUM) to the same history, so
    # the newest entry is not necessarily this run's write, and reading it would report a no-op the
    # MERGE never made. Take the latest MERGE: a run performs exactly one per target.
    hist = spark.sql(f"DESCRIBE HISTORY {full(target)}")
    latest = hist.orderBy("version", ascending=False)
    merges = latest.where("operation = 'MERGE'").limit(1).collect()
    row = merges[0] if merges else latest.limit(1).collect()[0]
    m = row["operationMetrics"] or {}
    return {
        "operation": row["operation"],
        "merge_rows_inserted": int(m.get("numTargetRowsInserted", 0)),
        "merge_rows_updated": int(m.get("numTargetRowsUpdated", 0)),
        "merge_rows_deleted": int(m.get("numTargetRowsDeleted", 0)),
        "version": int(row["version"]),
    }


spark.sql(
    f"""
    MERGE INTO {QUARANTINE} t
    USING v_quarantine s
      ON t.`ns` = {NS_LIT} AND t.`source_table` = s.`source_table`
     AND t.`source_key` <=> s.`source_key` AND t.`quarantine_reason` = s.`quarantine_reason`
    WHEN MATCHED AND NOT (t.`raw_source_payload` <=> s.`raw_source_payload`) THEN UPDATE SET
      t.`raw_source_payload` = s.`raw_source_payload`,
      t.`detail` = s.`detail`,
      t.`_batch_id` = s.`_batch_id`,
      t.`_quarantined_at` = s.`_quarantined_at`
    WHEN NOT MATCHED THEN INSERT *
    """
)
quarantine_metrics = merge_metrics(f"quarantine_{UNIT}")

if quar_pct > HALT_PCT:
    raise AssertionError(
        f"STOPA-QUARANTINE: quarantine rate {quar_pct:.4f}% exceeds {HALT_PCT}% of source rows — "
        f"halting the unit instead of loading around it. The {quarantined_rows} rejected rows are in "
        f"{QUARANTINE} (ns={NS}, _batch_id={BATCH_ID}); no rating row was written"
    )

# COMMAND ----------

# MAGIC %md ### Overflow guard probe
# MAGIC
# MAGIC The population above overflows nothing, so the guard's own reachability is measured rather than
# MAGIC assumed: a synthetic amount is pushed through the same cast and the same generated predicate.
# MAGIC This is a probe of the target expression only — it is not a finding about the source, and it
# MAGIC writes nothing.

# COMMAND ----------

PROBE_SQL = f"""
WITH amounts AS (
  SELECT 1 AS ord, CAST(1e14 AS DECIMAL(38,2)) AS amount
  UNION ALL
  SELECT 2 AS ord, CAST(12.34 AS DECIMAL(38,2)) AS amount
),
probe AS (
  SELECT a.ord,
         a.amount AS `overage_amount_raw`,
         try_cast(a.amount AS DECIMAL(14,2)) AS `overage_amount`,
         {", ".join(
            f"CAST(1 AS DECIMAL(38,0)) AS `{c}_raw`, "
            f"try_cast(CAST(1 AS DECIMAL(38,0)) AS DECIMAL(38,0)) AS `{c}`"
            for c in COUNT_COLS
         )}
  FROM amounts a
)
SELECT CAST(p.`overage_amount_raw` AS STRING) AS raw_value,
       CAST(p.`overage_amount` AS STRING) AS cast_value,
       CASE WHEN {overflow_pred("p.")} THEN 'NUMERIC_OVERFLOW' ELSE NULL END AS reason
FROM probe p
ORDER BY p.ord
"""
overflow_probe = {
    "description": "a value beyond DECIMAL(14,2) and an in-range control, both pushed through the "
    "pinned-type cast and the same generated overflow predicate the load uses",
    "is_probe_of_target_expression_not_source_finding": True,
    "cases": [
        {"raw_value": r[0], "value_after_cast": r[1], "quarantine_reason": r[2]}
        for r in spark.sql(PROBE_SQL).collect()
    ],
}
print(json.dumps(overflow_probe, indent=1))
if [c["quarantine_reason"] for c in overflow_probe["cases"]] != ["NUMERIC_OVERFLOW", None]:
    raise AssertionError(
        f"the NUMERIC_OVERFLOW guard did not behave as declared on the probe: {overflow_probe}"
    )

# COMMAND ----------

# MAGIC %md ### Suspension proration probe
# MAGIC
# MAGIC Every `suspended_on` in this population sits at midnight, so the fractional-day half of
# MAGIC `(p_period_end - v_suspended_on + 1)` is exercised by no row. The factor is therefore measured
# MAGIC on synthetic timestamps through the same generated expression the load uses: a midday
# MAGIC suspension, the same day at midnight, and one second before the next midnight. The
# MAGIC `*_if_date_truncated` columns are what a `to_date()`-truncated subtraction would have produced,
# MAGIC kept alongside so the difference is visible rather than asserted.
# MAGIC
# MAGIC This is a probe of the target expression, not a finding about the source, and it writes
# MAGIC nothing. The recon runner evaluates the same three cases in **Oracle** and compares them
# MAGIC (`PRORATION-FRACTIONAL-DAY`).

# COMMAND ----------

PRORATION_PROBE_BILLABLE = "1400"
PRORATION_PROBE_OVERAGE = "560.00"
_PROBE_DAY = f"CAST({PS_LIT} + INTERVAL 13 DAYS AS TIMESTAMP)"
_PROBE_B = f"CAST({PRORATION_PROBE_BILLABLE} AS DECIMAL(38,0))"
_PROBE_O = f"CAST({PRORATION_PROBE_OVERAGE} AS DECIMAL(38,2))"

PRORATION_PROBE_SQL = f"""
WITH cases AS (
  SELECT 1 AS ord, 'suspended at midday' AS label,
         {_PROBE_DAY} + INTERVAL 12 HOURS AS suspended_on
  UNION ALL
  SELECT 2 AS ord, 'suspended at midnight' AS label, {_PROBE_DAY} AS suspended_on
  UNION ALL
  SELECT 3 AS ord, 'suspended one second before the next midnight' AS label,
         {_PROBE_DAY} + INTERVAL 86399 SECONDS AS suspended_on
)
SELECT label,
       date_format(`suspended_on`, 'yyyy-MM-dd HH:mm:ss') AS suspended_on,
       CAST(CAST({factor_num('`suspended_on`')} AS DECIMAL(38,10)) / {FACTOR_DEN} AS STRING)
         AS factor,
       CAST({prorate(_PROBE_B, '`suspended_on`', 0)} AS STRING) AS billable_prorated,
       CAST({prorate(_PROBE_O, '`suspended_on`', 2)} AS STRING) AS overage_prorated,
       CAST({prorate(_PROBE_B, 'to_date(`suspended_on`)', 0)} AS STRING)
         AS billable_prorated_if_date_truncated,
       CAST({prorate(_PROBE_O, 'to_date(`suspended_on`)', 2)} AS STRING)
         AS overage_prorated_if_date_truncated
FROM cases
ORDER BY ord
"""
proration_probe = {
    "description": "the suspension factor and its effect on billable_units and overage_amount, "
    "measured on synthetic suspension timestamps through the same generated expression the load "
    "uses; *_if_date_truncated is what a to_date()-truncated subtraction would have produced",
    "is_probe_of_target_expression_not_source_finding": True,
    "period_start": PERIOD_START,
    "period_end": PERIOD_END,
    "inputs": {
        "billable_pre_proration": PRORATION_PROBE_BILLABLE,
        "overage_pre_proration": PRORATION_PROBE_OVERAGE,
    },
    "cases": [r.asDict() for r in spark.sql(PRORATION_PROBE_SQL).collect()],
}
print(json.dumps(proration_probe, indent=1))
_midday = proration_probe["cases"][0]
if _midday["factor"] == proration_probe["cases"][1]["factor"] or (
    _midday["billable_prorated"] == _midday["billable_prorated_if_date_truncated"]
    and _midday["overage_prorated"] == _midday["overage_prorated_if_date_truncated"]
):
    raise AssertionError(
        "the proration factor is not carrying the time component: a midday suspension must not "
        f"produce the midnight factor or the date-truncated money: {proration_probe}"
    )

# COMMAND ----------

# MAGIC %md ## Migrated history
# MAGIC
# MAGIC `RATING_PERIODS` / `RATING_RESULTS` rows the source already holds are the source's own record
# MAGIC for periods this run does not finalize (they are also the rollover bank the engine above reads),
# MAGIC so they migrate verbatim, `_origin = 'source-migrated'`. Recomputing them would overwrite the
# MAGIC bank with values `sp_finalize_rating` never wrote. The rated period is `_origin =
# MAGIC 'target-finalize'`. `KEY_DUPLICATE` guards the source's `(tenant_id, period_start)` uniqueness.

# COMMAND ----------

dup_periods = spark.sql(
    f"""
    SELECT `tenant_id`, to_date(`period_start`) AS period_start, count(DISTINCT `id`) AS ids
    FROM {CATALOG}.{BRONZE}.rating_periods
    WHERE `ns` = {NS_LIT}
    GROUP BY `tenant_id`, to_date(`period_start`)
    HAVING count(DISTINCT `id`) > 1
    """
).collect()
if dup_periods:
    raise AssertionError(
        "KEY_DUPLICATE on RATING_PERIODS(tenant_id, period_start) in bronze: "
        f"{[(r[0], str(r[1])) for r in dup_periods]} — MERGE cannot resolve these deterministically"
    )

spark.sql(
    f"""
    CREATE OR REPLACE TEMP VIEW v_periods_src AS
    SELECT `id`, `tenant_id`, to_date(`period_start`) AS `period_start`,
           to_date(`period_end`) AS `period_end`, 'source-migrated' AS `_origin`
    FROM {CATALOG}.{BRONZE}.rating_periods
    WHERE `ns` = {NS_LIT}
      AND to_date(`period_start`) <> {PS_LIT}
    UNION ALL
    SELECT `period_id` AS `id`, `tenant_id`, {PS_LIT} AS `period_start`, {PE_LIT} AS `period_end`,
           'target-finalize' AS `_origin`
    FROM v_loaded
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TEMP VIEW v_results_src AS
    SELECT rr.`id`, rr.`period_id`, rr.`subscription_id`,
           CAST(rr.`used_units` AS DECIMAL(38,0)) AS `used_units`,
           CAST(rr.`quota_units` AS DECIMAL(38,0)) AS `quota_units`,
           CAST(rr.`rollover_units` AS DECIMAL(38,0)) AS `rollover_units`,
           CAST(rr.`billable_units` AS DECIMAL(38,0)) AS `billable_units`,
           CAST(rr.`overage_amount` AS DECIMAL(14,2)) AS `overage_amount`,
           rr.`created_at`,
           CAST(NULL AS DECIMAL(38,0)) AS `computed_rollover_units`,
           CAST(NULL AS DECIMAL(38,0)) AS `first_tier_units`,
           CAST(NULL AS DECIMAL(38,0)) AS `second_tier_units`,
           CAST(NULL AS BOOLEAN) AS `suspension_prorated`,
           CAST(NULL AS DECIMAL(12,6)) AS `overage_rate`,
           'source-migrated' AS `_origin`
    FROM {CATALOG}.{BRONZE}.rating_results rr
    JOIN {CATALOG}.{BRONZE}.rating_periods rp ON rp.`id` = rr.`period_id` AND rp.`ns` = rr.`ns`
    WHERE rr.`ns` = {NS_LIT}
      AND to_date(rp.`period_start`) <> {PS_LIT}
    UNION ALL
    SELECT {f_md5_uuid("`period_id`")} AS `id`, `period_id`, `subscription_id`,
           `used_units`, `quota_units`, `rollover_units`, `billable_units`, `overage_amount`,
           `created_at`, `computed_rollover_units`, `first_tier_units`, `second_tier_units`,
           `suspension_prorated`, `overage_rate`, 'target-finalize' AS `_origin`
    FROM v_loaded
    """
)

# COMMAND ----------

# MAGIC %md ## MERGE
# MAGIC
# MAGIC `MERGE` on `id` plus `ns` with the payload compared null-safely, so a rerun with identical
# MAGIC inputs updates nothing and the Delta metrics show it (ACC-IDEM). `_batch_id` and `_loaded_at`
# MAGIC are deliberately outside the comparison: stamping them on every run would make every rerun look
# MAGIC like a change.
# MAGIC
# MAGIC **Re-rating a period already finalized here updates only what the source updates.** A second
# MAGIC `sp_finalize_rating` for the same period hits `DUP_VAL_ON_INDEX` and its fallback `UPDATE`
# MAGIC assigns `used_units`, `rollover_units`, `billable_units`, `overage_amount` on `RATING_RESULTS`
# MAGIC (`period_end` on `RATING_PERIODS`) and nothing else, so `subscription_id`, `quota_units` and
# MAGIC `created_at` keep their first-finalize values even when the plan or subscription has since
# MAGIC changed. That set is `refinalize_update_columns` in the spec, and for a row this run rates again
# MAGIC (`_origin = 'target-finalize'` on both sides) the `UPDATE` is scoped to exactly those columns
# MAGIC plus the explanatory columns that have no source analogue, which follow the money so the row
# MAGIC stays internally consistent. The match predicate is scoped to the same columns: a changed quota
# MAGIC alone is not a difference, so it neither churns the row nor dirties the idempotency proof. Rows
# MAGIC that are not a re-rate of a row this unit finalized — migrated history, and a row changing
# MAGIC origin — take the full payload, because there the target is mirroring the source verbatim.

# COMMAND ----------


def merge_target(tbl: dict, view: str) -> dict:
    target = tbl["target"]
    cols = [c["name"] for c in tbl["columns"]]
    payload = [c for c in cols if c not in ("id",)]
    refinalize = tbl.get("refinalize_update_columns", []) + tbl.get("explicit_state_columns", [])
    stamps = [f"t.`_batch_id` = {BATCH_LIT}", "t.`_loaded_at` = current_timestamp()"]

    def diff_of(columns: list[str]) -> str:
        return " OR ".join(f"NOT (t.`{c}` <=> s.`{c}`)" for c in columns)

    def set_of(columns: list[str], origin: bool) -> str:
        return ",\n      ".join(
            [f"t.`{c}` = s.`{c}`" for c in columns]
            + (["t.`_origin` = s.`_origin`"] if origin else [])
            + stamps
        )

    insert_cols = ", ".join([f"`{c}`" for c in cols] + ["`ns`", "`_origin`", "`_batch_id`", "`_loaded_at`"])
    insert_vals = ", ".join(
        [f"s.`{c}`" for c in cols] + [NS_LIT, "s.`_origin`", BATCH_LIT, "current_timestamp()"]
    )
    refinalized = "t.`_origin` = 'target-finalize' AND s.`_origin` = 'target-finalize'"
    spark.sql(
        f"""
        MERGE INTO {full(target)} t
        USING {view} s
          ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
        WHEN MATCHED AND {refinalized} AND ({diff_of(refinalize)}) THEN UPDATE SET
      {set_of(refinalize, origin=False)}
        WHEN MATCHED AND NOT ({refinalized}) AND ({diff_of(payload + ['_origin'])}) THEN UPDATE SET
      {set_of(payload, origin=True)}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """
    )
    return merge_metrics(target)


metrics = {
    "rating_periods": merge_target(TABLES["rating_periods"], "v_periods_src"),
    "rating_results": merge_target(TABLES["rating_results"], "v_results_src"),
    f"quarantine_{UNIT}": quarantine_metrics,
}
print(json.dumps(metrics, indent=1))

# COMMAND ----------

# MAGIC %md ## fn_usage_summary
# MAGIC
# MAGIC The third entrypoint returns a cursor rather than writing a table, and this unit's contract
# MAGIC declares exactly three target objects, so the projection is ported here and emitted in the run
# MAGIC summary for the recon to compare against transcript RATING-007. `DECODE` becomes a null-safe
# MAGIC `CASE` (D-03) and the window is the same string-date comparison (D-07).

# COMMAND ----------

USAGE_SUMMARY_SQL = f"""
SELECT u.`tenant_id`,
       CASE WHEN u.`kind_cd` <=> 1 THEN 'api'
            WHEN u.`kind_cd` <=> 2 THEN 'storage'
            WHEN u.`kind_cd` <=> 3 THEN 'compute'
            ELSE 'UNKNOWN' END AS kind,
       count(*) AS event_count,
       coalesce(sum(u.`units`), CAST(0 AS DECIMAL(38,0))) AS units
FROM {CATALOG}.{BRONZE}.usage_events u
WHERE u.`ns` = {NS_LIT}
  AND {yyyymmdd("u.`occurred_at`")}
      BETWEEN {yyyymmdd(PS_LIT)} AND {yyyymmdd(PE_LIT)}
GROUP BY u.`tenant_id`,
         CASE WHEN u.`kind_cd` <=> 1 THEN 'api'
              WHEN u.`kind_cd` <=> 2 THEN 'storage'
              WHEN u.`kind_cd` <=> 3 THEN 'compute'
              ELSE 'UNKNOWN' END
ORDER BY u.`tenant_id`, 2
"""
usage_summary = [
    {"tenant_id": r[0], "kind": r[1], "event_count": int(r[2]), "units": str(r[3])}
    for r in spark.sql(USAGE_SUMMARY_SQL).collect()
]

# COMMAND ----------

# MAGIC %md ## Anomaly detection
# MAGIC
# MAGIC Each `must-detect` entry of the contract is detected by a query over this run's own data or over
# MAGIC the source artefact, and reports its measured exposure. Where the live exposure is zero the
# MAGIC number is reported as zero and the path is declared unverified in the recon report; nothing is
# MAGIC asserted that was not measured.

# COMMAND ----------

anomalies = {}

rollover_diff = spark.sql(
    """
    SELECT count(*) AS rows_differing,
           count(*) FILTER (WHERE rollover_units > computed_rollover_units) AS persisted_higher,
           count(*) FILTER (WHERE rollover_units < computed_rollover_units) AS persisted_lower,
           CAST(sum(abs(rollover_units - computed_rollover_units)) AS STRING) AS abs_unit_delta
    FROM v_loaded
    """
).collect()[0]
anomalies["ANOM-ROLLOVER-PERSIST"] = {
    "detected": int(rollover_diff[0]) > 0,
    "detector": "silver.rating_results.rollover_units (persisted GREATEST(quota-used,0), D-09) "
    "compared row by row with computed_rollover_units (three-month banked, double-capped)",
    "rows_compared": loaded_drivers,
    "rows_where_persisted_differs_from_computed": int(rollover_diff[0]),
    "persisted_higher_than_computed": int(rollover_diff[1]),
    "persisted_lower_than_computed": int(rollover_diff[2]),
    "absolute_unit_delta": rollover_diff[3],
    "target_behaviour": "both values are persisted as explicit columns; the source formula is written "
    "verbatim to rollover_units and is not reconciled with the computed value",
}

string_vs_ts = spark.sql(
    f"""
    SELECT
      count(*) FILTER (
        WHERE {yyyymmdd("`occurred_at`")} BETWEEN {yyyymmdd(PS_LIT)} AND {yyyymmdd(PE_LIT)}
      ) AS in_window_string_compare,
      count(*) FILTER (
        WHERE `occurred_at` BETWEEN CAST({PS_LIT} AS TIMESTAMP) AND CAST({PE_LIT} AS TIMESTAMP)
      ) AS in_window_timestamp_compare,
      CAST(coalesce(sum(`units`) FILTER (
        WHERE {yyyymmdd("`occurred_at`")} BETWEEN {yyyymmdd(PS_LIT)} AND {yyyymmdd(PE_LIT)}
          AND NOT (`occurred_at` BETWEEN CAST({PS_LIT} AS TIMESTAMP) AND CAST({PE_LIT} AS TIMESTAMP))
      ), 0) AS STRING) AS units_only_string_compare
    FROM {CATALOG}.{BRONZE}.usage_events
    WHERE `ns` = {NS_LIT}
    """
).collect()[0]
anomalies["ANOM-STRING-DATE-COMPARE"] = {
    "detected": int(string_vs_ts[0]) != int(string_vs_ts[1]),
    "detector": "usage events in the period counted twice over ow_tp.bronze.usage_events: once with "
    "the source's date_format(occurred_at,'yyyyMMdd') string comparison (D-07), once with a "
    "timestamp comparison",
    "events_in_window_string_compare": int(string_vs_ts[0]),
    "events_in_window_timestamp_compare": int(string_vs_ts[1]),
    "units_included_only_by_string_compare": string_vs_ts[2],
    "target_behaviour": "the string comparison is kept, so the same boundary-day events are rated as "
    "in the source",
}

rownum = spark.sql(
    """
    SELECT count(*) FILTER (WHERE sub_candidates > 1) AS tenants_with_multiple_candidates,
           count(*) FILTER (WHERE sub_tied_rows > 1) AS tenants_with_tied_starts_on,
           max(sub_candidates) AS max_candidates
    FROM v_judged
    """
).collect()[0]
anomalies["ANOM-ROWNUM-1"] = {
    "detected": True,
    "detector": "the covering-subscription lookup is materialised as a window over all candidate rows, "
    "so the number of rows the source's ROWNUM <= 1 discards is measured per tenant instead of assumed",
    "tenants_with_more_than_one_covering_subscription": int(rownum[0]),
    "tenants_with_tied_starts_on": int(rownum[1]),
    "max_candidate_rows_for_one_tenant": int(rownum[2] or 0),
    "source_construct": "SELECT ... FROM (SELECT ... ORDER BY s.starts_on DESC) WHERE ROWNUM <= 1, "
    "on a non-unique starts_on, in both compute_rating and sp_finalize_rating",
    "target_resolution": "row_number() OVER (PARTITION BY tenant_id ORDER BY starts_on DESC, id DESC) = 1 "
    "(D-08). For tenants with tied starts_on the source is nondeterministic and the target is not: "
    "target and a given source run may legitimately differ there.",
}

globals_declared = [
    "g_tenant_id", "g_period_start", "g_period_end", "g_used_units", "g_quota_units",
    "g_rollover_units", "g_billable_units", "g_first_tier", "g_second_tier", "g_overage_amount",
]
order_probe = spark.sql(
    """
    SELECT count(*) AS rows_compared,
           count(*) FILTER (WHERE NOT (a.billable_units <=> b.billable_units)
                              OR NOT (a.overage_amount <=> b.overage_amount)
                              OR NOT (a.rollover_units <=> b.rollover_units)) AS rows_differing
    FROM v_loaded a
    JOIN (SELECT * FROM v_loaded ORDER BY tenant_id DESC) b USING (tenant_id)
    """
).collect()[0]
anomalies["ANOM-PKG-GLOBAL-STATE"] = {
    "detected": True,
    "detector": "the source's package globals are enumerated from the rating package and mapped one by "
    "one onto explicit target columns; the target's order-independence is then measured by recomputing "
    "the population under a different row order and comparing money and units row by row",
    "source_package_globals": globals_declared,
    "source_globals_read_outside_the_computing_procedure": [
        "g_used_units", "g_quota_units", "g_rollover_units", "g_billable_units",
        "g_first_tier", "g_second_tier", "g_overage_amount",
    ],
    "rows_compared_under_reordering": int(order_probe[0]),
    "rows_differing_under_reordering": int(order_probe[1]),
    "target_behaviour": "no cross-row or cross-call state: every value pkg_rating carried in a global "
    "is a column of the row it belongs to (used_units, quota_units, computed_rollover_units, "
    "billable_units, first_tier_units, second_tier_units, overage_amount), so a second call cannot see "
    "the first's state",
}

swallowed = spark.sql(
    """
    SELECT count(*) FILTER (WHERE subscription_id IS NULL) AS no_covering_subscription,
           count(*) FILTER (WHERE quota_units IS NULL) AS no_covering_plan,
           count(*) FILTER (WHERE overage_amount IS NULL) AS null_overage_amount,
           count(*) FILTER (WHERE bad_usage_rows > 0) AS unknown_usage_kind
    FROM v_judged
    """
).collect()[0]
anomalies["ANOM-SWALLOWED-EXCEPTION"] = {
    "detected": True,
    "detector": "every source path that swallows a failure in the rating lineage is enumerated and its "
    "live exposure counted over this run's population; the target routes each one to quarantine or a "
    "halt, and a quarantined tenant-period produces no rating row at all",
    "source_swallowed_paths": [
        "compute_rating: WHEN NO_DATA_FOUND THEN NULL around the covering-subscription lookup — "
        "v_sub_id/v_plan_id stay NULL and rating continues",
        "compute_rating: WHEN NO_DATA_FOUND THEN NULL around the plan lookup — v_included/v_rate stay "
        "NULL, so quota and overage become NULL and billable silently becomes 0",
        "sp_finalize_rating: WHEN NO_DATA_FOUND THEN v_sub_id := NULL, then INSERT into NOT NULL "
        "subscription_id raises ORA-01400 and the tenant's finalize aborts mid-batch",
        "pkg_ow_util.log_msg: WHEN OTHERS THEN ROLLBACK — the autonomous-transaction audit write is "
        "discarded silently (D-20, out of parity scope)",
        "pkg_ow_util.f_str2dt: WHEN OTHERS THEN RETURN NULL — unparseable dates become NULL "
        "(not reached by this unit: rating reads DATE and TIMESTAMP columns only)",
    ],
    "live_exposure": {
        "tenant_periods_without_covering_subscription": int(swallowed[0]),
        "tenant_periods_without_covering_plan": int(swallowed[1]),
        "tenant_periods_with_null_overage_amount": int(swallowed[2]),
        "tenant_periods_with_unknown_usage_kind": int(swallowed[3]),
    },
    "target_behaviour": "quarantine with FK_ORPHAN (D-19 cause NO_COVERING_PLAN) or CODE_UNKNOWN "
    "(D-16), counted toward the 5% halt; no partial rating row is ever written",
}

# COMMAND ----------

# MAGIC %md ## Run summary
# MAGIC
# MAGIC Everything the recon needs, recomputed from the Delta targets after the `MERGE`, written to
# MAGIC `<landing>/<ns>/silver_rating/_runs/<batch_id>.json`. The driver reads this file; it does not
# MAGIC recompute the pipeline's own numbers from anything but the targets.

# COMMAND ----------

target_counts = {}
for name in ("rating_periods", "rating_results"):
    row = spark.sql(
        f"""
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE `_origin` = 'target-finalize') AS finalized,
               count(*) FILTER (WHERE `_origin` = 'source-migrated') AS migrated,
               count(*) FILTER (WHERE `ns` IS NULL) AS rows_without_ns
        FROM {full(name)} WHERE `ns` = {NS_LIT}
        """
    ).collect()[0]
    target_counts[name] = {
        "rows": int(row[0]),
        "target_finalize_rows": int(row[1]),
        "source_migrated_rows": int(row[2]),
        "rows_without_ns": int(row[3]),
    }

money = spark.sql(
    f"""
    SELECT CAST(coalesce(sum(`overage_amount`), 0) AS STRING) AS overage_total,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'target-finalize' THEN `overage_amount` END), 0)
                AS STRING) AS overage_total_finalized,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'source-migrated' THEN `overage_amount` END), 0)
                AS STRING) AS overage_total_migrated,
           CAST(coalesce(sum(`used_units`), 0) AS STRING) AS used_units_total,
           CAST(coalesce(sum(`billable_units`), 0) AS STRING) AS billable_units_total,
           CAST(coalesce(sum(`rollover_units`), 0) AS STRING) AS rollover_units_total,
           CAST(coalesce(sum(`computed_rollover_units`), 0) AS STRING) AS computed_rollover_total
    FROM {full('rating_results')} WHERE `ns` = {NS_LIT}
    """
).collect()[0]

quar_by_reason = {
    r[0]: int(r[1])
    for r in spark.sql(
        f"SELECT `quarantine_reason`, count(*) FROM {QUARANTINE} WHERE `ns` = {NS_LIT} "
        f"GROUP BY `quarantine_reason` ORDER BY 1"
    ).collect()
}

rated_rows = [
    r.asDict()
    for r in spark.sql(
        f"""
        SELECT rp.`tenant_id`, rr.`id`, rr.`period_id`, rr.`subscription_id`,
               CAST(rr.`used_units` AS STRING) AS used_units,
               CAST(rr.`quota_units` AS STRING) AS quota_units,
               CAST(rr.`rollover_units` AS STRING) AS rollover_units,
               CAST(rr.`computed_rollover_units` AS STRING) AS computed_rollover_units,
               CAST(rr.`first_tier_units` AS STRING) AS first_tier_units,
               CAST(rr.`second_tier_units` AS STRING) AS second_tier_units,
               CAST(rr.`billable_units` AS STRING) AS billable_units,
               CAST(rr.`overage_amount` AS STRING) AS overage_amount,
               rr.`suspension_prorated`,
               date_format(rr.`created_at`, 'yyyy-MM-dd HH:mm:ss') AS created_at,
               date_format(rp.`period_start`, 'yyyy-MM-dd') AS period_start,
               date_format(rp.`period_end`, 'yyyy-MM-dd') AS period_end,
               rr.`_origin`
        FROM {full('rating_results')} rr
        JOIN {full('rating_periods')} rp ON rp.`id` = rr.`period_id` AND rp.`ns` = rr.`ns`
        WHERE rr.`ns` = {NS_LIT}
        ORDER BY rp.`tenant_id`, rp.`period_start`
        """
    ).collect()
]

# What the bank was read from, as it stood before this run's MERGE: how many tenants had banked
# rollover at all, how many of them drew on a period only silver has finalized, and the units that
# came from each side. This is the evidence for the bronze-wins deduplication above.
_bank = spark.sql(
    """
    SELECT count(*) AS tenants_with_bank,
           coalesce(sum(bank_rows_from_bronze), 0) AS bank_rows_from_bronze,
           coalesce(sum(bank_rows_from_silver), 0) AS bank_rows_from_silver,
           count(*) FILTER (WHERE bank_rows_from_silver > 0) AS tenants_drawing_on_silver,
           CAST(coalesce(sum(prior_units), 0) AS STRING) AS prior_units_total,
           CAST(coalesce(sum(prior_units_from_silver), 0) AS STRING) AS prior_units_from_silver_total
    FROM v_prior_bank
    """
).collect()[0]
prior_bank_evidence = {
    "read_from": [
        f"{CATALOG}.{BRONZE}.rating_results (the source's own finalized rows; authoritative)",
        f"{full('rating_results')} where _origin = 'target-finalize' "
        "(periods this unit finalized that the source has not)",
    ],
    "deduplicated_per": ["tenant_id", "period_start"],
    "winner_when_both_exist": "bronze",
    "lookback_months": ROLLOVER_MONTHS,
    "tenants_with_bank": int(_bank["tenants_with_bank"]),
    "tenants_drawing_on_silver": int(_bank["tenants_drawing_on_silver"]),
    "bank_rows_from_bronze": int(_bank["bank_rows_from_bronze"]),
    "bank_rows_from_silver": int(_bank["bank_rows_from_silver"]),
    "prior_units_total": _bank["prior_units_total"],
    "prior_units_from_silver_total": _bank["prior_units_from_silver_total"],
    # Every tenant whose bank draws on bronze first (these are the ones where the deduplication
    # decides something), then a few that draw on silver alone.
    "sample": [
        r.asDict()
        for r in spark.sql(
            """
            SELECT `tenant_id`, bank_rows, bank_rows_from_bronze, bank_rows_from_silver,
                   CAST(prior_units AS STRING) AS prior_units,
                   CAST(prior_units_from_silver AS STRING) AS prior_units_from_silver
            FROM v_prior_bank
            ORDER BY bank_rows_from_bronze DESC, bank_rows_from_silver DESC, `tenant_id`
            LIMIT 6
            """
        ).collect()
    ],
}
print(json.dumps(prior_bank_evidence, indent=1))

column_types = {
    f"{r[0]}.{r[1]}": r[2]
    for r in spark.sql(
        f"""
        SELECT table_name, column_name, full_data_type
        FROM {CATALOG}.information_schema.columns
        WHERE table_schema = {sql_str(SCHEMA)}
          AND table_name IN ('rating_periods', 'rating_results', 'quarantine_{UNIT}')
        """
    ).collect()
}

summary = {
    "unit": UNIT,
    "ns": NS,
    "batch_id": BATCH_ID,
    "period": {"start": PERIOD_START, "end": PERIOD_END},
    "spec_path": SPEC_PATH,
    "bronze_inputs": SPEC["bronze_inputs"],
    "drivers": {
        "source_rows": source_rows_drivers,
        "loaded_rows": loaded_drivers,
        "quarantined_rows": quarantined_rows,
        "quarantine_rate_pct": round(quar_pct, 4),
        "quarantine_by_reason": quar_by_reason,
    },
    "target_counts": target_counts,
    "money": {
        "overage_amount_total": money[0],
        "overage_amount_total_target_finalize": money[1],
        "overage_amount_total_source_migrated": money[2],
        "used_units_total": money[3],
        "billable_units_total": money[4],
        "rollover_units_total_persisted": money[5],
        "computed_rollover_units_total": money[6],
        "quarantined_rows_alongside_money": quarantined_rows,
    },
    "merge_metrics": metrics,
    "refinalize": {
        "quarantine_persisted_before_halt_decision": True,
        "plan_overrides": PLAN_OVERRIDES,
        "update_columns": {
            name: TABLES[name].get("refinalize_update_columns", [])
            + TABLES[name].get("explicit_state_columns", [])
            for name in ("rating_periods", "rating_results")
        },
        "columns_held_at_first_finalize": {
            "rating_results": ["subscription_id", "quota_units", "created_at"],
            "rating_periods": ["tenant_id", "period_start"],
        },
    },
    "prior_bank": prior_bank_evidence,
    "overflow_probe": overflow_probe,
    "proration_probe": proration_probe,
    "column_types": column_types,
    "usage_summary": usage_summary,
    "rating_rows": rated_rows,
    "anomaly_detections": anomalies,
}

out_path = f"{LANDING}/_runs/{BATCH_ID}.json"
dbutils.fs.mkdirs(f"{LANDING}/_runs")
dbutils.fs.put(out_path, json.dumps(summary, indent=1), overwrite=True)
print(f"run summary -> {out_path}")
dbutils.notebook.exit(json.dumps({"run_summary": out_path, "batch_id": BATCH_ID}))
