# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_silver_invoicing
# MAGIC
# MAGIC Port of the OW_BILLING invoicing engine (`pkg_invoicing`: `compute_preview`,
# MAGIC `fn_invoice_preview`, `fn_invoice_lines`, `sp_issue_invoice`) onto `ow_tp.silver.invoices`,
# MAGIC `ow_tp.silver.invoice_lines`, `ow_tp.silver.credit_applications` and
# MAGIC `ow_tp.silver.quarantine_silver_invoicing`. This is the code that decides what a customer is
# MAGIC actually charged, so every arithmetic step below is the source's step, in the source's order.
# MAGIC
# MAGIC Inputs are the wave-1 bronze tables (`ow_tp.bronze.*`), read only. Behaviour is fixed by
# MAGIC `docs/tech-partnerships/contracts/silver_invoicing.json` and
# MAGIC `.migration/09_semantic_dictionary.md`:
# MAGIC
# MAGIC * **D-10 / ACC-INLINE-RATING** the overage is **recomputed inline** by the same expressions
# MAGIC   `pkg_rating.compute_rating` evaluates, because `compute_preview` reads it out of
# MAGIC   `pkg_rating.g_overage_amount` — a package global — and never out of `RATING_RESULTS`.
# MAGIC   `ow_tp.silver.rating_*` is not read at all. `ow_tp.bronze.rating_results` is read for exactly
# MAGIC   one thing, and only because `compute_rating` reads it: the three-month rollover bank of
# MAGIC   periods strictly earlier than this one. D-09's persisted `rollover_units` is *not* the
# MAGIC   rollover the same call computes, and `ANOM-GLOBAL-DEPENDENCY` below measures what the
# MAGIC   invoices would have become had the persisted value been consumed instead.
# MAGIC * **D-11 / ACC-TAX** `TAX_RATE CONSTANT NUMBER := 0.0825` lives in the package body and has no
# MAGIC   column anywhere in the source or in bronze. The tax is emitted as two halves that are each
# MAGIC   left **unrounded** in the preview and rounded only where the source rounds them, so the
# MAGIC   header tax is `2 * ROUND(g_tax/2, 2)` and not `ROUND(g_tax, 2)`.
# MAGIC * **D-12 / ACC-CREDIT-BURN** the credit burn-down stays sequential in the source's
# MAGIC   `ORDER BY issued_on, id`, with the running counter decremented by each note's *pre-update*
# MAGIC   balance, and the balances the sequence reads include what this unit's other invoices already
# MAGIC   applied to the same note.
# MAGIC * **D-01** every `LEAST`/`GREATEST` is wrapped so a `NULL` argument yields `NULL` (Spark's own
# MAGIC   `least`/`greatest` ignore nulls and would silently return the other side).
# MAGIC * **D-07** usage is windowed on the source's `date_format(occurred_at, 'yyyyMMdd')` string
# MAGIC   comparison; the subscription dates travel at full precision because an Oracle `DATE` carries
# MAGIC   a time and the proration factor is fractional-day arithmetic (D-13).
# MAGIC * **D-14** `f_md5_uuid` reimplemented byte for byte: the period id is
# MAGIC   `f_md5_uuid(tenant_id || TO_CHAR(period_start,'YYYY-MM-DD'))`, the invoice id is
# MAGIC   `f_md5_uuid(period_id || 'invoice')` and a line id is `f_md5_uuid(invoice_id || line_no)`.
# MAGIC * **D-20 / ANOM-DYNAMIC-SQL** the source builds its line-delete statement text at runtime; the
# MAGIC   target's rebuild is one static `DELETE` scoped to this run's invoices and `ns`.
# MAGIC * **D-04/D-23/T6** decimal-only money lineage, `DECIMAL(14,2)` money pinned in
# MAGIC   `databricks/ddl/silver_invoicing_spec.json`; no `DOUBLE` anywhere. The unrounded tax halves
# MAGIC   are `DECIMAL(28,10)`, still decimal.
# MAGIC * **D-19/11_quarantine_codes** a tenant-period the source cannot invoice is quarantined with a
# MAGIC   code from the closed set and its raw payload, never written as a partial money row.
# MAGIC
# MAGIC The job is serverless, takes `ns`, and `MERGE`s on `id` plus `ns`, so a second identical run is
# MAGIC a no-op that the run summary proves with Delta `MERGE` metrics.

# COMMAND ----------

import datetime
import json
import re

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "silver")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("period_start", "2026-02-01")
dbutils.widgets.text("period_end", "2026-02-28")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/silver_invoicing_spec.json")
dbutils.widgets.text("batch_id", "")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRONZE = dbutils.widgets.get("bronze_schema").strip()
PERIOD_START = dbutils.widgets.get("period_start").strip()
PERIOD_END = dbutils.widgets.get("period_end").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()

UNIT = "silver_invoicing"

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
    # Shape alone admits 2026-02-31, which Spark then resolves to NULL and silently empties every
    # period predicate below, so the parameter is held to a real calendar date.
    try:
        datetime.date.fromisoformat(_pval)
    except ValueError as exc:
        raise ValueError(f"{_pname}={_pval!r} is not a real calendar date: {exc}") from exc
if PERIOD_START > PERIOD_END:
    raise ValueError(f"period_start {PERIOD_START} is after period_end {PERIOD_END}")

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
INV = SPEC["invoicing_constants"]
RAT = SPEC["rating_constants"]

# The tax rate is a constant of the *source package body*, carried in the frozen spec because the
# source schema has no column for it and neither does bronze (ANOM-HARDCODED-TAX).
TAX_RATE = INV["tax_rate"]
if TAX_RATE != "0.0825":
    raise ValueError(f"tax_rate {TAX_RATE!r} is not the source's hardcoded 0.0825")
TAX_LINES = int(INV["tax_line_count"])
ISSUED_CD = int(INV["issued_status_cd"])
PREVIEW_LINES = int(INV["preview_line_count"])
CREDIT_ORDER = INV["credit_order_by"]
if CREDIT_ORDER != ["issued_on", "id"]:
    raise ValueError("the credit burn-down order is the source's ORDER BY issued_on, id")

TIER_BREAK = int(RAT["tier_break_units"])
SECOND_TIER_MULT = RAT["second_tier_multiplier"]
ROLLOVER_MONTHS = int(RAT["rollover_lookback_months"])
ROLLOVER_CAP = int(RAT["rollover_cap_multiple"])
SUSPENDED_CD = int(RAT["suspended_status_cd"])
USAGE_KIND_TYPE = RAT["usage_kind_code_type"]

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
# sp_issue_invoice is called with DATE parameters at midnight and compares its DATE columns against
# them at full precision, so the bounds reach every comparison here as midnight timestamps.
PS_TS = f"TIMESTAMP'{PERIOD_START} 00:00:00'"
PE_TS = f"TIMESTAMP'{PERIOD_END} 00:00:00'"
BATCH_LIT = sql_str(BATCH_ID)
TAX_RATE_LIT = f"CAST({TAX_RATE} AS DECIMAL(12,6))"


# The period id and the invoice id are pure functions of (tenant_id, period_start), exactly as in
# sp_issue_invoice, so they can be derived wherever they are needed without a lookup.
def period_id_expr(tenant_col: str = "`tenant_id`") -> str:
    return f_md5_uuid(f"concat({tenant_col}, date_format({PS_LIT}, 'yyyy-MM-dd'))")


def invoice_id_expr(tenant_col: str = "`tenant_id`") -> str:
    return f_md5_uuid(f"concat({period_id_expr(tenant_col)}, 'invoice')")


PERIOD_ID_EXPR = period_id_expr()
INVOICE_ID_EXPR = invoice_id_expr()

# Oracle DATE arithmetic is wall-clock: DATE - DATE is a plain difference with no zone in it. The
# session zone is pinned so a timestamp difference below is that same wall-clock difference and no
# daylight-saving jump inside a period can move a proration factor.
spark.conf.set("spark.sql.session.timeZone", "UTC")

# COMMAND ----------

# MAGIC %md ## Target DDL
# MAGIC
# MAGIC `CREATE TABLE IF NOT EXISTS` only, liquid clustering on the natural key plus `ns` (D-22).
# MAGIC This unit never drops or replaces a table, and touches nothing outside its own four targets.

# COMMAND ----------


def full(target: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{target}"


def lit(value: str) -> str:
    """A single-quoted SQL literal: the estate's prose carries apostrophes."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


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
        COMMENT {lit(f'silver_invoicing: {tbl["source_table"]} ported from pkg_invoicing; ns-scoped, MERGE on ' + "+".join(tbl["merge_key"]))}
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
    COMMENT 'silver_invoicing rejects: one reason from the closed set in .migration/11_quarantine_codes.md, with ns, source table and raw payload'
    """
)

# COMMAND ----------

# MAGIC %md ## The inline rating, step by step in the source's order
# MAGIC
# MAGIC `compute_preview` calls `pkg_rating.compute_rating(p_tenant_id, p_period_start, p_period_end)`
# MAGIC and then reads `pkg_rating.g_overage_amount` — a package global. There is no table between the
# MAGIC two procedures, so there is none here either: the computation is re-expressed inline from
# MAGIC bronze, and the values it produces are the in-call values, carried onto the invoice as explicit
# MAGIC columns (`used_units`, `quota_units`, `computed_rollover_units`, `billable_units`,
# MAGIC `first_tier_units`, `second_tier_units`, `overage_rate`, `overage_amount`).
# MAGIC
# MAGIC The one table `compute_rating` itself reads is `RATING_RESULTS`, as the three-month rollover
# MAGIC bank of periods strictly *before* this one, so `ow_tp.bronze.rating_results` is read for that
# MAGIC and nothing else. Note `sp_issue_invoice` calls `sp_finalize_rating` before the preview, and
# MAGIC the row that writes is for *this* period, which the bank's `period_start < p_period_start`
# MAGIC filter excludes — so it cannot move the invoice, and this unit does not write it: the
# MAGIC `RATING_PERIODS`/`RATING_RESULTS` targets belong to `silver_rating`.

# COMMAND ----------

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
    """ROUND(value * v_factor, scale) with the factor applied as an exact decimal ratio (D-13)."""
    return (
        f"round(CAST(CAST({value} AS DECIMAL(28,{scale})) * {factor_num(susp)} AS DECIMAL(38,10))"
        f" / {FACTOR_DEN}, {scale})"
    )


SUSPENDED_PRED = (
    f"(`status_cd` = {SUSPENDED_CD} AND `suspended_on` IS NOT NULL "
    f"AND `suspended_on` BETWEEN {PS_TS} AND {PE_TS})"
)

# compute_rating's rollover bank. Only the source's own finalized rows are read: silver.rating_*
# belongs to silver_rating and is not an input to this unit (ACC-INLINE-RATING). The filter is
# strictly earlier periods, so nothing this run does can change it.
PRIOR_BANK_SQL = f"""
SELECT rp.`tenant_id`,
       sum(coalesce(rr.`rollover_units`, CAST(0 AS DECIMAL(38,0)))) AS prior_units,
       count(*) AS bank_rows
FROM {CATALOG}.{BRONZE}.rating_results rr
JOIN {CATALOG}.{BRONZE}.rating_periods rp
  ON rp.`id` = rr.`period_id` AND rp.`ns` = rr.`ns`
WHERE rr.`ns` = {NS_LIT}
  AND rp.`period_start` < {PS_TS}
  AND rp.`period_start` >= add_months({PS_TS}, -{ROLLOVER_MONTHS})
GROUP BY rp.`tenant_id`
"""
prior_bank = spark.sql(PRIOR_BANK_SQL)
prior_bank.createOrReplaceTempView("v_prior_bank")

RATING_SQL = f"""
WITH tenant AS (
  SELECT `id` AS tenant_id
  FROM {CATALOG}.{BRONZE}.tenants
  WHERE `ns` = {NS_LIT}
),
-- compute_rating's own covering-subscription lookup: subscriptions alone, no join to plans, so a
-- subscription pointing at a missing plan still wins here and leaves quota and rate NULL.
sub_cand AS (
  SELECT s.`tenant_id`, s.`id`, s.`status_cd`, s.`suspended_on`, s.`plan_id`, s.`starts_on`,
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
         CAST(p.`included_units` AS DECIMAL(38,0)) AS v_included,
         CAST(p.`overage_rate` AS DECIMAL(12,6)) AS v_rate,
         coalesce(u.used_units, CAST(0 AS DECIMAL(38,0))) AS used_units,
         coalesce(u.usage_events_in_window, 0) AS usage_events_in_window,
         coalesce(pr.prior_units, CAST(0 AS DECIMAL(38,0))) AS prior_units,
         coalesce(pr.bank_rows, 0) AS bank_rows,
         coalesce(bk.bad_usage_rows, 0) AS bad_usage_rows,
         bk.payload AS bad_usage_payload
  FROM tenant t
  LEFT JOIN sub_pick s ON s.`tenant_id` = t.tenant_id
  LEFT JOIN {CATALOG}.{BRONZE}.plans p ON p.`id` = s.`plan_id` AND p.`ns` = {NS_LIT}
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
       subscription_id AS rating_subscription_id,
       plan_id AS rating_plan_id,
       sub_candidates, sub_tied_rows, usage_events_in_window,
       prior_units, bank_rows, bad_usage_rows, bad_usage_payload,
       CAST(v_rate AS DECIMAL(12,6)) AS overage_rate,
       CAST(used_units AS DECIMAL(38,0)) AS used_units,
       CAST(quota_units AS DECIMAL(38,0)) AS quota_units,
       CAST(computed_rollover_units AS DECIMAL(38,0)) AS computed_rollover_units,
       CAST(first_tier_units AS DECIMAL(38,0)) AS first_tier_units,
       CAST(second_tier_units AS DECIMAL(38,0)) AS second_tier_units,
       CAST(billable_units AS DECIMAL(38,0)) AS billable_units,
       -- The pre-cast overage, kept wide: narrowing it to the pinned money type here would let the
       -- cast decide the row's fate before the NUMERIC_OVERFLOW guard ever sees the value (D-23/T6).
       CAST(overage_amount AS DECIMAL(38,2)) AS overage_amount_raw,
       suspension_prorated,
       -- D-09's persisted rollover, computed but never consumed: it is the value the *table* would
       -- have carried, and ANOM-GLOBAL-DEPENDENCY prices the invoice both ways to show the gap.
       {o_greatest("`quota_units` - `used_units`", "CAST(0 AS DECIMAL(38,0))")}
         AS persisted_rollover_units
FROM prorated
"""
spark.sql(RATING_SQL).createOrReplaceTempView("v_rating")
print(f"rating drivers (tenants in ns={NS}): {spark.table('v_rating').count()}")

# COMMAND ----------

# MAGIC %md ## The credit balances the sequence reads
# MAGIC
# MAGIC `compute_preview` sums `CREDIT_NOTES.remaining_amount` over the tenant's open notes, and
# MAGIC `sp_issue_invoice` then burns those same rows down with an in-place `UPDATE`. `CREDIT_NOTES`
# MAGIC belongs to the bronze units and this unit never writes it, so the balance a note has *for this
# MAGIC invoice* is what bronze carries minus what this unit's **other** invoices already applied to
# MAGIC it: the source's sequence reads the live table and therefore sees its own earlier
# MAGIC applications, and a bank that cannot see what the unit itself wrote is exactly the defect class
# MAGIC the pilot hit in `silver_rating`. Applications made by *this* invoice are excluded, which is
# MAGIC what makes a rerun a no-op instead of a second burn.
# MAGIC
# MAGIC `remaining_amount > 0` is the source's filter, applied to that same visible balance.

# COMMAND ----------

CREDIT_STATE_SQL = f"""
WITH inv AS (
  SELECT `id` AS tenant_id, {INVOICE_ID_EXPR} AS invoice_id
  FROM {CATALOG}.{BRONZE}.tenants
  WHERE `ns` = {NS_LIT}
),
applied_elsewhere AS (
  SELECT ca.`credit_note_id`,
         sum(ca.`applied_amount`) AS applied_amount,
         count(*) AS application_rows
  FROM {full('credit_applications')} ca
  JOIN inv ON inv.tenant_id = ca.`tenant_id`
  WHERE ca.`ns` = {NS_LIT}
    AND ca.`invoice_id` <> inv.invoice_id
  GROUP BY ca.`credit_note_id`
),
notes AS (
  SELECT cn.`id` AS credit_note_id, cn.`tenant_id`, cn.`issued_on`, i.invoice_id,
         CAST(cn.`remaining_amount` AS DECIMAL(14,2)) AS bronze_remaining_amount,
         coalesce(CAST(ae.applied_amount AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2)))
           AS applied_by_other_invoices,
         coalesce(ae.application_rows, 0) AS other_application_rows,
         {o_greatest(
             "CAST(cn.`remaining_amount` AS DECIMAL(14,2)) "
             "- coalesce(CAST(ae.applied_amount AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2)))",
             "CAST(0 AS DECIMAL(14,2))",
         )} AS remaining_before
  FROM {CATALOG}.{BRONZE}.credit_notes cn
  JOIN inv i ON i.tenant_id = cn.`tenant_id`
  LEFT JOIN applied_elsewhere ae ON ae.`credit_note_id` = cn.`id`
  WHERE cn.`ns` = {NS_LIT}
)
SELECT * FROM notes WHERE `remaining_before` > CAST(0 AS DECIMAL(14,2))
"""
spark.sql(CREDIT_STATE_SQL).createOrReplaceTempView("v_credit_state")

# COMMAND ----------

# MAGIC %md ## compute_preview and fn_invoice_preview
# MAGIC
# MAGIC The plan lookup here is **not** `compute_rating`'s: `compute_preview` joins `SUBSCRIPTIONS` to
# MAGIC `PLANS`, so a subscription whose plan row is missing is skipped by this pick while it still
# MAGIC wins the rating pick. Both picks are carried (`fee_subscription_id`,
# MAGIC `rating_subscription_id`) and the run summary reports how often they disagree.
# MAGIC
# MAGIC Then, in the source's order:
# MAGIC
# MAGIC * `g_credit` — the sum of the open notes, one row at a time, no ordering;
# MAGIC * `v_exempt` — `NVL(tax_exempt_yn,'N')` from `TENANTS`;
# MAGIC * `g_tax := DECODE(v_exempt,'Y',0,(g_plan_fee + g_overage) * 0.0825)` — the hardcoded rate, and
# MAGIC   a `NULL` plan fee or overage propagating to a `NULL` tax;
# MAGIC * `v_charge_cap := ROUND(g_plan_fee + g_overage + g_tax, 2)`;
# MAGIC * `v_credit_app := LEAST(g_credit, NVL(v_charge_cap, g_credit))` — the D-01 `LEAST`, with the
# MAGIC   `NVL` that collapses a `NULL` cap so a no-plan period still applies the whole balance.
# MAGIC
# MAGIC Every `*_raw` column is the value **before** the pinned-type cast, so the `NUMERIC_OVERFLOW`
# MAGIC guard sees what the cast would otherwise have nulled or truncated first (D-23/T6).

# COMMAND ----------

PREVIEW_SQL = f"""
WITH tenant AS (
  SELECT `id` AS tenant_id, `tax_exempt_yn`
  FROM {CATALOG}.{BRONZE}.tenants
  WHERE `ns` = {NS_LIT}
),
fee_cand AS (
  SELECT s.`tenant_id`, s.`id` AS subscription_id, p.`code`, p.`monthly_fee`, s.`starts_on`,
         row_number() OVER (PARTITION BY s.`tenant_id`
                            ORDER BY s.`starts_on` DESC, s.`id` DESC) AS rn,
         count(*) OVER (PARTITION BY s.`tenant_id`) AS fee_candidates,
         count(*) OVER (PARTITION BY s.`tenant_id`, s.`starts_on`) AS fee_tied_rows
  FROM {CATALOG}.{BRONZE}.subscriptions s
  JOIN {CATALOG}.{BRONZE}.plans p ON p.`id` = s.`plan_id` AND p.`ns` = s.`ns`
  WHERE s.`ns` = {NS_LIT}
    AND s.`starts_on` <= {PE_TS}
    AND (s.`ends_on` IS NULL OR s.`ends_on` >= {PS_TS})
),
fee_pick AS (
  SELECT * FROM fee_cand WHERE rn = 1
),
credit AS (
  SELECT `tenant_id`,
         sum(`remaining_before`) AS credit_offered,
         count(*) AS open_credit_notes,
         sum(`bronze_remaining_amount`) AS bronze_credit_balance,
         sum(`applied_by_other_invoices`) AS credit_applied_by_other_invoices
  FROM v_credit_state
  GROUP BY `tenant_id`
),
pre AS (
  SELECT t.tenant_id,
         {period_id_expr("t.`tenant_id`")} AS period_id,
         {invoice_id_expr("t.`tenant_id`")} AS invoice_id,
         f.`code` AS plan_code,
         CAST(f.`monthly_fee` AS DECIMAL(14,2)) AS plan_fee_raw,
         f.subscription_id AS fee_subscription_id,
         coalesce(f.fee_candidates, 0) AS fee_candidates,
         coalesce(f.fee_tied_rows, 0) AS fee_tied_rows,
         r.* EXCEPT (r.`tenant_id`),
         -- NVL(tax_exempt_yn,'N'), then DECODE against 'Y' (D-02/D-03: no null-collapsing beyond
         -- the source's own NVL, and the comparison is the source's exact equality).
         coalesce(t.`tax_exempt_yn`, 'N') AS tax_exempt_yn,
         coalesce(c.credit_offered, CAST(0 AS DECIMAL(14,2))) AS credit_offered_raw,
         coalesce(c.open_credit_notes, 0) AS open_credit_notes,
         coalesce(c.bronze_credit_balance, CAST(0 AS DECIMAL(14,2))) AS bronze_credit_balance,
         coalesce(c.credit_applied_by_other_invoices, CAST(0 AS DECIMAL(14,2)))
           AS credit_applied_by_other_invoices
  FROM tenant t
  LEFT JOIN v_rating r ON r.tenant_id = t.tenant_id
  LEFT JOIN fee_pick f ON f.`tenant_id` = t.tenant_id
  LEFT JOIN credit c ON c.`tenant_id` = t.tenant_id
),
taxed AS (
  SELECT p.*,
         CASE WHEN p.`tax_exempt_yn` = 'Y' THEN CAST(0 AS DECIMAL(28,10))
              ELSE CAST(CAST(p.`plan_fee_raw` + p.`overage_amount_raw` AS DECIMAL(38,2))
                        * {TAX_RATE_LIT} AS DECIMAL(28,10)) END AS tax_computed_raw
  FROM pre p
),
halved AS (
  SELECT t.*,
         -- The two tax lines are g_tax/2 each, left unrounded here exactly as the cursor leaves
         -- them (D-11); the rounding happens only where the source rounds (ACC-TAX).
         CAST(t.`tax_computed_raw` / CAST({TAX_LINES} AS DECIMAL(2,0)) AS DECIMAL(28,10))
           AS tax_half_raw
  FROM taxed t
),
capped AS (
  SELECT h.*,
         round(h.`plan_fee_raw` + h.`overage_amount_raw` + h.`tax_computed_raw`, 2)
           AS charge_cap_raw
  FROM halved h
),
applied AS (
  SELECT c.*,
         {o_least("`credit_offered_raw`", "coalesce(`charge_cap_raw`, `credit_offered_raw`)")}
           AS credit_applied_raw
  FROM capped c
),
-- The header the issue loop accumulates: plan and usage lines into v_subtotal, the two tax lines
-- into v_tax, the credit line into v_credit, each added as ROUND(v_amount, 2).
header AS (
  SELECT a.*,
         round(round(a.`plan_fee_raw`, 2) + round(a.`overage_amount_raw`, 2), 2) AS subtotal_raw,
         round(round(a.`tax_half_raw`, 2) + round(a.`tax_half_raw`, 2), 2) AS tax_raw
  FROM applied a
)
SELECT h.*,
       round(h.`subtotal_raw` + h.`tax_raw` - h.`credit_applied_raw`, 2) AS total_raw,
       try_cast(h.`plan_fee_raw` AS DECIMAL(14,2)) AS plan_fee,
       try_cast(h.`overage_amount_raw` AS DECIMAL(14,2)) AS overage_amount,
       try_cast(h.`tax_computed_raw` AS DECIMAL(28,10)) AS tax_computed,
       try_cast(h.`tax_half_raw` AS DECIMAL(28,10)) AS tax_half,
       try_cast(h.`charge_cap_raw` AS DECIMAL(14,2)) AS charge_cap,
       try_cast(h.`credit_offered_raw` AS DECIMAL(14,2)) AS credit_offered,
       try_cast(h.`credit_applied_raw` AS DECIMAL(14,2)) AS credit_applied,
       try_cast(h.`subtotal_raw` AS DECIMAL(14,2)) AS subtotal,
       try_cast(h.`tax_raw` AS DECIMAL(14,2)) AS tax,
       try_cast(round(h.`subtotal_raw` + h.`tax_raw` - h.`credit_applied_raw`, 2)
                AS DECIMAL(14,2)) AS total,
       {TAX_RATE_LIT} AS tax_rate,
       -- What the same invoice would have been had the two tax halves been rounded before the
       -- split, and had the rating come from the persisted D-09 rollover instead of the in-call
       -- value. Measured, never written to a money column (ANOM-HALF-CENT-TAX / -GLOBAL-DEPENDENCY).
       round(h.`tax_computed_raw`, 2) AS tax_if_rounded_once,
       {o_greatest(
           "coalesce(`used_units` - `persisted_rollover_units` - `quota_units`, CAST(0 AS DECIMAL(38,0)))",
           "CAST(0 AS DECIMAL(38,0))",
       )} AS billable_if_persisted_rollover
FROM header h
"""
spark.sql(PREVIEW_SQL).createOrReplaceTempView("v_preview")
print(f"preview rows: {spark.table('v_preview').count()}")

# COMMAND ----------

# MAGIC %md ## Quarantine
# MAGIC
# MAGIC Reasons come from the closed set in `.migration/11_quarantine_codes.md`; nothing local is
# MAGIC invented and there is no catch-all. A quarantined tenant-period produces **no** invoice, no
# MAGIC line and no credit application, so a swallowed source failure can never surface here as a
# MAGIC partial number (`ANOM-SWALLOWED-EXCEPTION`).
# MAGIC
# MAGIC * `KEY_NULL` — the tenant id or a derived `f_md5_uuid` key is null, so no `MERGE` key exists.
# MAGIC * `FK_ORPHAN` — no covering subscription-with-plan, or no plan row behind the rating pick, so
# MAGIC   `g_plan_code`/`g_plan_fee`/`g_overage` stay `NULL` (`compute_preview`'s two
# MAGIC   `WHEN NO_DATA_FOUND THEN NULL` handlers) and the source's `INSERT` of the plan or usage line
# MAGIC   puts `NULL` into `INVOICE_LINES.description`/`.amount`, both `NOT NULL` — `ORA-01400`, after
# MAGIC   the invoice header row has already been inserted. This is D-19's `NO_COVERING_PLAN`.
# MAGIC * `CODE_UNKNOWN` — a usage event in the window carries a `kind_cd` with no `CODES` row
# MAGIC   (`trg_usage_events_check`, D-16), so the rated units, and with them the overage, cannot be
# MAGIC   trusted.
# MAGIC * `NUMERIC_OVERFLOW` — a computed value does not fit its pinned target type (D-23/T6), tested
# MAGIC   on the pre-cast `*_raw` expressions with `try_cast` so the cast cannot decide the outcome
# MAGIC   before the guard sees it. Money is never widened or rescaled to make it fit.
# MAGIC * `KEY_DUPLICATE` — two bronze rows share a primary key or a `(invoice_id, line_no)` pair, so a
# MAGIC   `MERGE` could not resolve them deterministically. Applies to the migrated source rows below.
# MAGIC
# MAGIC **Ordering: quarantine is persisted before the halt is decided.** The quarantine `MERGE` runs
# MAGIC first, then the rate is compared with the 5% threshold and the run raises, so a halted run
# MAGIC hands the operator the payloads that caused it while `invoices`, `invoice_lines` and
# MAGIC `credit_applications` stay exactly as they were.
# MAGIC
# MAGIC **Divergence, orphan invoice header.** `sp_issue_invoice` inserts the `INVOICES` row *before*
# MAGIC the line loop, so a tenant whose plan or usage line then raises leaves a zeroed invoice header
# MAGIC (`subtotal`/`tax`/`total` = 0, `status_cd` = 20) behind in the source with no lines. A
# MAGIC quarantined tenant here gets no invoice at all — a reject is preferable to a header whose money
# MAGIC never landed — so as soon as quarantine is non-empty the target carries one invoice fewer per
# MAGIC affected tenant. Recorded as a divergence, not a parity failure.

# COMMAND ----------

MONEY_MAX = "999999999999.99"  # largest DECIMAL(14,2)
UNROUNDED_MAX = "9" * 18 + ".9999999999"  # largest DECIMAL(28,10)
MONEY_COLS = (
    "plan_fee",
    "overage_amount",
    "charge_cap",
    "credit_offered",
    "credit_applied",
    "subtotal",
    "tax",
    "total",
)
UNROUNDED_COLS = ("tax_computed", "tax_half")

# Every money value this unit derives, with the inputs it is derived from: a narrowing cast anywhere
# along the chain reports an out-of-range result as NULL, and a NULL that appears while its inputs
# were present is an overflow, not a missing value. Tested so no intermediate can quietly empty a
# money column between the source expression and the pinned type.
DERIVED_MONEY = (
    ("tax_computed_raw", ("plan_fee_raw", "overage_amount_raw")),
    ("tax_half_raw", ("tax_computed_raw",)),
    ("charge_cap_raw", ("plan_fee_raw", "overage_amount_raw", "tax_computed_raw")),
    ("credit_applied_raw", ("credit_offered_raw",)),
    ("subtotal_raw", ("plan_fee_raw", "overage_amount_raw")),
    ("tax_raw", ("tax_half_raw",)),
    ("total_raw", ("subtotal_raw", "tax_raw", "credit_applied_raw")),
)


def overflow_pred(p: str) -> str:
    """True when a value did not fit its pinned target type, tested before the cast (D-23/T6).

    Two tests per column: the raw value against the target type's own bound, and the raw value
    surviving while the cast one is NULL, which is how a non-ANSI cast reports an out-of-range
    value. Either one means the number cannot be represented, so the row is rejected rather than
    landed with a silently altered amount.
    """
    parts = []
    for c in MONEY_COLS:
        parts.append(f"abs({p}`{c}_raw`) > CAST({MONEY_MAX} AS DECIMAL(14,2))")
        parts.append(f"({p}`{c}_raw` IS NOT NULL AND {p}`{c}` IS NULL)")
    for c in UNROUNDED_COLS:
        parts.append(f"abs({p}`{c}_raw`) > CAST({UNROUNDED_MAX} AS DECIMAL(28,10))")
        parts.append(f"({p}`{c}_raw` IS NOT NULL AND {p}`{c}` IS NULL)")
    for col, inputs in DERIVED_MONEY:
        present = " AND ".join(f"{p}`{i}` IS NOT NULL" for i in inputs)
        parts.append(f"({p}`{col}` IS NULL AND {present})")
    return "(" + "\n             OR ".join(parts) + ")"


JUDGE_SQL = f"""
SELECT p.*,
       CASE
         WHEN p.`tenant_id` IS NULL OR p.`period_id` IS NULL OR p.`invoice_id` IS NULL
           THEN 'KEY_NULL'
         -- The overflow guard is decided on the pre-cast values *before* any null-based branch:
         -- an out-of-range amount nulls its pinned-type column, and were FK_ORPHAN asked first it
         -- would answer for the one money column most likely to overflow (D-23/T6).
         WHEN {overflow_pred("p.")} THEN 'NUMERIC_OVERFLOW'
         WHEN p.`plan_code` IS NULL OR p.`plan_fee_raw` IS NULL OR p.`overage_amount_raw` IS NULL
           THEN 'FK_ORPHAN'
         WHEN p.`bad_usage_rows` > 0 THEN 'CODE_UNKNOWN'
         ELSE NULL
       END AS quarantine_reason
FROM v_preview p
"""
spark.sql(JUDGE_SQL).createOrReplaceTempView("v_judged")
spark.sql(
    "CREATE OR REPLACE TEMP VIEW v_loaded AS SELECT * FROM v_judged WHERE quarantine_reason IS NULL"
)

# COMMAND ----------

# MAGIC %md ### The source's own invoices and lines
# MAGIC
# MAGIC `INVOICES` and `INVOICE_LINES` rows the source already holds are its own record for periods
# MAGIC this run does not issue, so they migrate verbatim with `_origin = 'source-migrated'`. An
# MAGIC invoice this run re-issues is not migrated separately: it *is* the same row, keyed by the same
# MAGIC `f_md5_uuid`, and the re-issue rules below decide what changes on it.
# MAGIC
# MAGIC The source enforces both foreign keys and both unique constraints, so `FK_ORPHAN` and
# MAGIC `KEY_DUPLICATE` here are guards against a bronze slice that lost or doubled a row rather than
# MAGIC against the source; their live exposure is measured and reported, not assumed.

# COMMAND ----------

MIG_INV_SQL = f"""
WITH issued AS (
  SELECT `invoice_id` AS id FROM v_loaded
),
dups AS (
  SELECT `id`, count(*) AS id_rows
  FROM {CATALOG}.{BRONZE}.invoices WHERE `ns` = {NS_LIT} GROUP BY `id`
)
SELECT i.`id`, i.`tenant_id`, i.`period_id`, i.`issued_at`,
       CAST(i.`subtotal` AS DECIMAL(14,2)) AS subtotal_raw,
       CAST(i.`tax` AS DECIMAL(14,2)) AS tax_raw,
       CAST(i.`total` AS DECIMAL(14,2)) AS total_raw,
       try_cast(i.`subtotal` AS DECIMAL(14,2)) AS subtotal,
       try_cast(i.`tax` AS DECIMAL(14,2)) AS tax,
       try_cast(i.`total` AS DECIMAL(14,2)) AS total,
       CAST(i.`status_cd` AS INT) AS status_cd,
       to_json(struct(i.`id`, i.`tenant_id`, i.`period_id`, i.`issued_at`, i.`subtotal`, i.`tax`,
                      i.`total`, i.`status_cd`)) AS raw_source_payload,
       CASE
         WHEN i.`id` IS NULL OR i.`tenant_id` IS NULL OR i.`period_id` IS NULL THEN 'KEY_NULL'
         WHEN d.id_rows > 1 THEN 'KEY_DUPLICATE'
         WHEN NOT EXISTS (SELECT 1 FROM {CATALOG}.{BRONZE}.tenants t
                           WHERE t.`ns` = {NS_LIT} AND t.`id` = i.`tenant_id`)
           OR NOT EXISTS (SELECT 1 FROM {CATALOG}.{BRONZE}.rating_periods rp
                           WHERE rp.`ns` = {NS_LIT} AND rp.`id` = i.`period_id`)
           THEN 'FK_ORPHAN'
         WHEN (i.`subtotal` IS NOT NULL AND try_cast(i.`subtotal` AS DECIMAL(14,2)) IS NULL)
           OR (i.`tax` IS NOT NULL AND try_cast(i.`tax` AS DECIMAL(14,2)) IS NULL)
           OR (i.`total` IS NOT NULL AND try_cast(i.`total` AS DECIMAL(14,2)) IS NULL)
           THEN 'NUMERIC_OVERFLOW'
         ELSE NULL
       END AS quarantine_reason
FROM {CATALOG}.{BRONZE}.invoices i
LEFT JOIN dups d ON d.`id` = i.`id`
WHERE i.`ns` = {NS_LIT}
  AND NOT EXISTS (SELECT 1 FROM issued s WHERE s.id = i.`id`)
"""
spark.sql(MIG_INV_SQL).createOrReplaceTempView("v_mig_invoices")

MIG_LINE_SQL = f"""
WITH issued AS (
  SELECT `invoice_id` AS id FROM v_loaded
),
dup_id AS (
  SELECT `id`, count(*) AS id_rows
  FROM {CATALOG}.{BRONZE}.invoice_lines WHERE `ns` = {NS_LIT} GROUP BY `id`
),
dup_no AS (
  SELECT `invoice_id`, `line_no`, count(*) AS no_rows
  FROM {CATALOG}.{BRONZE}.invoice_lines WHERE `ns` = {NS_LIT} GROUP BY `invoice_id`, `line_no`
),
-- The parent invoices this run will actually load, collapsed per id so a doubled parent cannot fan
-- its children out.
parent AS (
  SELECT `id`,
         max(CASE WHEN `quarantine_reason` IS NULL THEN 1 ELSE 0 END) AS accepted_rows,
         max(CASE WHEN `quarantine_reason` IS NULL THEN 0 ELSE 1 END) AS rejected_rows
  FROM v_mig_invoices GROUP BY `id`
)
SELECT l.`id`, l.`invoice_id`, CAST(l.`line_no` AS INT) AS line_no, l.`line_type`, l.`description`,
       CAST(l.`amount` AS DECIMAL(14,2)) AS amount_raw,
       try_cast(l.`amount` AS DECIMAL(14,2)) AS amount,
       to_json(struct(l.`id`, l.`invoice_id`, l.`line_no`, l.`line_type`, l.`description`,
                      l.`amount`)) AS raw_source_payload,
       (coalesce(p.accepted_rows, 0) = 0 AND coalesce(p.rejected_rows, 0) = 1) AS parent_rejected,
       CASE
         WHEN l.`id` IS NULL OR l.`invoice_id` IS NULL OR l.`line_no` IS NULL THEN 'KEY_NULL'
         WHEN di.id_rows > 1 OR dn.no_rows > 1 THEN 'KEY_DUPLICATE'
         -- Eligibility is the *accepted* parent set, not bronze: a parent rejected for a duplicate
         -- or null key, an orphan or an overflow never reaches the target, so loading its lines
         -- would leave children with no invoice to belong to. They are rejected with their parent,
         -- carry their own quarantine row, and stay inside their own table's accounting (ACC-QUAR).
         WHEN coalesce(p.accepted_rows, 0) = 0 THEN 'FK_ORPHAN'
         WHEN l.`amount` IS NOT NULL AND try_cast(l.`amount` AS DECIMAL(14,2)) IS NULL
           THEN 'NUMERIC_OVERFLOW'
         ELSE NULL
       END AS quarantine_reason
FROM {CATALOG}.{BRONZE}.invoice_lines l
LEFT JOIN dup_id di ON di.`id` = l.`id`
LEFT JOIN dup_no dn ON dn.`invoice_id` = l.`invoice_id` AND dn.`line_no` = l.`line_no`
LEFT JOIN parent p ON p.`id` = l.`invoice_id`
WHERE l.`ns` = {NS_LIT}
  AND NOT EXISTS (SELECT 1 FROM issued s WHERE s.id = l.`invoice_id`)
"""
spark.sql(MIG_LINE_SQL).createOrReplaceTempView("v_mig_lines")

# COMMAND ----------

QUAR_SQL = f"""
SELECT `quarantine_reason`,
       {NS_LIT} AS `ns`,
       'OW_BILLING.TENANTS+SUBSCRIPTIONS+PLANS+USAGE_EVENTS+CREDIT_NOTES' AS `source_table`,
       concat_ws('|', `tenant_id`, {sql_str(PERIOD_START)}, {sql_str(PERIOD_END)}) AS `source_key`,
       coalesce(
         CASE WHEN `quarantine_reason` = 'CODE_UNKNOWN' THEN `bad_usage_payload` END,
         to_json(struct(`tenant_id`, `period_id`, `invoice_id`, `plan_code`, `plan_fee_raw`,
                        `overage_amount_raw`, `tax_computed_raw`, `credit_offered_raw`,
                        `credit_applied_raw`, `subtotal_raw`, `tax_raw`, `total_raw`,
                        `rating_subscription_id`, `fee_subscription_id`, `usage_events_in_window`))
       ) AS `raw_source_payload`,
       CASE `quarantine_reason`
         WHEN 'FK_ORPHAN' THEN 'NO_COVERING_PLAN: no covering subscription with a plan row, so compute_preview leaves g_plan_code/g_plan_fee/g_overage NULL and the source INSERT puts NULL into INVOICE_LINES.description/.amount (NOT NULL, ORA-01400) after the invoice header was already inserted'
         WHEN 'CODE_UNKNOWN' THEN concat('usage events in window with kind_cd absent from CODES(USAGE_KIND): ', `bad_usage_rows`)
         WHEN 'KEY_NULL' THEN 'tenant_id or a derived f_md5_uuid key (period_id, invoice_id) is null'
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

UNION ALL
SELECT `quarantine_reason`, {NS_LIT}, 'OW_BILLING.INVOICES', `id`, `raw_source_payload`,
       'migrated source invoice rejected before it could be loaded',
       CASE `quarantine_reason` WHEN 'KEY_DUPLICATE' THEN 'D-14' WHEN 'FK_ORPHAN' THEN 'D-19'
                               WHEN 'KEY_NULL' THEN 'D-14' ELSE 'D-23' END,
       {BATCH_LIT}, current_timestamp()
FROM v_mig_invoices WHERE `quarantine_reason` IS NOT NULL

UNION ALL
SELECT `quarantine_reason`, {NS_LIT}, 'OW_BILLING.INVOICE_LINES', `id`, `raw_source_payload`,
       CASE WHEN `parent_rejected`
            THEN 'migrated source invoice line rejected with its parent invoice, which did not '
                 || 'survive judgement, so the line would have had no invoice in the target'
            ELSE 'migrated source invoice line rejected before it could be loaded' END,
       CASE `quarantine_reason` WHEN 'KEY_DUPLICATE' THEN 'D-14' WHEN 'FK_ORPHAN' THEN 'D-19'
                               WHEN 'KEY_NULL' THEN 'D-14' ELSE 'D-23' END,
       {BATCH_LIT}, current_timestamp()
FROM v_mig_lines WHERE `quarantine_reason` IS NOT NULL
"""
spark.sql(QUAR_SQL).createOrReplaceTempView("v_quarantine_raw")

# One record per MERGE identity (ns, source_table, source_key, quarantine_reason). Several source
# rows legitimately share one identity — KEY_DUPLICATE is two bronze rows under one id by definition,
# and every KEY_NULL row whose key is null shares the null key — and inserting them all would leave
# the next run's MERGE matching one stored reject against many source rows, which Delta refuses. The
# rows are collapsed deterministically instead: the count and every payload are carried so each
# rejected source row is still diagnosable from the quarantine table alone.
spark.sql(
    """
    CREATE OR REPLACE TEMP VIEW v_quarantine AS
    SELECT `quarantine_reason`, `ns`, `source_table`, `source_key`,
           CASE WHEN count(*) = 1 THEN min(`raw_source_payload`)
                ELSE to_json(named_struct(
                       'rejected_source_rows', count(*),
                       'payloads', sort_array(collect_list(`raw_source_payload`)))) END
             AS `raw_source_payload`,
           CASE WHEN count(*) = 1 THEN min(`detail`)
                ELSE concat(min(`detail`), ' — ', CAST(count(*) AS STRING),
                            ' source rows share this rejection identity; every payload is carried '
                            || 'in raw_source_payload') END AS `detail`,
           min(`dictionary_ref`) AS `dictionary_ref`,
           min(`_batch_id`) AS `_batch_id`,
           min(`_quarantined_at`) AS `_quarantined_at`
    FROM v_quarantine_raw
    GROUP BY `quarantine_reason`, `ns`, `source_table`, `source_key`
    """
)
quarantine_source_rows = spark.table("v_quarantine_raw").count()

# The collapse's own reachability, measured rather than assumed: two synthetic rows under one merge
# identity through the same grouping the load uses. A probe of the target expression; it writes
# nothing.
_dedup_probe = spark.sql(
    """
    WITH raw AS (
      SELECT 'KEY_DUPLICATE' AS quarantine_reason, 'probe' AS ns, 'PROBE' AS source_table,
             'k' AS source_key, '{"row":1}' AS raw_source_payload, 'd' AS detail,
             'D-14' AS dictionary_ref, 'b' AS _batch_id, current_timestamp() AS _quarantined_at
      UNION ALL
      SELECT 'KEY_DUPLICATE', 'probe', 'PROBE', 'k', '{"row":2}', 'd', 'D-14', 'b',
             current_timestamp()
      UNION ALL
      SELECT 'KEY_NULL', 'probe', 'PROBE', NULL, '{"row":3}', 'd', 'D-14', 'b', current_timestamp()
      UNION ALL
      SELECT 'KEY_NULL', 'probe', 'PROBE', NULL, '{"row":4}', 'd', 'D-14', 'b', current_timestamp()
    )
    SELECT `quarantine_reason`, count(*) AS merged_rows,
           max(`raw_source_payload`) AS payload
    FROM (
      SELECT `quarantine_reason`, `source_key`,
             to_json(named_struct('rejected_source_rows', count(*),
                                  'payloads', sort_array(collect_list(`raw_source_payload`))))
               AS raw_source_payload
      FROM raw
      GROUP BY `quarantine_reason`, `ns`, `source_table`, `source_key`
    )
    GROUP BY `quarantine_reason` ORDER BY `quarantine_reason`
    """
).collect()
quarantine_identity_probe = {
    "description": "two KEY_DUPLICATE rows under one source_key and two KEY_NULL rows with a null "
    "source_key, through the same grouping the load applies: each identity collapses to one record "
    "carrying both payloads and the count, so a rerun's MERGE matches one source row per target row",
    "is_probe_of_target_expression_not_source_finding": True,
    "cases": [
        {"quarantine_reason": r[0], "merged_rows": r[1], "raw_source_payload": r[2]}
        for r in _dedup_probe
    ],
}
if [c["merged_rows"] for c in quarantine_identity_probe["cases"]] != [1, 1]:
    raise AssertionError(
        f"the quarantine identity collapse did not behave as declared: {quarantine_identity_probe}"
    )

_dup_identities = spark.sql(
    """
    SELECT count(*) FROM (
      SELECT 1 FROM v_quarantine_raw
      GROUP BY `quarantine_reason`, `ns`, `source_table`, `source_key` HAVING count(*) > 1
    )
    """
).collect()[0][0]

# The driver identities *this run* rejected. The quarantine table is a ledger of rejections, so it
# retains identities from earlier runs whose cause no longer reproduces; a corrected tenant must not
# stay excluded from the credit-burn parity check on the strength of a rejection that this run did
# not make. The run's own rejection set is published here, alongside what a read of every retained
# row would have claimed, so the difference between the two is measured rather than asserted. The
# retained row's `_batch_id` cannot carry this on its own: an unchanged rejection is not rewritten by
# the MERGE, which is exactly what keeps a rerun a no-op.
DRIVER_SOURCE_TABLE = "OW_BILLING.TENANTS+SUBSCRIPTIONS+PLANS+USAGE_EVENTS+CREDIT_NOTES"
rejected_driver_tenants_this_run = sorted(
    r[0]
    for r in spark.sql(
        f"""
        SELECT DISTINCT split(`source_key`, '\\\\|')[0]
        FROM v_quarantine WHERE `source_table` = {sql_str(DRIVER_SOURCE_TABLE)}
        """
    ).collect()
    if r[0] is not None
)
retained_driver_tenants = sorted(
    r[0]
    for r in spark.sql(
        f"""
        SELECT DISTINCT split(`source_key`, '\\\\|')[0]
        FROM {QUARANTINE}
        WHERE `ns` = {NS_LIT} AND `source_table` = {sql_str(DRIVER_SOURCE_TABLE)}
        """
    ).collect()
    if r[0] is not None
)
rejection_ledger = {
    "driver_source_table": DRIVER_SOURCE_TABLE,
    "rejected_driver_tenants_this_run": rejected_driver_tenants_this_run,
    "rejected_driver_tenants_this_run_count": len(rejected_driver_tenants_this_run),
    "retained_driver_tenants_in_target_before_this_run_s_merge": retained_driver_tenants,
    "retained_driver_tenants_count": len(retained_driver_tenants),
    "retained_but_not_rejected_by_this_run": sorted(
        set(retained_driver_tenants) - set(rejected_driver_tenants_this_run)
    ),
    "quarantine_is_a_ledger_of_rejections_not_current_state": True,
    "note": "the credit-burn parity check excludes only rejected_driver_tenants_this_run; a tenant "
    "in retained_but_not_rejected_by_this_run is compared like any other, so a rejection that no "
    "longer reproduces cannot hide a burn mismatch",
}

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

# COMMAND ----------

# MAGIC %md ### Quarantine accounting, per target
# MAGIC
# MAGIC `loaded_rows + quarantined_rows == source_rows` is asserted for every table in the unit, each
# MAGIC against its own declared source population (ACC-QUAR). The driver population is one issue per
# MAGIC tenant in `ns`; the line population is the five preview lines per issued invoice plus the
# MAGIC source's own lines; the credit-application population is one row per open note the sequence
# MAGIC visits. A quarantined driver takes its five lines and its credit applications with it, which is
# MAGIC why they are attributed to it rather than counted twice.

# COMMAND ----------

drivers_source = spark.table("v_judged").count()
drivers_loaded = spark.table("v_loaded").count()
drivers_quarantined = drivers_source - drivers_loaded

mig_inv_source = spark.table("v_mig_invoices").count()
mig_inv_quarantined = spark.sql(
    "SELECT count(*) FROM v_mig_invoices WHERE quarantine_reason IS NOT NULL"
).collect()[0][0]
mig_line_source = spark.table("v_mig_lines").count()
mig_line_quarantined = spark.sql(
    "SELECT count(*) FROM v_mig_lines WHERE quarantine_reason IS NOT NULL"
).collect()[0][0]

credit_notes_visited = spark.sql(
    """
    SELECT count(*) FROM v_credit_state cs
    JOIN v_judged j ON j.tenant_id = cs.tenant_id
    """
).collect()[0][0]
credit_notes_loaded = spark.sql(
    """
    SELECT count(*) FROM v_credit_state cs
    JOIN v_loaded l ON l.tenant_id = cs.tenant_id
    """
).collect()[0][0]

accounting = {
    "invoices": {
        "basis": "one sp_issue_invoice driver per tenant in ns, plus the source's own INVOICES rows "
        "that this run does not re-issue",
        "source_rows": drivers_source + mig_inv_source,
        "loaded_rows": drivers_loaded + (mig_inv_source - mig_inv_quarantined),
        "quarantined_rows": drivers_quarantined + mig_inv_quarantined,
    },
    "invoice_lines": {
        "basis": f"{PREVIEW_LINES} fn_invoice_preview lines per issued invoice, plus the source's own "
        "INVOICE_LINES rows for invoices this run does not re-issue",
        "source_rows": PREVIEW_LINES * drivers_source + mig_line_source,
        "loaded_rows": PREVIEW_LINES * drivers_loaded + (mig_line_source - mig_line_quarantined),
        "quarantined_rows": PREVIEW_LINES * drivers_quarantined + mig_line_quarantined,
    },
    "credit_applications": {
        "basis": "one row per open credit note the issue sequence visits, for every driver",
        "source_rows": credit_notes_visited,
        "loaded_rows": credit_notes_loaded,
        "quarantined_rows": credit_notes_visited - credit_notes_loaded,
    },
}
for _name, _acc in accounting.items():
    if _acc["loaded_rows"] + _acc["quarantined_rows"] != _acc["source_rows"]:
        raise AssertionError(f"quarantine accounting broken for {_name}: {_acc}")

for _name, _acc in accounting.items():
    _acc["rate_pct"] = (
        round(100.0 * _acc["quarantined_rows"] / _acc["source_rows"], 4)
        if _acc["source_rows"]
        else 0.0
    )

quarantined_rows = spark.table("v_quarantine").count()

# The halt rate's numerator and denominator are the *same* population: the invoice driver — one
# sp_issue_invoice per tenant-period, plus each migrated source invoice this run carries. A physical
# quarantine row is not that unit of work (one rejected driver takes five preview lines and its
# credit applications with it), so measuring physical rows against the line population would divide
# one reject by six-plus source rows and let far more than 5% of tenants fail without halting.
QUAR_BASIS = (
    "invoice driver: one sp_issue_invoice per tenant-period in ns, plus each migrated source "
    "INVOICES row this run carries — numerator and denominator on that one population"
)
quar_source_rows = accounting["invoices"]["source_rows"]
quar_rejected_rows = accounting["invoices"]["quarantined_rows"]
quar_pct = (100.0 * quar_rejected_rows / quar_source_rows) if quar_source_rows else 0.0
print(
    f"drivers={drivers_source} loaded={drivers_loaded} rejected_invoices={quar_rejected_rows} "
    f"({quar_pct:.4f}% of {quar_source_rows} invoice drivers); "
    f"physical quarantine rows={quarantined_rows}"
)

# COMMAND ----------

# MAGIC %md ### The rejects are persisted, then the halt is decided

# COMMAND ----------


def table_version(target: str) -> int:
    v = spark.sql(f"SELECT max(version) FROM (DESCRIBE HISTORY {full(target)})").collect()[0][0]
    return int(v) if v is not None else -1


# Every commit this run makes is made by the job run executing this notebook, and the version each
# target sat at before the run is captured here. The idempotency proof then reads only the commits
# this run produced: managed Delta interleaves maintenance commits (OPTIMIZE, VACUUM) and ns=demo is
# shared with other sessions holding the same PAT, so "the newest MERGE" could otherwise be somebody
# else's write dressed up as this unit's no-op.
# Serverless refuses spark.databricks.delta.commitInfo.userMetadata
# ([CONFIG_NOT_AVAILABLE.WITHOUT_SUGGESTION]), so the commit is identified by the job run that wrote
# it. `DESCRIBE HISTORY` carries both `job.jobRunId` and `job.jobName`, and the two submission modes
# this unit runs under populate them differently: the deployed Terraform job is always named
# `ow_tp_silver_invoicing` and passes `{{job.run_id}}` as the batch id, while the recon harness
# submits a one-off run named for the batch id. Attribution is therefore on the run *id* — which
# holds under both — and falls back to the name only where history reports no run id at all.
WRITE_TARGETS = ("invoices", "invoice_lines", "credit_applications", f"quarantine_{UNIT}")
base_versions = {t: table_version(t) for t in WRITE_TARGETS}
print(f"target versions before this run's writes: {base_versions}")


def context_run_ids() -> list[str]:
    """This run's Databricks run identifiers, as the notebook context reports them.

    A multitask job run and its task run carry different ids and `DESCRIBE HISTORY` reports the job
    run, so every id the context exposes is collected rather than guessing which one a given
    submission mode commits under.
    """
    ids: list[str] = []
    try:
        ctx = json.loads(
            dbutils.notebook.entry_point.getDbutils().notebook().getContext().safeToJson()
        )
    except Exception as exc:  # noqa: BLE001 - a context this runtime does not expose is not fatal
        print(f"notebook context carries no run id ({exc}); attribution falls back to the job name")
        return ids
    attrs = ctx.get("attributes") or {}
    for key in ("multitaskParentRunId", "jobRunId", "rootRunId", "currentRunId", "runId", "idInJob"):
        val = attrs.get(key)
        if val not in (None, "") and str(val) not in ids:
            ids.append(str(val))
    return ids


RUN_IDS = context_run_ids()
# The deployed job passes {{job.run_id}} as batch_id, so a numeric batch id is itself a run id.
if BATCH_ID.isdigit() and BATCH_ID not in RUN_IDS:
    RUN_IDS.append(BATCH_ID)
ATTRIBUTION = (
    "version > the target's pre-run version AND the commit's job.jobRunId is one of this run's own "
    f"run ids ({', '.join(RUN_IDS) if RUN_IDS else 'none reported'}); where DESCRIBE HISTORY reports "
    "no job run id, the fallback is the commit's job.jobName ending with this run's batch id"
)
print(f"this run's job run ids for commit attribution: {RUN_IDS}")


def writing_job(row) -> dict:
    """The job run behind a Delta commit, as DESCRIBE HISTORY reports it."""
    job = row["job"]
    if job is None:
        return {"job_name": None, "job_run_id": None}
    return {"job_name": job["jobName"], "job_run_id": job["jobRunId"]}


def commit_is_this_run(row) -> tuple[bool, str]:
    """Whether a commit is this run's, and which attribution rule decided it."""
    job = writing_job(row)
    run_id = job["job_run_id"]
    if run_id is not None and str(run_id) != "" and RUN_IDS:
        return str(run_id) in RUN_IDS, "job_run_id"
    return (job["job_name"] or "").endswith(BATCH_ID), "job_name_suffix"


def history_metrics(target: str, operation: str) -> dict:
    """This run's own `operation` commit on `target`, from DESCRIBE HISTORY.

    A commit qualifies only if it is newer than the version the target sat at before this run
    started *and* was written by one of this run's own job run ids. A run performs at most one MERGE
    and at most one DELETE per target, and a write that changed nothing produces no commit at all —
    reported as such rather than borrowed from an older commit.
    """
    rows = (
        spark.sql(f"DESCRIBE HISTORY {full(target)}")
        .where(f"operation = '{operation}' AND version > {base_versions[target]}")
        .orderBy("version", ascending=False)
        .collect()
    )
    matched = [(r,) + commit_is_this_run(r) for r in rows]
    mine = [(r, rule) for r, is_mine, rule in matched if is_mine]
    if not mine:
        return {
            "operation": operation,
            "version": None,
            "commit_from_this_run": False,
            "attributed_by": ATTRIBUTION,
            "pre_run_version": base_versions[target],
            "newer_commits_by_other_runs": [
                {"version": int(r["version"]), "writing_job_run": writing_job(r)}
                for r, _is_mine, _rule in matched
            ],
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_deleted": 0,
            "note": "this run produced no such commit on this target: the write changed nothing",
        }
    row, rule = mine[0]
    m = row["operationMetrics"] or {}
    out = {
        "operation": row["operation"],
        "version": int(row["version"]),
        "commit_from_this_run": True,
        "attributed_by": ATTRIBUTION,
        "attribution_rule_matched": rule,
        "pre_run_version": base_versions[target],
        "writing_job_run": writing_job(row),
        "rows_inserted": int(m.get("numTargetRowsInserted", 0)),
        "rows_updated": int(m.get("numTargetRowsUpdated", 0)),
        "rows_deleted": int(m.get("numTargetRowsDeleted", 0)),
    }
    if operation == "DELETE":
        out["rows_deleted"] = int(m.get("numDeletedRows", 0))
    return out


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
quarantine_metrics = history_metrics(f"quarantine_{UNIT}", "MERGE")

if quar_pct > HALT_PCT:
    raise AssertionError(
        f"STOPA-QUARANTINE: quarantine rate {quar_pct:.4f}% ({quar_rejected_rows} rejected of "
        f"{quar_source_rows} invoice drivers) exceeds {HALT_PCT}% — "
        f"halting the unit instead of loading around it. The {quarantined_rows} rejected rows are in "
        f"{QUARANTINE} (ns={NS}, _batch_id={BATCH_ID}); no invoice, line or credit application was "
        "written"
    )

# COMMAND ----------

# MAGIC %md ### Overflow guard probe
# MAGIC
# MAGIC The population above overflows nothing, so the guard's own reachability is measured rather than
# MAGIC assumed: a synthetic amount is pushed through the same cast and the same generated predicate.
# MAGIC This is a probe of the target expression only — it is not a finding about the source, and it
# MAGIC writes nothing.

# COMMAND ----------

def probe_case(column: str, raw_expr: str) -> dict:
    """Push one synthetic amount into one money column and ask the load's own predicate about it.

    Every other column is held at an in-range 1.00, so the answer is attributable to the column
    under probe. `raw_expr` is the *pre-cast* value: the cast is applied here exactly as the load
    applies it, which is the point — the guard has to reach its verdict from the raw column.
    """
    money = ", ".join(
        (
            f"{raw_expr} AS `{c}_raw`, try_cast({raw_expr} AS DECIMAL(14,2)) AS `{c}`"
            if c == column
            else f"CAST(1.00 AS DECIMAL(38,2)) AS `{c}_raw`, "
            f"try_cast(CAST(1.00 AS DECIMAL(38,2)) AS DECIMAL(14,2)) AS `{c}`"
        )
        for c in MONEY_COLS
    )
    unrounded = ", ".join(
        (
            f"{raw_expr} AS `{c}_raw`, try_cast({raw_expr} AS DECIMAL(28,10)) AS `{c}`"
            if c == column
            else f"CAST(1.00 AS DECIMAL(28,10)) AS `{c}_raw`, "
            f"try_cast(CAST(1.00 AS DECIMAL(28,10)) AS DECIMAL(28,10)) AS `{c}`"
        )
        for c in UNROUNDED_COLS
    )
    row = spark.sql(
        f"""
        WITH probe AS (SELECT {money}, {unrounded})
        SELECT CAST(p.`{column}_raw` AS STRING) AS raw_value,
               CAST(p.`{column}` AS STRING) AS cast_value,
               CASE WHEN {overflow_pred("p.")} THEN 'NUMERIC_OVERFLOW' ELSE NULL END AS reason
        FROM probe p
        """
    ).collect()[0]
    return {
        "column": column,
        "pre_cast_expression": raw_expr,
        "raw_value": row[0],
        "value_after_cast": row[1],
        "quarantine_reason": row[2],
    }


BIG = "CAST(1e14 AS DECIMAL(38,2))"
overflow_probe = {
    "description": "synthetic amounts beyond DECIMAL(14,2) — the invoice total, the rating overage "
    "that reaches the guard before any narrowing cast, and a derived total nulled by a narrowing "
    "cast while its inputs survived — plus an in-range control, each pushed through the pinned-type "
    "cast and the same generated overflow predicate the load applies",
    "is_probe_of_target_expression_not_source_finding": True,
    "cases": [
        probe_case("total", BIG),
        probe_case("overage_amount", BIG),
        probe_case("total", "CAST(NULL AS DECIMAL(38,2))"),
        probe_case("total", "CAST(12.34 AS DECIMAL(38,2))"),
    ],
}
_expected_probe = ["NUMERIC_OVERFLOW", "NUMERIC_OVERFLOW", "NUMERIC_OVERFLOW", None]
overflow_probe["expected_reasons"] = _expected_probe
print(json.dumps(overflow_probe, indent=1))
if [c["quarantine_reason"] for c in overflow_probe["cases"]] != _expected_probe:
    raise AssertionError(
        f"the NUMERIC_OVERFLOW guard did not behave as declared on the probe: {overflow_probe}"
    )

# COMMAND ----------

# MAGIC %md ## The five preview lines, and the header the loop accumulates
# MAGIC
# MAGIC `fn_invoice_preview` returns exactly five rows and `sp_issue_invoice` inserts each of them with
# MAGIC `DECODE(v_line_type, 'credit', v_line_total, v_amount)` — so the credit line lands as
# MAGIC `-v_credit_app` while every other line lands as its `amount`. The tax lines' stored amount is
# MAGIC the unrounded `g_tax/2` arriving in a `NUMBER(12,2)` column, which is the source's own rounding
# MAGIC to the cent; `preview_amount` keeps the unrounded value beside it.
# MAGIC
# MAGIC A line id is `f_md5_uuid(invoice_id || TO_CHAR(line_no))`, so the five ids are stable across
# MAGIC issues and the `MERGE` key holds (ACC-IDEM).

# COMMAND ----------

LINES_SQL = f"""
WITH lines AS (
  SELECT l.`invoice_id`, l.`tenant_id`, 1 AS line_no, 'plan' AS line_type,
         l.`plan_code` AS description,
         CAST(round(l.`plan_fee`, 2) AS DECIMAL(28,10)) AS preview_amount,
         CAST(0 AS DECIMAL(14,2)) AS preview_tax_amount,
         CAST(0 AS DECIMAL(14,2)) AS preview_credit_applied,
         CAST(round(l.`plan_fee`, 2) AS DECIMAL(28,10)) AS preview_total
  FROM v_loaded l
  UNION ALL
  SELECT l.`invoice_id`, l.`tenant_id`, 2, 'usage', 'usage overage',
         CAST(round(l.`overage_amount_raw`, 2) AS DECIMAL(28,10)),
         CAST(0 AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2)),
         CAST(round(l.`overage_amount_raw`, 2) AS DECIMAL(28,10))
  FROM v_loaded l
  UNION ALL
  SELECT l.`invoice_id`, l.`tenant_id`, 3, 'tax', 'regional tax',
         l.`tax_half`, CAST(0 AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2)), l.`tax_half`
  FROM v_loaded l
  UNION ALL
  SELECT l.`invoice_id`, l.`tenant_id`, 4, 'tax', 'local tax',
         l.`tax_half`, CAST(0 AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2)), l.`tax_half`
  FROM v_loaded l
  UNION ALL
  SELECT l.`invoice_id`, l.`tenant_id`, 5, 'credit', 'credit notes',
         CAST(0 AS DECIMAL(28,10)), CAST(0 AS DECIMAL(14,2)), l.`credit_applied`,
         CAST(-l.`credit_applied` AS DECIMAL(28,10))
  FROM v_loaded l
)
SELECT {f_md5_uuid("concat(`invoice_id`, CAST(`line_no` AS STRING))")} AS `id`,
       `invoice_id`, `tenant_id`, CAST(`line_no` AS INT) AS `line_no`, `line_type`, `description`,
       -- DECODE(v_line_type, 'credit', v_line_total, v_amount), landing in a NUMBER(12,2) column.
       CAST(CASE WHEN `line_type` = 'credit' THEN round(`preview_total`, 2)
                 ELSE round(`preview_amount`, 2) END AS DECIMAL(14,2)) AS `amount`,
       `preview_amount`, `preview_tax_amount`, `preview_credit_applied`, `preview_total`
FROM lines
"""
spark.sql(LINES_SQL).createOrReplaceTempView("v_lines_issued")

line_count = spark.table("v_lines_issued").count()
if line_count != PREVIEW_LINES * drivers_loaded:
    raise AssertionError(
        f"fn_invoice_preview returns {PREVIEW_LINES} lines per invoice: expected "
        f"{PREVIEW_LINES * drivers_loaded}, built {line_count}"
    )

# The header is the issue loop's own accumulation over those five lines, so subtotal, tax and the
# credit are read back from the lines rather than recomputed independently.
HEADER_SQL = f"""
WITH acc AS (
  SELECT `invoice_id`,
         round(sum(CASE WHEN `line_type` IN ('plan', 'usage') THEN round(`preview_amount`, 2) END), 2)
           AS subtotal,
         round(sum(CASE WHEN `line_type` = 'tax' THEN round(`preview_amount`, 2) END), 2) AS tax,
         max(CASE WHEN `line_type` = 'credit' THEN `preview_credit_applied` END) AS credit
  FROM v_lines_issued
  GROUP BY `invoice_id`
)
SELECT l.*, CAST(a.subtotal AS DECIMAL(14,2)) AS subtotal_from_lines,
       CAST(a.tax AS DECIMAL(14,2)) AS tax_from_lines,
       CAST(a.credit AS DECIMAL(14,2)) AS credit_from_lines,
       CAST(round(a.subtotal + a.tax - a.credit, 2) AS DECIMAL(14,2)) AS total_from_lines,
       -- CAST(p_period_end AS TIMESTAMP) on the first issue; a re-issue's INSERT raises
       -- DUP_VAL_ON_INDEX and its fallback UPDATE never touches issued_at, so a source invoice with
       -- this id keeps the timestamp of its first issue.
       coalesce(bi.`issued_at`, CAST({PE_LIT} AS TIMESTAMP)) AS issued_at,
       (bi.`id` IS NOT NULL) AS reissue_of_source_invoice
FROM v_loaded l
JOIN acc a ON a.`invoice_id` = l.`invoice_id`
LEFT JOIN {CATALOG}.{BRONZE}.invoices bi ON bi.`ns` = {NS_LIT} AND bi.`id` = l.`invoice_id`
"""
spark.sql(HEADER_SQL).createOrReplaceTempView("v_issued")

# The header assembled from the lines has to be the header computed from the globals: the source
# does it both ways (v_subtotal/v_tax from the cursor, the amounts from compute_preview) and they
# are the same numbers. A mismatch means the line projection and the preview arithmetic disagree.
_hdr = spark.sql(
    """
    SELECT count(*) AS rows_differing FROM v_issued
    WHERE NOT (`subtotal` <=> `subtotal_from_lines`) OR NOT (`tax` <=> `tax_from_lines`)
       OR NOT (`credit_applied` <=> `credit_from_lines`) OR NOT (`total` <=> `total_from_lines`)
    """
).collect()[0][0]
if _hdr:
    raise AssertionError(
        f"{_hdr} invoices where the header accumulated from the five preview lines differs from the "
        "header computed from compute_preview's values"
    )

# COMMAND ----------

# MAGIC %md ## The credit burn-down, sequentially
# MAGIC
# MAGIC ```sql
# MAGIC FOR r IN (SELECT id, remaining_amount FROM credit_notes
# MAGIC            WHERE tenant_id = p_tenant_id AND remaining_amount > 0
# MAGIC            ORDER BY issued_on, id) LOOP
# MAGIC     EXIT WHEN v_credit <= 0;
# MAGIC     UPDATE credit_notes
# MAGIC        SET remaining_amount = GREATEST(remaining_amount - v_credit, 0)
# MAGIC      WHERE id = r.id;
# MAGIC     v_credit := GREATEST(v_credit - r.remaining_amount, 0);
# MAGIC END LOOP;
# MAGIC ```
# MAGIC
# MAGIC The loop cannot be made set-based without changing results (D-12), so it is expressed as an
# MAGIC ordered window that reproduces the recurrence exactly rather than as an aggregate:
# MAGIC
# MAGIC * the order is the source's `ORDER BY issued_on, id`, and `id` is unique, so unlike the rating
# MAGIC   unit's `ROWNUM <= 1` the source is already deterministic here — no tie-break is invented;
# MAGIC * `credit_running_before` for note *i* is `GREATEST(v_credit_app - Σ remaining_before(j<i), 0)`,
# MAGIC   which is the recurrence's closed form because `GREATEST(x, 0)` is monotone and the counter
# MAGIC   never rises;
# MAGIC * the counter is decremented by the note's **pre-update** balance, not by the amount actually
# MAGIC   applied, because that is the value the cursor's snapshot hands the source. `applied_amount`
# MAGIC   is therefore `min(remaining_before, credit_running_before)` while `credit_running_after` is
# MAGIC   `GREATEST(credit_running_before - remaining_before, 0)`;
# MAGIC * `EXIT WHEN v_credit <= 0` is evaluated *before* the update, so a note the loop never reaches
# MAGIC   is recorded with `skipped_by_exit_when = true` and its balance untouched — the row exists
# MAGIC   because the sequence visited it, and dropping it would hide the order.

# COMMAND ----------

CREDIT_APPLY_SQL = f"""
WITH visited AS (
  SELECT cs.`credit_note_id`, cs.`tenant_id`, cs.`invoice_id`, cs.`issued_on`,
         cs.`bronze_remaining_amount`, cs.`applied_by_other_invoices`, cs.`remaining_before`,
         i.`credit_applied`,
         row_number() OVER (PARTITION BY cs.`invoice_id`
                            ORDER BY cs.`issued_on`, cs.`credit_note_id`) AS seq_no,
         coalesce(sum(cs.`remaining_before`) OVER (
             PARTITION BY cs.`invoice_id`
             ORDER BY cs.`issued_on`, cs.`credit_note_id`
             ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), CAST(0 AS DECIMAL(14,2)))
           AS consumed_before
  FROM v_credit_state cs
  JOIN v_issued i ON i.`invoice_id` = cs.`invoice_id`
),
running AS (
  SELECT v.*,
         {o_greatest("`credit_applied` - `consumed_before`", "CAST(0 AS DECIMAL(14,2))")}
           AS credit_running_before
  FROM visited v
)
SELECT {f_md5_uuid("concat(`invoice_id`, `credit_note_id`)")} AS `id`,
       `invoice_id`, `tenant_id`, `credit_note_id`, CAST(`seq_no` AS INT) AS `seq_no`, `issued_on`,
       `bronze_remaining_amount`, `applied_by_other_invoices`, `remaining_before`,
       CAST(`credit_running_before` AS DECIMAL(14,2)) AS `credit_running_before`,
       CAST(CASE WHEN `credit_running_before` <= CAST(0 AS DECIMAL(14,2))
                 THEN CAST(0 AS DECIMAL(14,2))
                 ELSE `remaining_before`
                      - {o_greatest("`remaining_before` - `credit_running_before`",
                                    "CAST(0 AS DECIMAL(14,2))")} END AS DECIMAL(14,2))
         AS `applied_amount`,
       CAST(CASE WHEN `credit_running_before` <= CAST(0 AS DECIMAL(14,2))
                 THEN `remaining_before`
                 ELSE {o_greatest("`remaining_before` - `credit_running_before`",
                                  "CAST(0 AS DECIMAL(14,2))")} END AS DECIMAL(14,2))
         AS `remaining_after`,
       CAST(CASE WHEN `credit_running_before` <= CAST(0 AS DECIMAL(14,2))
                 THEN `credit_running_before`
                 ELSE {o_greatest("`credit_running_before` - `remaining_before`",
                                  "CAST(0 AS DECIMAL(14,2))")} END AS DECIMAL(14,2))
         AS `credit_running_after`,
       (`credit_running_before` <= CAST(0 AS DECIMAL(14,2))) AS `skipped_by_exit_when`
FROM running
"""
spark.sql(CREDIT_APPLY_SQL).createOrReplaceTempView("v_credit_apps")

# The sequence must account for exactly the credit the invoice granted: every cent the invoice
# subtracted has to come out of a note this run visited, and no more.
_burn = spark.sql(
    """
    SELECT count(*) AS invoices_differing
    FROM (
      SELECT i.`invoice_id`, i.`credit_applied`,
             coalesce(sum(c.`applied_amount`), CAST(0 AS DECIMAL(14,2))) AS applied_total
      FROM v_issued i
      LEFT JOIN v_credit_apps c ON c.`invoice_id` = i.`invoice_id`
      GROUP BY i.`invoice_id`, i.`credit_applied`
    )
    WHERE NOT (`credit_applied` <=> `applied_total`)
    """
).collect()[0][0]
if _burn:
    raise AssertionError(
        f"{_burn} invoices where the sequential burn-down does not account for the credit the "
        "invoice applied — the recurrence and the LEAST(g_credit, cap) disagree"
    )

# COMMAND ----------

# MAGIC %md ## MERGE
# MAGIC
# MAGIC `MERGE` on `id` plus `ns` with the payload compared null-safely, so a rerun with identical
# MAGIC inputs updates nothing and the Delta metrics show it (ACC-IDEM). `_batch_id` and `_loaded_at`
# MAGIC are deliberately outside the comparison: stamping them on every run would make every rerun
# MAGIC look like a change.
# MAGIC
# MAGIC **A re-issue updates only what the source's re-issue updates.** A second `sp_issue_invoice` for
# MAGIC the same period hits `DUP_VAL_ON_INDEX` on the header insert; its fallback sets `status_cd`, and
# MAGIC the `UPDATE` after the line loop sets `subtotal`, `tax` and `total`. Nothing assigns
# MAGIC `tenant_id`, `period_id` or `issued_at` again, so those keep their first-issue values even
# MAGIC though the money moved — `reissue_update_columns` in the spec, plus the explanatory columns
# MAGIC that have no source analogue and follow the money so the row stays internally consistent. Rows
# MAGIC that are not a re-issue of a row this unit wrote — the source's migrated invoices, and a row
# MAGIC changing origin — take the full payload, because there the target mirrors the source verbatim.

# COMMAND ----------


def merge_target(tbl: dict, view: str, origin_scoped: str = "target-issue") -> dict:
    target = tbl["target"]
    cols = [c["name"] for c in tbl["columns"]]
    payload = [c for c in cols if c != "id"]
    reissue = tbl.get("reissue_update_columns", []) + tbl.get("explicit_state_columns", [])
    stamps = [f"t.`_batch_id` = {BATCH_LIT}", "t.`_loaded_at` = current_timestamp()"]

    def diff_of(columns: list[str]) -> str:
        return " OR ".join(f"NOT (t.`{c}` <=> s.`{c}`)" for c in columns)

    def set_of(columns: list[str], origin: bool) -> str:
        return ",\n      ".join(
            [f"t.`{c}` = s.`{c}`" for c in columns]
            + (["t.`_origin` = s.`_origin`"] if origin else [])
            + stamps
        )

    insert_cols = ", ".join(
        [f"`{c}`" for c in cols] + ["`ns`", "`_origin`", "`_batch_id`", "`_loaded_at`"]
    )
    insert_vals = ", ".join(
        [f"s.`{c}`" for c in cols] + [NS_LIT, "s.`_origin`", BATCH_LIT, "current_timestamp()"]
    )
    reissued = f"t.`_origin` = '{origin_scoped}' AND s.`_origin` = '{origin_scoped}'"
    spark.sql(
        f"""
        MERGE INTO {full(target)} t
        USING {view} s
          ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
        WHEN MATCHED AND {reissued} AND ({diff_of(reissue)}) THEN UPDATE SET
      {set_of(reissue, origin=False)}
        WHEN MATCHED AND NOT ({reissued}) AND ({diff_of(payload + ['_origin'])}) THEN UPDATE SET
      {set_of(payload, origin=True)}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """
    )
    return history_metrics(target, "MERGE")


spark.sql(
    f"""
    CREATE OR REPLACE TEMP VIEW v_invoices_src AS
    SELECT `invoice_id` AS `id`, `tenant_id`, `period_id`, `issued_at`,
           `subtotal`, `tax`, `total`, CAST({ISSUED_CD} AS INT) AS `status_cd`,
           `plan_code`, `plan_fee`, `overage_amount`, `tax_exempt_yn`, `tax_rate`,
           `tax_computed`, `tax_half`, `charge_cap`, `credit_offered`, `credit_applied`,
           `overage_rate`, `used_units`, `quota_units`, `computed_rollover_units`, `billable_units`,
           `first_tier_units`, `second_tier_units`, `suspension_prorated`,
           `rating_subscription_id`, `fee_subscription_id`,
           'target-issue' AS `_origin`
    FROM v_issued
    UNION ALL
    SELECT `id`, `tenant_id`, `period_id`, `issued_at`, `subtotal`, `tax`, `total`, `status_cd`,
           CAST(NULL AS STRING), CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS DECIMAL(14,2)),
           CAST(NULL AS STRING), CAST(NULL AS DECIMAL(12,6)),
           CAST(NULL AS DECIMAL(28,10)), CAST(NULL AS DECIMAL(28,10)),
           CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS DECIMAL(14,2)),
           CAST(NULL AS DECIMAL(12,6)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)),
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS DECIMAL(38,0)),
           CAST(NULL AS DECIMAL(38,0)), CAST(NULL AS BOOLEAN),
           CAST(NULL AS STRING), CAST(NULL AS STRING),
           'source-migrated' AS `_origin`
    FROM v_mig_invoices WHERE `quarantine_reason` IS NULL
    """
)

spark.sql(
    """
    CREATE OR REPLACE TEMP VIEW v_lines_src AS
    SELECT `id`, `invoice_id`, `line_no`, `line_type`, `description`, `amount`,
           `preview_amount`, `preview_tax_amount`, `preview_credit_applied`, `preview_total`,
           'target-issue' AS `_origin`
    FROM v_lines_issued
    UNION ALL
    SELECT `id`, `invoice_id`, `line_no`, `line_type`, `description`, `amount`,
           CAST(NULL AS DECIMAL(28,10)), CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS DECIMAL(14,2)),
           CAST(NULL AS DECIMAL(28,10)), 'source-migrated' AS `_origin`
    FROM v_mig_lines WHERE `quarantine_reason` IS NULL
    """
)

spark.sql(
    """
    CREATE OR REPLACE TEMP VIEW v_credit_apps_src AS
    SELECT `id`, `invoice_id`, `tenant_id`, `credit_note_id`, `seq_no`, `issued_on`,
           `bronze_remaining_amount`, `applied_by_other_invoices`, `remaining_before`,
           `credit_running_before`, `applied_amount`, `remaining_after`, `credit_running_after`,
           `skipped_by_exit_when`, 'target-issue' AS `_origin`
    FROM v_credit_apps
    """
)

# COMMAND ----------

# MAGIC %md ### The rebuild, as a static statement
# MAGIC
# MAGIC The source rebuilds an invoice's lines on every issue, through statement text it assembles at
# MAGIC runtime (`ANOM-DYNAMIC-SQL`):
# MAGIC
# MAGIC ```sql
# MAGIC EXECUTE IMMEDIATE 'DELETE FROM invoice_lines WHERE invoice_id = :1' USING v_invoice_id;
# MAGIC ```
# MAGIC
# MAGIC The target reaches the same end state with one static `DELETE`, scoped to `ns` and to the
# MAGIC invoices this run issues, removing only lines the rebuild does not re-emit — never a table-wide
# MAGIC delete, never DDL, and no statement text built from a row value (D-20). Deleting the rows the
# MAGIC `MERGE` is about to rewrite would churn them for nothing, so the scope excludes them; the count
# MAGIC the predicate matches is measured and reported either way.

# COMMAND ----------

REBUILD_SCOPE = f"""
`ns` = {NS_LIT}
  AND `invoice_id` IN (SELECT `invoice_id` FROM v_issued)
  AND `id` NOT IN (SELECT `id` FROM v_lines_issued)
"""
stale_lines = spark.sql(
    f"SELECT count(*) FROM {full('invoice_lines')} WHERE {REBUILD_SCOPE}"
).collect()[0][0]
lines_outside_scope_before = spark.sql(
    f"""
    SELECT count(*) FROM {full('invoice_lines')}
    WHERE `ns` = {NS_LIT} AND `invoice_id` NOT IN (SELECT `invoice_id` FROM v_issued)
    """
).collect()[0][0]
spark.sql(f"DELETE FROM {full('invoice_lines')} WHERE {REBUILD_SCOPE}")
rebuild_delete_metrics = history_metrics("invoice_lines", "DELETE")
lines_outside_scope_after = spark.sql(
    f"""
    SELECT count(*) FROM {full('invoice_lines')}
    WHERE `ns` = {NS_LIT} AND `invoice_id` NOT IN (SELECT `invoice_id` FROM v_issued)
    """
).collect()[0][0]
if lines_outside_scope_before != lines_outside_scope_after:
    raise AssertionError(
        "the scoped rebuild delete touched lines outside its scope: "
        f"{lines_outside_scope_before} -> {lines_outside_scope_after}"
    )

# COMMAND ----------

# MAGIC %md ### The credit applications this run's invoices no longer produce
# MAGIC
# MAGIC The credit sequence is recomputed from bronze on every run, and an upsert alone would leave
# MAGIC behind an application this unit wrote earlier that the new sequence does not produce — a note
# MAGIC that has left `CREDIT_NOTES`, a note whose visible balance is now zero, a corrected input that
# MAGIC shortens the sequence. `CREDIT_STATE_SQL` counts every application belonging to *other*
# MAGIC invoices as `applied_by_other_invoices`, so such a row would keep eating a real balance for
# MAGIC every later invoice, permanently.
# MAGIC
# MAGIC So the applications get the same treatment the invoice lines get: one static `DELETE`, scoped
# MAGIC to `ns` and to the invoices this run issues, removing only the rows the recomputed sequence no
# MAGIC longer emits. Applications belonging to invoices outside this run are out of scope by
# MAGIC construction, and the invariant is measured on both sides of the statement. On an unchanged
# MAGIC rerun the scope is empty, so the rerun stays a no-op.

# COMMAND ----------

CREDIT_RECONCILE_SCOPE = f"""
`ns` = {NS_LIT}
  AND `invoice_id` IN (SELECT `invoice_id` FROM v_issued)
  AND `id` NOT IN (SELECT `id` FROM v_credit_apps_src)
"""
stale_credit_apps = spark.sql(
    f"SELECT count(*) FROM {full('credit_applications')} WHERE {CREDIT_RECONCILE_SCOPE}"
).collect()[0][0]
credit_apps_outside_scope_before = spark.sql(
    f"""
    SELECT count(*) FROM {full('credit_applications')}
    WHERE `ns` = {NS_LIT} AND `invoice_id` NOT IN (SELECT `invoice_id` FROM v_issued)
    """
).collect()[0][0]
spark.sql(f"DELETE FROM {full('credit_applications')} WHERE {CREDIT_RECONCILE_SCOPE}")
credit_reconcile_delete_metrics = history_metrics("credit_applications", "DELETE")
credit_apps_outside_scope_after = spark.sql(
    f"""
    SELECT count(*) FROM {full('credit_applications')}
    WHERE `ns` = {NS_LIT} AND `invoice_id` NOT IN (SELECT `invoice_id` FROM v_issued)
    """
).collect()[0][0]
if credit_apps_outside_scope_before != credit_apps_outside_scope_after:
    raise AssertionError(
        "the scoped credit-application reconciliation touched applications outside its scope: "
        f"{credit_apps_outside_scope_before} -> {credit_apps_outside_scope_after}"
    )

metrics = {
    "invoices": merge_target(TABLES["invoices"], "v_invoices_src"),
    "invoice_lines": merge_target(TABLES["invoice_lines"], "v_lines_src"),
    "credit_applications": merge_target(TABLES["credit_applications"], "v_credit_apps_src"),
    f"quarantine_{UNIT}": quarantine_metrics,
}
print(json.dumps(metrics, indent=1))

# Nothing this run's invoices do not produce may survive in their own applications, or the next
# run's available balance is wrong: the end state is asserted, not assumed.
_left_over = spark.sql(
    f"SELECT count(*) FROM {full('credit_applications')} WHERE {CREDIT_RECONCILE_SCOPE}"
).collect()[0][0]
if _left_over:
    raise AssertionError(
        f"{_left_over} credit applications for this run's invoices survive that the recomputed "
        "sequence does not produce — they would reduce every later invoice's available credit"
    )

# COMMAND ----------

# MAGIC %md ### Publications this run's driver population no longer produces
# MAGIC
# MAGIC `sp_issue_invoice` has no retraction: an invoice the source issued in an earlier period stands
# MAGIC even once the tenant loses its subscription, is deleted, or would now fail the preview. The
# MAGIC port keeps that behaviour — the reconciliations above are scoped to the invoices this run
# MAGIC issues precisely so an earlier publication is left alone — so a published invoice whose driver
# MAGIC is no longer in the accepted population survives, with its lines and its credit applications.
# MAGIC That is parity, not drift, and the population it applies to is measured here rather than
# MAGIC argued: a period-scoped or full-refresh reconciliation is the estate-level answer if the
# MAGIC business ever wants retraction, and that decision is not this unit's to invent.

# COMMAND ----------

CURRENT_PUBLICATION = """
`id` IN (SELECT `invoice_id` FROM v_issued)
  OR `id` IN (SELECT `id` FROM v_mig_invoices WHERE `quarantine_reason` IS NULL)
"""
_surviving = spark.sql(
    f"""
    WITH surviving AS (
      SELECT `id`, `tenant_id`, `total`, `_origin`
      FROM {full('invoices')}
      WHERE `ns` = {NS_LIT} AND NOT ({CURRENT_PUBLICATION})
    )
    SELECT count(*) AS invoices,
           count(DISTINCT `tenant_id`) AS tenants,
           CAST(coalesce(sum(`total`), 0) AS STRING) AS total_money,
           (SELECT count(*) FROM {full('invoice_lines')} l
             WHERE l.`ns` = {NS_LIT} AND l.`invoice_id` IN (SELECT `id` FROM surviving))
             AS invoice_lines,
           (SELECT count(*) FROM {full('credit_applications')} c
             WHERE c.`ns` = {NS_LIT} AND c.`invoice_id` IN (SELECT `id` FROM surviving))
             AS credit_applications
    FROM surviving
    """
).collect()[0]
surviving_publications = {
    "declared_as": "parity with the source, not a divergence",
    "source_behaviour": "sp_issue_invoice issues and re-issues; it never unpublishes, so an invoice "
    "of an earlier period stands even after its tenant loses its subscription, is deleted, or would "
    "now fail the preview",
    "population": "rows in ow_tp.silver.invoices for this ns that this run's accepted output does "
    "not contain: neither issued by this run nor carried as an accepted migrated source invoice",
    "invoices": int(_surviving["invoices"]),
    "tenants": int(_surviving["tenants"]),
    "invoice_lines": int(_surviving["invoice_lines"]),
    "credit_applications": int(_surviving["credit_applications"]),
    "total_money": _surviving["total_money"],
    "why_the_port_does_not_sweep_them": "deleting them would be the port inventing a retraction the "
    "source has no concept of; the scoped reconciliations above are deliberately confined to the "
    "invoices this run issues",
    "estate_level_answer_if_retraction_is_wanted": "a period-scoped or full-refresh reconciliation, "
    "decided estate-wide alongside the cross-table publication protocol rather than by this unit",
    "sample": [
        r.asDict()
        for r in spark.sql(
            f"""
            SELECT `id`, `tenant_id`, CAST(`total` AS STRING) AS total, `_origin`
            FROM {full('invoices')}
            WHERE `ns` = {NS_LIT} AND NOT ({CURRENT_PUBLICATION})
            ORDER BY `id` LIMIT 5
            """
        ).collect()
    ],
}
print(f"publications this run's drivers no longer produce: {surviving_publications['invoices']}")

# COMMAND ----------

# MAGIC %md ## fn_invoice_lines
# MAGIC
# MAGIC The second entrypoint returns a cursor rather than writing a table (`SELECT line_no, line_type,
# MAGIC description, amount FROM invoice_lines WHERE invoice_id = :1 ORDER BY line_no`), so it is
# MAGIC ported here as a projection over the target and emitted in the run summary for the recon to
# MAGIC compare against transcript INVOICE-006.

# COMMAND ----------

invoice_lines_projection = [
    r.asDict()
    for r in spark.sql(
        f"""
        SELECT `invoice_id`, `line_no`, `line_type`, `description`,
               CAST(`amount` AS STRING) AS amount, `_origin`
        FROM {full('invoice_lines')}
        WHERE `ns` = {NS_LIT}
        ORDER BY `invoice_id`, `line_no`
        """
    ).collect()
]

# fn_invoice_preview's own cursor, for the preview transcripts: the five rows as the function
# returns them, including the unrounded tax halves and the credit line's amount/total split.
preview_projection = [
    r.asDict()
    for r in spark.sql(
        """
        SELECT `tenant_id`, `invoice_id`, `line_no`, `line_type`, `description`,
               CAST(round(`preview_amount`, 2) AS STRING) AS amount,
               CAST(`preview_amount` AS STRING) AS amount_unrounded,
               CAST(`preview_tax_amount` AS STRING) AS tax_amount,
               CAST(`preview_credit_applied` AS STRING) AS credit_applied,
               CAST(round(`preview_total`, 2) AS STRING) AS total,
               CAST(`preview_total` AS STRING) AS total_unrounded
        FROM v_lines_issued
        ORDER BY `tenant_id`, `line_no`
        """
    ).collect()
]

# COMMAND ----------

# MAGIC %md ## Anomaly detection
# MAGIC
# MAGIC Each `must-detect` entry of the contract is detected by a query over this run's own data or
# MAGIC over the source artefact, and reports its measured exposure. Where the live exposure is zero
# MAGIC the number is reported as zero and the path is declared unverified in the recon report; nothing
# MAGIC is asserted that was not measured.

# COMMAND ----------

anomalies = {}

# ANOM-GLOBAL-DEPENDENCY -------------------------------------------------------------------------
# The dependency is structural, so it is detected structurally: the globals pkg_invoicing declares,
# the one it reads out of pkg_rating, and then the money measurement — what these invoices would
# have become had the rating come from the persisted table instead of the in-call values.
persisted_variant = spark.sql(
    f"""
    WITH v AS (
      SELECT j.`tenant_id`, j.`invoice_id`, j.`subtotal`, j.`total`,
             j.`billable_units`, j.`billable_if_persisted_rollover`,
             j.`computed_rollover_units`, j.`persisted_rollover_units`,
             j.`overage_amount`,
             round({o_least("`billable_if_persisted_rollover`", f"CAST({TIER_BREAK} AS DECIMAL(38,0))")}
                   * `overage_rate`
                   + {o_greatest(f"`billable_if_persisted_rollover` - {TIER_BREAK}",
                                 "CAST(0 AS DECIMAL(38,0))")}
                     * `overage_rate` * CAST({SECOND_TIER_MULT} AS DECIMAL(2,1)), 2)
               AS overage_if_persisted
      FROM v_loaded j
    ),
    priced AS (
      SELECT v.*,
             round(`subtotal` - round(`overage_amount`, 2) + round(`overage_if_persisted`, 2), 2)
               AS subtotal_if_persisted
      FROM v
    )
    SELECT count(*) AS rows_compared,
           count(*) FILTER (WHERE NOT (`computed_rollover_units` <=> `persisted_rollover_units`))
             AS rows_where_rollover_differs,
           count(*) FILTER (WHERE NOT (`overage_amount` <=> `overage_if_persisted`))
             AS invoices_whose_overage_would_change,
           CAST(coalesce(sum(abs(`overage_amount` - `overage_if_persisted`)), 0) AS STRING)
             AS absolute_money_delta,
           CAST(coalesce(sum(abs(`computed_rollover_units` - `persisted_rollover_units`)), 0) AS STRING)
             AS absolute_unit_delta
    FROM priced
    """
).collect()[0]
anomalies["ANOM-GLOBAL-DEPENDENCY"] = {
    "detected": True,
    "detector": "the package globals pkg_invoicing declares and the one it reads out of pkg_rating "
    "are enumerated from the source and mapped onto explicit columns of the invoice row; the money "
    "consequence is then measured by repricing every invoice in this run from the persisted D-09 "
    "rollover instead of the value the inline call computed",
    "source_package_globals": ["g_plan_code", "g_plan_fee", "g_overage", "g_tax", "g_credit"],
    "global_read_across_the_package_boundary": "g_overage := pkg_rating.g_overage_amount, set by "
    "pkg_rating.compute_rating and read by pkg_invoicing.compute_preview "
    "(04_pkg_invoicing.sql:48-49) — no table between the two",
    "rating_input": "recomputed inline from ow_tp.bronze.{tenants,subscriptions,plans,usage_events}; "
    "ow_tp.bronze.rating_results is read only as compute_rating's three-month rollover bank of "
    "earlier periods; ow_tp.silver.rating_* is not read",
    "rows_compared": int(persisted_variant[0]),
    "rows_where_persisted_rollover_differs_from_in_call_value": int(persisted_variant[1]),
    "invoices_whose_overage_would_change_if_the_table_were_consumed": int(persisted_variant[2]),
    "absolute_overage_delta": persisted_variant[3],
    "absolute_rollover_unit_delta": persisted_variant[4],
    "target_behaviour": "no cross-call state: every value the two packages passed through a global "
    "is a column of the invoice row it belongs to, and the rating values on the row are the in-call "
    "values",
}

# ANOM-HARDCODED-TAX ----------------------------------------------------------------------------
tax_provenance = spark.sql(
    f"""
    SELECT count(*) AS candidate_columns
    FROM {CATALOG}.information_schema.columns
    WHERE table_schema IN ({sql_str(BRONZE)}, {sql_str(SCHEMA)})
      AND (lower(column_name) LIKE '%tax%rate%' OR lower(column_name) LIKE '%vat%'
           OR lower(column_name) LIKE '%tax_pct%')
    """
).collect()[0][0]
tax_rate_rows = spark.sql(
    f"""
    SELECT count(DISTINCT `tax_rate`) AS distinct_rates,
           CAST(min(`tax_rate`) AS STRING) AS min_rate, CAST(max(`tax_rate`) AS STRING) AS max_rate,
           count(*) FILTER (WHERE `tax_exempt_yn` = 'Y') AS exempt_invoices,
           count(*) AS invoices
    FROM v_loaded
    """
).collect()[0]
anomalies["ANOM-HARDCODED-TAX"] = {
    "detected": True,
    "detector": "the rate the invoices were priced with is compared against the source constant and "
    "against the schema: every column in ow_tp.bronze and ow_tp.silver whose name could carry a tax "
    "rate is counted, so the claim that the rate has no data provenance is measured rather than "
    "asserted",
    "source_constant": "TAX_RATE CONSTANT NUMBER := 0.0825 (04_pkg_invoicing.sql:26), commented "
    "'hardcoded 2011 combined rate'",
    "rate_carrying_columns_in_bronze_or_silver": int(tax_provenance),
    "distinct_rates_applied_this_run": int(tax_rate_rows[0]),
    "rate_applied": tax_rate_rows[1],
    "tax_exempt_invoices": int(tax_rate_rows[3]),
    "invoices_priced": int(tax_rate_rows[4]),
    "target_behaviour": "the constant is pinned in databricks/ddl/silver_invoicing_spec.json, "
    "asserted equal to 0.0825 at load time, and written onto every invoice as tax_rate so a future "
    "rate change is a visible column change and not a silent reprice",
}

# ANOM-HALF-CENT-TAX ----------------------------------------------------------------------------
half_cent = spark.sql(
    """
    SELECT count(*) AS invoices,
           count(*) FILTER (WHERE NOT (`tax` <=> round(`tax_if_rounded_once`, 2)))
             AS invoices_changed_by_rounding_the_halves,
           CAST(coalesce(sum(abs(`tax` - round(`tax_if_rounded_once`, 2))), 0) AS STRING)
             AS absolute_tax_delta,
           count(*) FILTER (WHERE `tax_half` <> round(`tax_half`, 2)) AS invoices_with_unrounded_half,
           CAST(max(abs(`tax` - round(`tax_if_rounded_once`, 2))) AS STRING) AS max_tax_delta
    FROM v_loaded
    """
).collect()[0]
half_cent_sample = [
    r.asDict()
    for r in spark.sql(
        """
        SELECT `tenant_id`, CAST(`tax_computed` AS STRING) AS tax_computed,
               CAST(`tax_half` AS STRING) AS tax_half,
               CAST(round(`tax_half`, 2) AS STRING) AS tax_half_rounded,
               CAST(`tax` AS STRING) AS tax_two_unrounded_halves,
               CAST(round(`tax_if_rounded_once`, 2) AS STRING) AS tax_if_rounded_once,
               CAST(`total` AS STRING) AS total
        FROM v_loaded
        WHERE NOT (`tax` <=> round(`tax_if_rounded_once`, 2))
        ORDER BY `tenant_id`
        LIMIT 6
        """
    ).collect()
]
anomalies["ANOM-HALF-CENT-TAX"] = {
    "detected": True,
    "detector": "each invoice's tax is computed both ways over this run's own population — the "
    "source's two unrounded halves each rounded on insert and summed, and the single ROUND(g_tax, 2) "
    "a tidier implementation would have written — and the rows that differ are counted with their "
    "money delta",
    "source_construct": "SELECT 3, 'tax', 'regional tax', g_tax / 2, ... UNION ALL SELECT 4, 'tax', "
    "'local tax', g_tax / 2, ... (04_pkg_invoicing.sql:93-95), each accumulated as ROUND(v_amount, 2) "
    "into v_tax",
    "invoices_priced": int(half_cent[0]),
    "invoices_changed_if_the_halves_were_rounded_first": int(half_cent[1]),
    "invoices_whose_half_is_not_a_whole_cent": int(half_cent[3]),
    "absolute_tax_delta": half_cent[2],
    "max_tax_delta": half_cent[4],
    "sample": half_cent_sample,
    "target_behaviour": "tax_computed and tax_half are carried as DECIMAL(28,10), the halves are "
    "rounded only where the source's NUMBER(12,2) column rounds them, and the header tax is the sum "
    "of the two rounded halves",
}

# ANOM-CREDIT-OVERAPPLY -------------------------------------------------------------------------
burn = spark.sql(
    """
    SELECT count(*) AS application_rows,
           count(DISTINCT `invoice_id`) AS invoices_with_credit,
           count(*) FILTER (WHERE `skipped_by_exit_when`) AS notes_never_reached,
           count(*) FILTER (WHERE `credit_running_after`
                                  > {zero} AND `remaining_after` <= {zero}) AS notes_fully_burned_with_counter_left,
           count(*) FILTER (WHERE `credit_running_before` > `remaining_before`)
             AS notes_debited_by_more_than_their_balance,
           CAST(coalesce(sum({o_greatest_expr}), 0) AS STRING) AS carried_beyond_note_balance,
           CAST(coalesce(sum(`applied_amount`), 0) AS STRING) AS applied_total,
           CAST(coalesce(sum(`remaining_before`), 0) AS STRING) AS balance_before_total,
           CAST(coalesce(sum(`remaining_after`), 0) AS STRING) AS balance_after_total,
           CAST(coalesce(sum(`applied_by_other_invoices`), 0) AS STRING)
             AS already_applied_by_other_invoices
    FROM v_credit_apps
    """.format(
        zero="CAST(0 AS DECIMAL(14,2))",
        o_greatest_expr=o_greatest(
            "`credit_running_before` - `remaining_before`", "CAST(0 AS DECIMAL(14,2))"
        ),
    )
).collect()[0]

# What a second sp_issue_invoice for the same period would consume. The source's re-issue recomputes
# g_credit from the balances its first issue already reduced and burns them again, so the notes end
# up consumed by more than the credit the invoice's final state grants: that is the realised
# over-application, and it is measured here without writing anything.
reissue = spark.sql(
    f"""
    WITH after_first AS (
      SELECT i.`invoice_id`, i.`tenant_id`, i.`charge_cap`, i.`credit_applied`,
             coalesce(sum(c.`remaining_after`), CAST(0 AS DECIMAL(14,2))) AS balance_after_first
      FROM v_issued i
      LEFT JOIN v_credit_apps c ON c.`invoice_id` = i.`invoice_id`
      GROUP BY i.`invoice_id`, i.`tenant_id`, i.`charge_cap`, i.`credit_applied`
    ),
    second AS (
      SELECT a.*,
             {o_least("`balance_after_first`", "coalesce(`charge_cap`, `balance_after_first`)")}
               AS credit_applied_on_reissue
      FROM after_first a
    )
    SELECT count(*) FILTER (WHERE `credit_applied_on_reissue` > CAST(0 AS DECIMAL(14,2)))
             AS invoices_that_would_burn_credit_again,
           CAST(coalesce(sum(`credit_applied_on_reissue`), 0) AS STRING)
             AS credit_burned_again_on_reissue,
           CAST(coalesce(sum(CASE WHEN `credit_applied_on_reissue` > CAST(0 AS DECIMAL(14,2))
                                  THEN `credit_applied` END), 0) AS STRING)
             AS credit_granted_by_the_first_issue,
           CAST(coalesce(sum(`credit_applied` + `credit_applied_on_reissue`
                             - `credit_applied_on_reissue`), 0) AS STRING) AS control_first_issue_total
    FROM second
    """
).collect()[0]

burn_sample = [
    r.asDict()
    for r in spark.sql(
        """
        SELECT `tenant_id`, `invoice_id`, `credit_note_id`, `seq_no`,
               date_format(`issued_on`, 'yyyy-MM-dd') AS issued_on,
               CAST(`bronze_remaining_amount` AS STRING) AS bronze_remaining_amount,
               CAST(`applied_by_other_invoices` AS STRING) AS applied_by_other_invoices,
               CAST(`remaining_before` AS STRING) AS remaining_before,
               CAST(`credit_running_before` AS STRING) AS credit_running_before,
               CAST(`applied_amount` AS STRING) AS applied_amount,
               CAST(`remaining_after` AS STRING) AS remaining_after,
               CAST(`credit_running_after` AS STRING) AS credit_running_after,
               `skipped_by_exit_when`
        FROM v_credit_apps
        ORDER BY `tenant_id`, `seq_no`
        """
    ).collect()
]
anomalies["ANOM-CREDIT-OVERAPPLY"] = {
    "detected": True,
    "detector": "the burn-down is materialised one visited note at a time, with the running counter "
    "and both balances on every row, so the order and the over-application are measured rows rather "
    "than a claim; the re-issue exposure is then evaluated on those same rows",
    "source_construct": "FOR r IN (... ORDER BY issued_on, id) LOOP EXIT WHEN v_credit <= 0; UPDATE "
    "credit_notes SET remaining_amount = GREATEST(remaining_amount - v_credit, 0) WHERE id = r.id; "
    "v_credit := GREATEST(v_credit - r.remaining_amount, 0); END LOOP "
    "(04_pkg_invoicing.sql:182-190)",
    "order_determinism": "the source's ORDER BY issued_on, id is total because CREDIT_NOTES.id is "
    "the primary key, so the target orders by (issued_on, credit_note_id) and invents no tie-break; "
    "the sequence is deterministic on both sides",
    "application_rows": int(burn[0]),
    "invoices_applying_credit": int(burn[1]),
    "notes_the_loop_never_reached": int(burn[2]),
    "notes_debited_by_more_than_their_own_balance": int(burn[4]),
    "counter_carried_beyond_a_note_balance": burn[5],
    "credit_applied_total": burn[6],
    "note_balance_before_total": burn[7],
    "note_balance_after_total": burn[8],
    "credit_already_applied_by_this_units_other_invoices": burn[9],
    "reissue_exposure": {
        "description": "a second sp_issue_invoice for the same period recomputes g_credit from the "
        "balances the first issue already reduced and burns them again, so across the two issues the "
        "tenant's notes are consumed by more than the credit the invoice finally grants",
        "invoices_that_would_burn_credit_again": int(reissue[0]),
        "credit_that_would_be_burned_again": reissue[1],
        "credit_granted_by_the_first_issue_of_those_invoices": reissue[2],
    },
    "target_behaviour": "the sequence is recomputed from bronze minus what this unit's *other* "
    "invoices applied, so it sees its own earlier applications across periods but a rerun of the "
    "same period re-derives the identical rows instead of burning the notes a second time; the "
    "divergence from the source's re-issue double-burn is declared in the recon report",
}

# ANOM-DYNAMIC-SQL ------------------------------------------------------------------------------
anomalies["ANOM-DYNAMIC-SQL"] = {
    "detected": True,
    "detector": "the source's issue path is read for EXECUTE IMMEDIATE and the statement it "
    "assembles is named with its bind; the target's replacement is the static DELETE below, whose "
    "own scope is measured on every run (rows matched, and rows outside the scope counted before and "
    "after to prove they were untouched)",
    "source_constructs": [
        "pkg_invoicing.sp_issue_invoice: EXECUTE IMMEDIATE 'DELETE FROM invoice_lines WHERE "
        "invoice_id = :1' USING v_invoice_id (04_pkg_invoicing.sql:149-150) — statement text built "
        "in the issue path, bound to a runtime invoice id",
        "pkg_ow_util.f_code_desc: EXECUTE IMMEDIATE of a SELECT against CODES assembled into v_sql "
        "(01_pkg_util.sql:36-46) — reached from this unit only through the code lookups, which the "
        "target expresses as joins to ow_tp.bronze.codes",
    ],
    "target_statement": "DELETE FROM " + full("invoice_lines") + " WHERE " + " ".join(
        REBUILD_SCOPE.split()
    ),
    "target_behaviour": "one static statement, scoped to ns and to this run's invoices, with no "
    "string built from a row value anywhere in the write path; the rebuild's end state is the same "
    "as the source's delete-and-reinsert",
    "rows_matched_by_the_scoped_delete": int(stale_lines),
    "delete_commit_metrics": rebuild_delete_metrics,
    "lines_outside_the_scope_before": int(lines_outside_scope_before),
    "lines_outside_the_scope_after": int(lines_outside_scope_after),
}

credit_reconciliation = {
    "why": "an application this unit wrote earlier that the recomputed sequence no longer produces "
    "would be counted as applied_by_other_invoices forever, so every later invoice would under-apply "
    "a real balance",
    "target_statement": "DELETE FROM "
    + full("credit_applications")
    + " WHERE "
    + " ".join(CREDIT_RECONCILE_SCOPE.split()),
    "target_behaviour": "one static statement scoped to ns and to this run's invoices, removing only "
    "rows the recomputed sequence does not re-emit; applications of invoices outside the run are out "
    "of scope by construction and the count outside the scope is measured on both sides",
    "rows_matched_by_the_scoped_delete": int(stale_credit_apps),
    "delete_commit_metrics": credit_reconcile_delete_metrics,
    "applications_outside_the_scope_before": int(credit_apps_outside_scope_before),
    "applications_outside_the_scope_after": int(credit_apps_outside_scope_after),
    "applications_left_unreconciled": int(_left_over),
}

# COMMAND ----------

# MAGIC %md ### Swallowed exceptions
# MAGIC
# MAGIC Every source path in this unit's lineage that hides a failure is enumerated with its live
# MAGIC exposure over this run's population. None of them may surface as a silently partial number: a
# MAGIC tenant that hits one is quarantined and gets no invoice at all.

# COMMAND ----------

swallowed = spark.sql(
    """
    SELECT count(*) FILTER (WHERE `fee_subscription_id` IS NULL) AS no_covering_subscription_with_plan,
           count(*) FILTER (WHERE `plan_fee_raw` IS NULL) AS null_plan_fee,
           count(*) FILTER (WHERE `overage_amount_raw` IS NULL) AS null_overage,
           count(*) FILTER (WHERE `tax_computed_raw` IS NULL) AS null_tax,
           count(*) FILTER (WHERE `rating_subscription_id` IS NULL) AS no_rating_subscription,
           count(*) FILTER (WHERE NOT (`rating_subscription_id` <=> `fee_subscription_id`))
             AS picks_disagreeing,
           count(*) FILTER (WHERE `bad_usage_rows` > 0) AS unknown_usage_kind
    FROM v_judged
    """
).collect()[0]
swallowed_paths = {
    "source_swallowed_paths": [
        "compute_preview: WHEN NO_DATA_FOUND THEN NULL around the plan/fee lookup — g_plan_code and "
        "g_plan_fee stay NULL and the preview continues, so the plan line's description and amount "
        "go NULL into NOT NULL columns later (04_pkg_invoicing.sql:44-46)",
        "compute_preview: WHEN NO_DATA_FOUND THEN v_exempt := 'N' around the tenant lookup — a "
        "missing tenant is silently treated as taxable (04_pkg_invoicing.sql:61-63)",
        "pkg_rating.compute_rating: two WHEN NO_DATA_FOUND THEN NULL handlers, which leave the "
        "quota and the rate NULL so g_overage_amount becomes NULL and the usage line follows it",
        "pkg_ow_util.log_msg: WHEN OTHERS THEN ROLLBACK — the autonomous-transaction audit write "
        "sp_issue_invoice ends with is discarded silently (D-20, out of parity scope)",
        "pkg_ow_util.f_str2dt: WHEN OTHERS THEN RETURN NULL — unparseable dates become NULL (not "
        "reached by this unit: invoicing reads DATE and TIMESTAMP columns only)",
    ],
    "live_exposure": {
        "tenants_without_a_covering_subscription_with_a_plan": int(swallowed[0]),
        "tenants_with_null_plan_fee": int(swallowed[1]),
        "tenants_with_null_overage": int(swallowed[2]),
        "tenants_with_null_tax": int(swallowed[3]),
        "tenants_without_a_rating_subscription": int(swallowed[4]),
        "tenants_where_the_two_subscription_picks_disagree": int(swallowed[5]),
        "tenants_with_an_unknown_usage_kind": int(swallowed[6]),
    },
    "target_behaviour": "quarantine with FK_ORPHAN (D-19 cause NO_COVERING_PLAN) or CODE_UNKNOWN "
    "(D-16), counted toward the 5% halt; no partial invoice, line or credit application is written "
    "for a quarantined tenant",
}

# COMMAND ----------

# MAGIC %md ## Run summary
# MAGIC
# MAGIC Everything the recon needs, recomputed from the Delta targets after the `MERGE`, written to
# MAGIC `<landing>/<ns>/silver_invoicing/_runs/<batch_id>.json`. The driver reads this file; it does not
# MAGIC recompute the pipeline's own numbers from anything but the targets.

# COMMAND ----------

target_counts = {}
for _name in ("invoices", "invoice_lines", "credit_applications"):
    row = spark.sql(
        f"""
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE `_origin` = 'target-issue') AS issued,
               count(*) FILTER (WHERE `_origin` = 'source-migrated') AS migrated,
               count(*) FILTER (WHERE `ns` IS NULL) AS rows_without_ns
        FROM {full(_name)} WHERE `ns` = {NS_LIT}
        """
    ).collect()[0]
    target_counts[_name] = {
        "rows": int(row[0]),
        "target_issue_rows": int(row[1]),
        "source_migrated_rows": int(row[2]),
        "rows_without_ns": int(row[3]),
    }

money = spark.sql(
    f"""
    SELECT CAST(coalesce(sum(`subtotal`), 0) AS STRING) AS subtotal_total,
           CAST(coalesce(sum(`tax`), 0) AS STRING) AS tax_total,
           CAST(coalesce(sum(`total`), 0) AS STRING) AS total_total,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'target-issue' THEN `subtotal` END), 0) AS STRING)
             AS subtotal_issued,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'target-issue' THEN `tax` END), 0) AS STRING)
             AS tax_issued,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'target-issue' THEN `total` END), 0) AS STRING)
             AS total_issued,
           CAST(coalesce(sum(CASE WHEN `_origin` = 'source-migrated' THEN `total` END), 0) AS STRING)
             AS total_migrated,
           CAST(coalesce(sum(`plan_fee`), 0) AS STRING) AS plan_fee_total,
           CAST(coalesce(sum(`overage_amount`), 0) AS STRING) AS overage_total,
           CAST(coalesce(sum(`credit_applied`), 0) AS STRING) AS credit_applied_total,
           CAST(coalesce(sum(`credit_offered`), 0) AS STRING) AS credit_offered_total
    FROM {full('invoices')} WHERE `ns` = {NS_LIT}
    """
).collect()[0]

lines_money = spark.sql(
    f"""
    SELECT CAST(coalesce(sum(`amount`), 0) AS STRING) AS line_amount_total,
           CAST(coalesce(sum(CASE WHEN `line_type` = 'tax' THEN `amount` END), 0) AS STRING)
             AS tax_line_total,
           CAST(coalesce(sum(CASE WHEN `line_type` = 'credit' THEN `amount` END), 0) AS STRING)
             AS credit_line_total,
           count(*) AS rows
    FROM {full('invoice_lines')} WHERE `ns` = {NS_LIT}
    """
).collect()[0]

credit_money = spark.sql(
    f"""
    SELECT CAST(coalesce(sum(`applied_amount`), 0) AS STRING) AS applied_total,
           CAST(coalesce(sum(`remaining_before`), 0) AS STRING) AS remaining_before_total,
           CAST(coalesce(sum(`remaining_after`), 0) AS STRING) AS remaining_after_total,
           count(*) AS rows
    FROM {full('credit_applications')} WHERE `ns` = {NS_LIT}
    """
).collect()[0]

quar_by_reason = {
    f"{r[0]}|{r[1]}": int(r[2])
    for r in spark.sql(
        f"SELECT `source_table`, `quarantine_reason`, count(*) FROM {QUARANTINE} "
        f"WHERE `ns` = {NS_LIT} GROUP BY 1, 2 ORDER BY 1, 2"
    ).collect()
}


def checksum(target: str, cols: list[str]) -> str:
    """A row-order-independent digest of the parity columns, for the idempotency proof (T10)."""
    proj = ", ".join(f"CAST(`{c}` AS STRING)" for c in cols)
    return spark.sql(
        f"""
        SELECT sha2(concat_ws('\\n', array_sort(collect_list(concat_ws('|', {proj})))), 256)
        FROM {full(target)} WHERE `ns` = {NS_LIT}
        """
    ).collect()[0][0]


def parity_cols(name: str) -> list[str]:
    tbl = TABLES[name]
    cols = ["id"] + tbl["natural_key"]
    return cols + [
        c["name"] for c in tbl["columns"] if c.get("parity") and c["name"] not in cols
    ]


checksums = {name: checksum(name, parity_cols(name)) for name in
             ("invoices", "invoice_lines", "credit_applications")}

invoice_rows = [
    r.asDict()
    for r in spark.sql(
        f"""
        SELECT `id`, `tenant_id`, `period_id`,
               date_format(`issued_at`, 'yyyy-MM-dd HH:mm:ss') AS issued_at,
               CAST(`subtotal` AS STRING) AS subtotal, CAST(`tax` AS STRING) AS tax,
               CAST(`total` AS STRING) AS total, `status_cd`,
               `plan_code`, CAST(`plan_fee` AS STRING) AS plan_fee,
               CAST(`overage_amount` AS STRING) AS overage_amount, `tax_exempt_yn`,
               CAST(`tax_computed` AS STRING) AS tax_computed,
               CAST(`tax_half` AS STRING) AS tax_half,
               CAST(`charge_cap` AS STRING) AS charge_cap,
               CAST(`credit_offered` AS STRING) AS credit_offered,
               CAST(`credit_applied` AS STRING) AS credit_applied,
               CAST(`used_units` AS STRING) AS used_units,
               CAST(`quota_units` AS STRING) AS quota_units,
               CAST(`computed_rollover_units` AS STRING) AS computed_rollover_units,
               CAST(`billable_units` AS STRING) AS billable_units,
               CAST(`first_tier_units` AS STRING) AS first_tier_units,
               CAST(`second_tier_units` AS STRING) AS second_tier_units,
               CAST(`overage_rate` AS STRING) AS overage_rate,
               `suspension_prorated`, `rating_subscription_id`, `fee_subscription_id`, `_origin`
        FROM {full('invoices')} WHERE `ns` = {NS_LIT}
        ORDER BY `tenant_id`, `id`
        """
    ).collect()
]

credit_rows = [
    r.asDict()
    for r in spark.sql(
        f"""
        SELECT `invoice_id`, `tenant_id`, `credit_note_id`, `seq_no`,
               date_format(`issued_on`, 'yyyy-MM-dd') AS issued_on,
               CAST(`bronze_remaining_amount` AS STRING) AS bronze_remaining_amount,
               CAST(`applied_by_other_invoices` AS STRING) AS applied_by_other_invoices,
               CAST(`remaining_before` AS STRING) AS remaining_before,
               CAST(`credit_running_before` AS STRING) AS credit_running_before,
               CAST(`applied_amount` AS STRING) AS applied_amount,
               CAST(`remaining_after` AS STRING) AS remaining_after,
               CAST(`credit_running_after` AS STRING) AS credit_running_after,
               `skipped_by_exit_when`
        FROM {full('credit_applications')} WHERE `ns` = {NS_LIT}
        ORDER BY `tenant_id`, `seq_no`
        """
    ).collect()
]

column_types = {
    f"{r[0]}.{r[1]}": r[2]
    for r in spark.sql(
        f"""
        SELECT table_name, column_name, full_data_type
        FROM {CATALOG}.information_schema.columns
        WHERE table_schema = {sql_str(SCHEMA)}
          AND table_name IN ('invoices', 'invoice_lines', 'credit_applications',
                             'quarantine_{UNIT}')
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
    "rating_input_policy": SPEC["rating_input_policy"],
    "drivers": {
        "source_rows": drivers_source,
        "loaded_rows": drivers_loaded,
        "quarantined_rows": drivers_quarantined,
    },
    "quarantine": {
        "accounting": accounting,
        "rows": quarantined_rows,
        "source_rows_rejected": quarantine_source_rows,
        "merge_identities_with_multiple_source_rows": _dup_identities,
        "identity_collapse_probe": quarantine_identity_probe,
        "rate_basis": QUAR_BASIS,
        "rate_source_rows": quar_source_rows,
        "rate_rejected_rows": quar_rejected_rows,
        "rate_pct": round(quar_pct, 4),
        "halt_threshold_pct": HALT_PCT,
        "by_source_table_and_reason": quar_by_reason,
        "persisted_before_halt_decision": True,
        "rejection_ledger": rejection_ledger,
    },
    "surviving_publications": surviving_publications,
    "target_counts": target_counts,
    "money": {
        "invoices": {
            "subtotal_total": money[0],
            "tax_total": money[1],
            "total_total": money[2],
            "subtotal_total_target_issue": money[3],
            "tax_total_target_issue": money[4],
            "total_total_target_issue": money[5],
            "total_total_source_migrated": money[6],
            "plan_fee_total": money[7],
            "overage_total": money[8],
            "credit_applied_total": money[9],
            "credit_offered_total": money[10],
        },
        "invoice_lines": {
            "line_amount_total": lines_money[0],
            "tax_line_total": lines_money[1],
            "credit_line_total": lines_money[2],
            "rows": int(lines_money[3]),
        },
        "credit_applications": {
            "applied_total": credit_money[0],
            "remaining_before_total": credit_money[1],
            "remaining_after_total": credit_money[2],
            "rows": int(credit_money[3]),
        },
        "quarantined_rows_alongside_money": quarantined_rows,
    },
    "checksums": checksums,
    "merge_metrics": metrics,
    "rebuild": {
        "scope": " ".join(REBUILD_SCOPE.split()),
        "rows_matched": int(stale_lines),
        "delete_commit_metrics": rebuild_delete_metrics,
        "lines_outside_scope_before": int(lines_outside_scope_before),
        "lines_outside_scope_after": int(lines_outside_scope_after),
        "credit_applications": credit_reconciliation,
        "reissue_update_columns": {
            name: TABLES[name].get("reissue_update_columns", [])
            + TABLES[name].get("explicit_state_columns", [])
            for name in ("invoices", "invoice_lines", "credit_applications")
        },
        "columns_held_at_first_issue": {
            name: TABLES[name].get("columns_held_at_first_issue", [])
            for name in ("invoices", "invoice_lines", "credit_applications")
        },
        "reissues_of_source_invoices": int(
            spark.sql(
                "SELECT count(*) FROM v_issued WHERE reissue_of_source_invoice"
            ).collect()[0][0]
        ),
    },
    "overflow_probe": overflow_probe,
    "column_types": column_types,
    "invoice_rows": invoice_rows,
    "invoice_lines": invoice_lines_projection,
    "preview_lines": preview_projection,
    "credit_applications": credit_rows,
    "credit_burn_sequence": burn_sample,
    "anomaly_detections": anomalies,
    "swallowed_exceptions": swallowed_paths,
}

out_path = f"{LANDING}/_runs/{BATCH_ID}.json"
dbutils.fs.mkdirs(f"{LANDING}/_runs")
dbutils.fs.put(out_path, json.dumps(summary, indent=1), overwrite=True)
print(f"run summary -> {out_path}")
dbutils.notebook.exit(json.dumps({"run_summary": out_path, "batch_id": BATCH_ID}))
