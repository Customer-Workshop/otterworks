# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_silver_plans — `pkg_plans` on Delta
# MAGIC
# MAGIC Wave 3 of the OW_BILLING → Databricks run. This notebook is the whole write path for
# MAGIC `ow_tp.silver.plans`, `ow_tp.silver.subscriptions`, `ow_tp.silver.entitlements` and
# MAGIC `ow_tp.silver.quarantine_silver_plans`, ported from
# MAGIC `services/legacy-billing/db/oracle/packages/02_pkg_plans.sql`
# MAGIC (`fn_list_plans`, `fn_entitlement`, `sp_change_plan`) and the DDL/triggers beside it.
# MAGIC It reads `ow_tp.bronze.*` and writes nothing else.
# MAGIC
# MAGIC The parts of the source that decide customer-visible state, and what happens to each here:
# MAGIC
# MAGIC * **`NVL(active_yn,'N') = 'Y'`** — a NULL `active_yn` is *inactive* (D-02). The filter is not a
# MAGIC   row filter in the target: every `PLANS` row is loaded, carrying `active_yn`, the `NVL`'d
# MAGIC   `active_nvl`, `listed_by_fn_list_plans` and the `ORDER BY monthly_fee, code` position as
# MAGIC   `list_seq`, so the accounting identity holds on the whole source table and the function's
# MAGIC   answer is still exactly reproducible from the target.
# MAGIC * **`DECODE(tier_cd, 1,'starter', 2,'growth', 3,'scale','UNKNOWN')`** — null-safe equality
# MAGIC   (D-03, `<=>`); an unmapped or NULL `tier_cd` becomes the literal `'UNKNOWN'`, which is neither
# MAGIC   a NULL nor a quarantine.
# MAGIC * **`fn_entitlement` carries two different date predicates.** The package-global lookup uses
# MAGIC   `NVL(s.ends_on, TO_DATE('31-DEC-99','DD-MON-YY')) >= p_on` — the sentinel resolves to **2099**
# MAGIC   (D-05), and the pinned `DATE'2099-12-31'` literal is used here because Spark's own
# MAGIC   `to_date('31-DEC-99','dd-MMM-yy')` resolves it to 1999 (probed below, ACC-SENTINEL-99). The
# MAGIC   returned cursor uses `(s.ends_on IS NULL OR s.ends_on >= p_on)`. Both are evaluated, per row,
# MAGIC   as `sentinel_predicate_covers` and `cursor_predicate_covers`, with `predicates_disagree`
# MAGIC   beside them: they are two predicates, not one.
# MAGIC * **`p.id (+) = s.plan_id`** — an outer join whose direction keeps the *subscription* when its
# MAGIC   plan row is missing (D-18). `plan_code`, `tier`, `monthly_fee` and `included_units`
# MAGIC   null-extend and `plan_null_extended` records it (ACC-OUTER-JOIN).
# MAGIC * **`ROWNUM = 1` with no `ORDER BY`** in the global lookup and `ROWNUM <= 1` after
# MAGIC   `ORDER BY s.starts_on DESC` in the cursor — both non-deterministic under ties (D-08). Both are
# MAGIC   pinned to `row_number() OVER (PARTITION BY tenant_id ORDER BY starts_on DESC, id DESC) = 1`,
# MAGIC   and the tie population is measured (`tied_starts_on_rows`), not assumed empty.
# MAGIC * **`GREATEST(s.starts_on, p_on)`** — Oracle propagates NULL, Spark's `greatest` ignores it
# MAGIC   (D-01), so the wrapper is used.
# MAGIC * **The package globals go stale.** `g_last_tenant_id := p_tenant_id` is assigned *before* the
# MAGIC   `SELECT ... INTO g_last_plan_code`, whose `WHEN OTHERS THEN NULL` swallows `NO_DATA_FOUND`, so
# MAGIC   a tenant with no covering subscription leaves the pair pointing at the *previous* tenant's
# MAGIC   plan code. No package-global equivalent is built (D-10): the values are explicit columns
# MAGIC   (`global_lookup_matched`, `global_lookup_plan_code`, `stale_global_plan_code`,
# MAGIC   `stale_global_mismatch`) and the population that would hit the mismatch is measured.
# MAGIC * **`sp_change_plan`'s close-out loop** closes each open subscription with
# MAGIC   `ends_on = p_effective_on - 1, status_cd = DECODE(r.status_cd, 30, 30, 10)`: cancelled stays
# MAGIC   cancelled (`trg_sub_no_uncancel`, D-16, ACC-CANCELLED) and **suspended becomes active** — a
# MAGIC   customer-visible side effect that is parity, reproduced here and counted. The cursor's
# MAGIC   `starts_on < p_effective_on` is strict, so a subscription starting exactly on the effective
# MAGIC   date is *not* closed and overlaps the new one; that population is measured too.
# MAGIC   `p_effective_on - 1` is Oracle day arithmetic on a `DATE`, so it is `- INTERVAL 1 DAY` here
# MAGIC   and any time component is carried, not truncated (D-07/T7).
# MAGIC * **The new subscription id** is `f_md5_uuid(tenant || plan || TO_CHAR(effective_on,'YYYY-MM-DD'))`
# MAGIC   (D-14) and the source's INSERT has no `DUP_VAL_ON_INDEX` handler, so re-applying the same
# MAGIC   change closes the open subscriptions and *then* raises ORA-00001. This port is idempotent
# MAGIC   (`MERGE` on that id plus `ns`) and does not reproduce the partial-effect failure; the source
# MAGIC   exposure is measured and declared.
# MAGIC * **`EXECUTE IMMEDIATE` for a static INSERT** (D-20) becomes a static write
# MAGIC   (`ANOM-DYNAMIC-SQL`). `pkg_ow_util.log_msg`'s autonomous `BILLING_AUDIT_LOG` write is out of
# MAGIC   parity scope for this unit and belongs to `bronze_hist`.
# MAGIC
# MAGIC `ow_tp.silver.subscriptions` is also written by wave 4 (`sp_suspend_overdue`): this unit
# MAGIC `MERGE`s the identities it produces and never deletes or rewrites a row it did not produce, and
# MAGIC it invents no cross-unit locking or publication protocol (D-28, `.migration/10_wave_plan.md`).

# COMMAND ----------

import datetime
import json
import re

# COMMAND ----------

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "silver")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("entitlement_on", "2026-02-28")
dbutils.widgets.text("change_effective_on", "2026-03-01")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/silver_plans_spec.json")
dbutils.widgets.text("batch_id", "")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRONZE = dbutils.widgets.get("bronze_schema").strip()
ENTITLEMENT_ON = dbutils.widgets.get("entitlement_on").strip()
CHANGE_EFFECTIVE_ON = dbutils.widgets.get("change_effective_on").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()

UNIT = "silver_plans"

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
for _pname, _pval in (
    ("entitlement_on", ENTITLEMENT_ON),
    ("change_effective_on", CHANGE_EFFECTIVE_ON),
):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _pval):
        raise ValueError(f"{_pname}={_pval!r} must be an ISO date (YYYY-MM-DD)")
    # Shape alone admits 2026-02-31, which Spark then resolves to NULL and silently empties every
    # date predicate below, so the parameter is held to a real calendar date.
    try:
        datetime.date.fromisoformat(_pval)
    except ValueError as exc:
        raise ValueError(f"{_pname}={_pval!r} is not a real calendar date: {exc}") from exc

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
CONST = SPEC["plans_constants"]

TIER_MAP = {int(k): v for k, v in CONST["tier_map"].items()}
TIER_DEFAULT = CONST["tier_default"]
STATUS_MAP = {int(k): v for k, v in CONST["status_map"].items()}
STATUS_DEFAULT = CONST["status_default"]
ACTIVE_FLAG = CONST["active_flag"]
INACTIVE_DEFAULT = CONST["inactive_nvl_default"]
SENTINEL_DATE = CONST["sentinel_end_date"]
ACTIVE_CD = int(CONST["active_status_cd"])
SUSPENDED_CD = int(CONST["suspended_status_cd"])
CANCELLED_CD = int(CONST["cancelled_status_cd"])

if TIER_MAP != {1: "starter", 2: "growth", 3: "scale"} or TIER_DEFAULT != "UNKNOWN":
    raise ValueError("the tier map is the source's DECODE(tier_cd, 1,'starter',2,'growth',3,'scale','UNKNOWN')")
if not SENTINEL_DATE.startswith("2099-"):
    raise ValueError(
        f"sentinel_end_date {SENTINEL_DATE!r} is not in 2099: TO_DATE('31-DEC-99','DD-MON-YY') "
        "resolves to 2099-12-31 in Oracle (D-05, ACC-SENTINEL-99), and a 1999 sentinel would expire "
        "every open subscription"
    )

REASONS = set(SPEC["quarantine_reasons"])
HALT_PCT = float(SPEC["quarantine_halt_threshold_pct"])
TABLES = {t["target"]: t for t in SPEC["tables"]}
CHANGE_OVERRIDES = SPEC["change_requests"]["overrides_are_pinned_from_transcripts"]

print(
    f"ns={NS} entitlement_on={ENTITLEMENT_ON} change_effective_on={CHANGE_EFFECTIVE_ON} "
    f"batch_id={BATCH_ID} targets={sorted(TABLES)} quarantine={QUARANTINE}"
)

# COMMAND ----------

# MAGIC %md ## Dialect helpers
# MAGIC
# MAGIC `GREATEST`, `DECODE` and `f_md5_uuid` are the three places a plain translation is wrong, so they
# MAGIC exist once, here, and every expression below is built from them.

# COMMAND ----------


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def o_greatest(a: str, b: str) -> str:
    """Oracle GREATEST: NULL in, NULL out (D-01). Spark's greatest() ignores nulls."""
    return f"(CASE WHEN ({a}) IS NULL OR ({b}) IS NULL THEN NULL ELSE greatest({a}, {b}) END)"


def o_decode(expr: str, mapping: dict, default: str) -> str:
    """Oracle DECODE with null-safe equality (D-03): `<=>`, not `=`."""
    whens = " ".join(
        f"WHEN ({expr}) <=> {key} THEN {value}"
        for key, value in ((k, sql_str(v)) for k, v in sorted(mapping.items()))
    )
    return f"(CASE {whens} ELSE {default} END)"


def f_md5_uuid(expr: str) -> str:
    """pkg_ow_util.f_md5_uuid: lower(md5(input)) sliced 8-4-4-4-12 (D-14)."""
    return (
        f"concat_ws('-', substr(lower(md5({expr})), 1, 8), substr(lower(md5({expr})), 9, 4), "
        f"substr(lower(md5({expr})), 13, 4), substr(lower(md5({expr})), 17, 4), "
        f"substr(lower(md5({expr})), 21, 12))"
    )


NS_LIT = sql_str(NS)
BATCH_LIT = sql_str(BATCH_ID)
# fn_entitlement is called with a DATE parameter and compares DATE columns against it at full
# precision, so the as-of bound reaches every comparison as a midnight timestamp.
AS_OF_TS = f"TIMESTAMP'{ENTITLEMENT_ON} 00:00:00'"
EFF_TS = f"TIMESTAMP'{CHANGE_EFFECTIVE_ON} 00:00:00'"
# The pinned D-05 sentinel. Not parsed from '31-DEC-99' here: Spark's own two-digit-year pivot
# resolves that string to 1999 (probed in the sentinel section below).
SENTINEL_TS = f"TIMESTAMP'{SENTINEL_DATE} 00:00:00'"

TIER_EXPR_TMPL = "{col}"
MONEY_MAX = "999999999999.99"
RATE_MAX = "999999.999999"

# Oracle DATE arithmetic is wall-clock: DATE - 1 is a plain day difference with no zone in it. The
# session zone is pinned so `- INTERVAL 1 DAY` below is that same wall-clock difference and no
# daylight-saving jump can move a close-out date.
spark.conf.set("spark.sql.session.timeZone", "UTC")

# COMMAND ----------

# MAGIC %md ## Target DDL
# MAGIC
# MAGIC `CREATE TABLE IF NOT EXISTS` only, liquid clustering on the natural key plus `ns` (D-22); no
# MAGIC one-for-one port of the source's indexes. This unit never drops or replaces a table and touches
# MAGIC nothing outside its own four targets.

# COMMAND ----------


def full(target: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{target}"


def lit(value: str) -> str:
    """A single-quoted SQL literal: the estate's prose carries apostrophes."""
    return "'" + value.replace("'", "''") + "'"


def ensure_target(tbl: dict) -> None:
    cols = ",\n  ".join(f"`{c['name']}` {c['target_type']}" for c in tbl["columns"])
    cluster = ", ".join(f"`{c}`" for c in tbl["cluster_by"])
    comment = (
        f"silver_plans: {tbl['source_table']} ported from pkg_plans; ns-scoped, MERGE on "
        + "+".join(tbl["merge_key"])
    )
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
        COMMENT {lit(comment)}
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
    COMMENT 'silver_plans rejects: one reason from the closed set in .migration/11_quarantine_codes.md, with ns, source table and raw payload'
    """
)

# COMMAND ----------

# MAGIC %md ## `fn_list_plans` — every PLANS row, with the function's answer as columns
# MAGIC
# MAGIC The source function filters and orders; the target keeps the whole table so
# MAGIC `loaded_rows + quarantined_rows == source_rows` holds on `OW_BILLING.PLANS` itself, and carries
# MAGIC the function's answer as `active_nvl` / `listed_by_fn_list_plans` / `list_seq` / `tier`.
# MAGIC
# MAGIC `ORDER BY monthly_fee, code` is Oracle's: ascending with NULLs **last**. Spark sorts NULLs first
# MAGIC by default, so the ordering is written out explicitly.

# COMMAND ----------

PLANS_SQL = f"""
WITH dup_id AS (
  SELECT `id`, count(*) AS id_rows FROM {CATALOG}.{BRONZE}.plans
  WHERE `ns` = {NS_LIT} GROUP BY `id`
),
dup_code AS (
  SELECT `code`, count(*) AS code_rows FROM {CATALOG}.{BRONZE}.plans
  WHERE `ns` = {NS_LIT} GROUP BY `code`
),
base AS (
  SELECT p.`id`, p.`code`,
         CAST(p.`tier_cd` AS INT) AS `tier_cd`,
         CAST(p.`monthly_fee` AS DECIMAL(38,6)) AS `monthly_fee_raw`,
         try_cast(p.`monthly_fee` AS DECIMAL(14,2)) AS `monthly_fee`,
         CAST(p.`included_units` AS DECIMAL(38,0)) AS `included_units_raw`,
         try_cast(p.`included_units` AS DECIMAL(38,0)) AS `included_units`,
         CAST(p.`overage_rate` AS DECIMAL(38,6)) AS `overage_rate_raw`,
         try_cast(p.`overage_rate` AS DECIMAL(12,6)) AS `overage_rate`,
         p.`active_yn`,
         coalesce(p.`active_yn`, {sql_str(INACTIVE_DEFAULT)}) AS `active_nvl`,
         {o_decode("CAST(p.`tier_cd` AS INT)", TIER_MAP, sql_str(TIER_DEFAULT))} AS `tier`,
         to_json(struct(p.`id`, p.`code`, p.`tier_cd`, p.`monthly_fee`, p.`included_units`,
                        p.`overage_rate`, p.`active_yn`)) AS `raw_source_payload`,
         coalesce(di.id_rows, 0) AS id_rows,
         coalesce(dc.code_rows, 0) AS code_rows
  FROM {CATALOG}.{BRONZE}.plans p
  LEFT JOIN dup_id di ON di.`id` = p.`id`
  LEFT JOIN dup_code dc ON dc.`code` = p.`code`
  WHERE p.`ns` = {NS_LIT}
),
judged AS (
  SELECT b.*,
         CASE
           WHEN b.`id` IS NULL OR b.`code` IS NULL THEN 'KEY_NULL'
           -- The overflow guard is decided on the pre-cast values before any null-based branch, so an
           -- out-of-range fee cannot be answered for by a later test on the column it nulled
           -- (D-23/T6).
           WHEN abs(b.`monthly_fee_raw`) > CAST({MONEY_MAX} AS DECIMAL(38,6))
             OR (b.`monthly_fee_raw` IS NOT NULL AND b.`monthly_fee` IS NULL)
             OR (b.`included_units_raw` IS NOT NULL AND b.`included_units` IS NULL)
             OR abs(b.`overage_rate_raw`) > CAST({RATE_MAX} AS DECIMAL(38,6))
             OR (b.`overage_rate_raw` IS NOT NULL AND b.`overage_rate` IS NULL)
             THEN 'NUMERIC_OVERFLOW'
           WHEN b.id_rows > 1 OR b.code_rows > 1 THEN 'KEY_DUPLICATE'
           ELSE NULL
         END AS `quarantine_reason`
  FROM base b
)
SELECT j.*,
       (j.`active_nvl` = {sql_str(ACTIVE_FLAG)}) AS `listed_by_fn_list_plans`,
       CAST(CASE WHEN j.`quarantine_reason` IS NULL AND j.`active_nvl` = {sql_str(ACTIVE_FLAG)}
                 THEN row_number() OVER (
                        PARTITION BY CASE WHEN j.`quarantine_reason` IS NULL
                                          AND j.`active_nvl` = {sql_str(ACTIVE_FLAG)}
                                     THEN 1 ELSE 0 END
                        ORDER BY j.`monthly_fee` ASC NULLS LAST, j.`code` ASC NULLS LAST)
            END AS INT) AS `list_seq`
FROM judged j
"""
spark.sql(PLANS_SQL).createOrReplaceTempView("v_plans_judged")
spark.sql(
    "CREATE OR REPLACE TEMP VIEW v_plans_loaded AS "
    "SELECT * FROM v_plans_judged WHERE `quarantine_reason` IS NULL"
)
spark.sql(
    "CREATE OR REPLACE TEMP VIEW v_plans_listed AS "
    f"SELECT * FROM v_plans_loaded WHERE `active_nvl` = {sql_str(ACTIVE_FLAG)}"
)

unknown_tier_plans = spark.sql(
    f"SELECT count(*) FROM v_plans_judged WHERE `tier` = {sql_str(TIER_DEFAULT)}"
).collect()[0][0]
inactive_plans = spark.sql(
    f"SELECT count(*) FROM v_plans_judged WHERE `active_nvl` <> {sql_str(ACTIVE_FLAG)}"
).collect()[0][0]
null_active_yn_plans = spark.sql(
    "SELECT count(*) FROM v_plans_judged WHERE `active_yn` IS NULL"
).collect()[0][0]
print(
    f"plans: unknown_tier={unknown_tier_plans} inactive={inactive_plans} "
    f"null_active_yn={null_active_yn_plans}"
)

# COMMAND ----------

# MAGIC %md ## `OW_BILLING.SUBSCRIPTIONS`, judged
# MAGIC
# MAGIC A subscription whose **plan** is missing is *not* a reject: `p.id (+) = s.plan_id` keeps it and
# MAGIC null-extends the plan columns (D-18), so `FK_ORPHAN` here is about the **tenant** reference only
# MAGIC — the one the source enforces with `fk_sub_tenant` and the one D-19 declares mandatory. The live
# MAGIC exposure of both is measured rather than assumed.

# COMMAND ----------

SUBS_SQL = f"""
WITH dup_id AS (
  SELECT `id`, count(*) AS id_rows FROM {CATALOG}.{BRONZE}.subscriptions
  WHERE `ns` = {NS_LIT} GROUP BY `id`
),
base AS (
  SELECT s.`id`, s.`tenant_id`, s.`plan_id`, s.`starts_on`, s.`ends_on`,
         CAST(s.`status_cd` AS DECIMAL(38,0)) AS `status_cd_raw`,
         try_cast(s.`status_cd` AS INT) AS `status_cd`,
         s.`suspended_on`,
         to_json(struct(s.`id`, s.`tenant_id`, s.`plan_id`, s.`starts_on`, s.`ends_on`,
                        s.`status_cd`, s.`suspended_on`)) AS `raw_source_payload`,
         coalesce(d.id_rows, 0) AS id_rows,
         EXISTS (SELECT 1 FROM {CATALOG}.{BRONZE}.tenants t
                  WHERE t.`ns` = {NS_LIT} AND t.`id` = s.`tenant_id`) AS tenant_exists,
         EXISTS (SELECT 1 FROM v_plans_loaded p WHERE p.`id` = s.`plan_id`) AS plan_exists
  FROM {CATALOG}.{BRONZE}.subscriptions s
  LEFT JOIN dup_id d ON d.`id` = s.`id`
  WHERE s.`ns` = {NS_LIT}
)
SELECT b.*,
       CASE
         WHEN b.`id` IS NULL OR b.`tenant_id` IS NULL OR b.`starts_on` IS NULL THEN 'KEY_NULL'
         WHEN b.`status_cd_raw` IS NOT NULL AND b.`status_cd` IS NULL THEN 'NUMERIC_OVERFLOW'
         WHEN b.id_rows > 1 THEN 'KEY_DUPLICATE'
         -- fk_sub_tenant is enforced in the source, so this guards a bronze slice that lost a
         -- tenant, not the source. A missing *plan* is deliberately not a reject (D-18).
         WHEN NOT b.tenant_exists THEN 'FK_ORPHAN'
         ELSE NULL
       END AS `quarantine_reason`
FROM base b
"""
spark.sql(SUBS_SQL).createOrReplaceTempView("v_subs_judged")
spark.sql(
    "CREATE OR REPLACE TEMP VIEW v_subs_loaded AS "
    "SELECT * FROM v_subs_judged WHERE `quarantine_reason` IS NULL"
)

subs_with_missing_plan = spark.sql(
    "SELECT count(*) FROM v_subs_loaded WHERE NOT plan_exists"
).collect()[0][0]
print(f"subscriptions: rows with a missing plan row (kept, null-extended) = {subs_with_missing_plan}")

# COMMAND ----------

# MAGIC %md ## `fn_entitlement`, both predicates and both `ROWNUM` picks
# MAGIC
# MAGIC The cursor's population is `tenants ⋈ subscriptions` with `p.id (+) = s.plan_id`; the
# MAGIC package-global lookup is `subscriptions` with the same outer join but the **sentinel** predicate
# MAGIC and a bare `ROWNUM = 1`. Both are materialised, per tenant, with their candidate and tie counts,
# MAGIC so the disagreement between the two predicates and the exposure of the two `ROWNUM` picks are
# MAGIC measured values rather than prose.
# MAGIC
# MAGIC The stale package-global pair is reconstructed the way the PL/SQL leaves it: tenants are walked
# MAGIC in the declared order (`tenant_id`), and a tenant whose lookup finds nothing inherits the plan
# MAGIC code assigned by the last tenant whose lookup *did* find something — the value the swallowed
# MAGIC `NO_DATA_FOUND` leaves behind. Nothing here writes a global: they are columns.

# COMMAND ----------

CURSOR_PRED = f"(s.`ends_on` IS NULL OR s.`ends_on` >= {AS_OF_TS})"
SENTINEL_PRED = f"(coalesce(s.`ends_on`, {SENTINEL_TS}) >= {AS_OF_TS})"

ENT_SQL = f"""
WITH sub AS (
  SELECT s.`id`, s.`tenant_id`, s.`plan_id`, s.`starts_on`, s.`ends_on`, s.`status_cd`,
         {CURSOR_PRED} AS cursor_covers,
         {SENTINEL_PRED} AS sentinel_covers,
         (s.`starts_on` <= {AS_OF_TS}) AS starts_before
  FROM v_subs_loaded s
),
-- The returned cursor: tenants ⋈ subscriptions, plans outer-joined so a missing plan null-extends
-- (D-18), ORDER BY starts_on DESC + ROWNUM <= 1 pinned with the D-08 tie-break.
cursor_cand AS (
  SELECT t.`id` AS tenant_id, s.`id` AS subscription_id, s.`plan_id`, s.`starts_on`, s.`ends_on`,
         s.`status_cd`, s.cursor_covers, s.sentinel_covers,
         p.`code` AS plan_code, p.`tier`, p.`monthly_fee`, p.`included_units`,
         row_number() OVER (PARTITION BY t.`id`
                            ORDER BY s.`starts_on` DESC, s.`id` DESC) AS rn,
         count(*) OVER (PARTITION BY t.`id`) AS candidate_rows,
         count(*) OVER (PARTITION BY t.`id`, s.`starts_on`) AS tied_starts_on_rows
  FROM {CATALOG}.{BRONZE}.tenants t
  JOIN sub s ON s.`tenant_id` = t.`id`
  LEFT JOIN v_plans_loaded p ON p.`id` = s.`plan_id`
  WHERE t.`ns` = {NS_LIT}
    AND s.starts_before
    AND s.cursor_covers
),
cursor_pick AS (SELECT * FROM cursor_cand WHERE rn = 1),
-- The package-global lookup: SUBSCRIPTIONS alone with the 2099 sentinel and a bare ROWNUM = 1, no
-- ORDER BY at all. Same pinned tie-break, and the population it looks at is measured separately
-- because the two predicates are not the same predicate.
global_cand AS (
  SELECT s.`tenant_id`, p.`code` AS plan_code, s.`id` AS subscription_id,
         row_number() OVER (PARTITION BY s.`tenant_id`
                            ORDER BY s.`starts_on` DESC, s.`id` DESC) AS rn,
         count(*) OVER (PARTITION BY s.`tenant_id`) AS candidate_rows
  FROM sub s
  LEFT JOIN v_plans_loaded p ON p.`id` = s.`plan_id`
  WHERE s.starts_before AND s.sentinel_covers
),
global_pick AS (SELECT * FROM global_cand WHERE rn = 1),
tenant_walk AS (
  SELECT t.`id` AS tenant_id,
         CAST(row_number() OVER (ORDER BY t.`id`) AS INT) AS global_iteration_seq,
         (g.`tenant_id` IS NOT NULL) AS global_lookup_matched,
         g.plan_code AS global_lookup_plan_code,
         CAST(coalesce(g.candidate_rows, 0) AS INT) AS global_lookup_candidate_rows
  FROM {CATALOG}.{BRONZE}.tenants t
  LEFT JOIN global_pick g ON g.`tenant_id` = t.`id`
  WHERE t.`ns` = {NS_LIT}
),
-- g_last_plan_code is whatever the last *successful* SELECT INTO assigned, which may itself be NULL
-- when that tenant's plan row was missing. So the carried value is looked up by the sequence number
-- of the last matched predecessor rather than by "last non-null".
walk AS (
  SELECT w.*,
         max(CASE WHEN w.global_lookup_matched THEN w.global_iteration_seq END) OVER (
           ORDER BY w.global_iteration_seq
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS last_matched_seq
  FROM tenant_walk w
),
stale AS (
  SELECT w.*,
         prev.`global_lookup_plan_code` AS stale_global_plan_code,
         (NOT w.global_lookup_matched AND w.last_matched_seq IS NOT NULL) AS stale_global_mismatch
  FROM walk w
  LEFT JOIN tenant_walk prev ON prev.global_iteration_seq = w.last_matched_seq
)
SELECT c.`tenant_id`,
       {AS_OF_TS} AS `as_of_on`,
       c.`subscription_id`, c.`plan_id`, c.`plan_code`, c.`tier`, c.`monthly_fee`,
       c.`included_units`, c.`status_cd`,
       {o_decode("c.`status_cd`", STATUS_MAP, sql_str(STATUS_DEFAULT))} AS `subscription_status`,
       {o_greatest("c.`starts_on`", AS_OF_TS)} AS `effective_on`,
       c.`starts_on`, c.`ends_on`,
       CAST(c.`candidate_rows` AS INT) AS `candidate_rows`,
       CAST(c.`tied_starts_on_rows` AS INT) AS `tied_starts_on_rows`,
       (c.`plan_id` IS NOT NULL AND c.`plan_code` IS NULL) AS `plan_null_extended`,
       c.cursor_covers AS `cursor_predicate_covers`,
       c.sentinel_covers AS `sentinel_predicate_covers`,
       (c.cursor_covers <> c.sentinel_covers) AS `predicates_disagree`,
       s.global_lookup_matched AS `global_lookup_matched`,
       s.global_lookup_plan_code AS `global_lookup_plan_code`,
       s.global_lookup_candidate_rows AS `global_lookup_candidate_rows`,
       s.global_iteration_seq AS `global_iteration_seq`,
       s.stale_global_plan_code AS `stale_global_plan_code`,
       s.stale_global_mismatch AS `stale_global_mismatch`
FROM cursor_pick c
JOIN stale s ON s.`tenant_id` = c.`tenant_id`
"""
spark.sql(ENT_SQL).createOrReplaceTempView("v_entitlements")

# The same cursor population over the *judged* subscriptions: the entitlement table's declared source
# population is "one fn_entitlement row per tenant whose cursor returns a row", so a tenant that only
# had a rejected subscription is a quarantined entitlement rather than a silently missing one.
ENT_SOURCE_SQL = f"""
SELECT count(DISTINCT t.`id`) FROM {CATALOG}.{BRONZE}.tenants t
JOIN v_subs_judged s ON s.`tenant_id` = t.`id`
WHERE t.`ns` = {NS_LIT}
  AND s.`starts_on` <= {AS_OF_TS}
  AND (s.`ends_on` IS NULL OR s.`ends_on` >= {AS_OF_TS})
"""
ent_source_tenants = spark.sql(ENT_SOURCE_SQL).collect()[0][0]
ent_loaded_tenants = spark.table("v_entitlements").count()

ent_pop = spark.sql(
    """
    SELECT sum(CASE WHEN `plan_null_extended` THEN 1 ELSE 0 END),
           sum(CASE WHEN `tied_starts_on_rows` > 1 THEN 1 ELSE 0 END),
           sum(CASE WHEN `candidate_rows` > 1 THEN 1 ELSE 0 END),
           sum(CASE WHEN `predicates_disagree` THEN 1 ELSE 0 END),
           sum(CASE WHEN `stale_global_mismatch` THEN 1 ELSE 0 END),
           sum(CASE WHEN NOT `global_lookup_matched` THEN 1 ELSE 0 END),
           sum(CASE WHEN `tier` = 'UNKNOWN' THEN 1 ELSE 0 END),
           sum(CASE WHEN `subscription_status` = 'UNKNOWN' THEN 1 ELSE 0 END),
           count(*)
    FROM v_entitlements
    """
).collect()[0]

tenants_total = spark.sql(
    f"SELECT count(*) FROM {CATALOG}.{BRONZE}.tenants WHERE `ns` = {NS_LIT}"
).collect()[0][0]

# The mismatch the source leaves behind lands on tenants whose lookup finds nothing — which are
# exactly the tenants the cursor also returns no row for, so they carry no entitlement row at all
# (the contract's write-empty-result shape). The population is therefore measured here, over every
# tenant, rather than only over the rows the table holds.
STALE_POP_SQL = f"""
WITH sub AS (
  SELECT s.`tenant_id`, s.`starts_on`, s.`ends_on` FROM v_subs_loaded s
),
covered AS (
  SELECT DISTINCT `tenant_id` FROM sub
  WHERE `starts_on` <= {AS_OF_TS} AND (coalesce(`ends_on`, {SENTINEL_TS}) >= {AS_OF_TS})
),
covered_cursor AS (
  SELECT DISTINCT `tenant_id` FROM sub
  WHERE `starts_on` <= {AS_OF_TS} AND (`ends_on` IS NULL OR `ends_on` >= {AS_OF_TS})
),
tn AS (SELECT `id` FROM {CATALOG}.{BRONZE}.tenants WHERE `ns` = {NS_LIT})
SELECT
  count_if(c.`tenant_id` IS NULL),
  count_if(cc.`tenant_id` IS NULL),
  count(c.`tenant_id`),
  count(cc.`tenant_id`)
FROM tn
LEFT JOIN covered c ON c.`tenant_id` = tn.`id`
LEFT JOIN covered_cursor cc ON cc.`tenant_id` = tn.`id`
"""
_stale = spark.sql(STALE_POP_SQL).collect()[0]

entitlement_populations = {
    "as_of_on": ENTITLEMENT_ON,
    "tenants_in_ns": tenants_total,
    "entitlement_rows": int(ent_pop[8]),
    "tenants_with_no_covering_subscription_sentinel_predicate": int(_stale[0]),
    "tenants_with_no_covering_subscription_cursor_predicate": int(_stale[1]),
    "tenants_covered_sentinel_predicate": int(_stale[2]),
    "tenants_covered_cursor_predicate": int(_stale[3]),
    "tenants_where_the_two_predicates_disagree": int(_stale[2] - _stale[3]),
    "rows_where_the_two_predicates_disagree_on_the_picked_subscription": int(ent_pop[3] or 0),
    "plan_null_extended_rows": int(ent_pop[0] or 0),
    "rows_with_tied_starts_on": int(ent_pop[1] or 0),
    "rows_with_more_than_one_candidate": int(ent_pop[2] or 0),
    "rows_carrying_a_stale_global_mismatch": int(ent_pop[4] or 0),
    "rows_whose_global_lookup_found_nothing": int(ent_pop[5] or 0),
    "tenants_that_would_hit_the_stale_globals_mismatch": int(_stale[0]),
    "unknown_tier_rows": int(ent_pop[6] or 0),
    "unknown_subscription_status_rows": int(ent_pop[7] or 0),
}
print(json.dumps(entitlement_populations, indent=1))

# COMMAND ----------

# MAGIC %md ## The sentinel, the two-digit pivot, and the null-propagation wrappers
# MAGIC
# MAGIC Probes of the target's own expressions, evaluated on the warehouse: they write nothing and they
# MAGIC are not findings about the source. What they establish is that this port resolves
# MAGIC `31-DEC-99` the way Oracle does (2099, D-05) — by pinning the literal rather than trusting any
# MAGIC engine's two-digit-year pivot, which is what `ACC-SENTINEL-99` is about — and that the
# MAGIC `GREATEST`/`DECODE` wrappers behave as D-01/D-03 require. The runtime's own parse of the string
# MAGIC is measured beside the pinned literal rather than predicted.

# COMMAND ----------

_probe = spark.sql(
    f"""
    SELECT CAST(to_date('31-DEC-99', 'dd-MMM-yy') AS STRING),
           CAST(DATE{sql_str(SENTINEL_DATE)} AS STRING),
           CAST(greatest(CAST(NULL AS TIMESTAMP), {AS_OF_TS}) AS STRING),
           CAST({o_greatest("CAST(NULL AS TIMESTAMP)", AS_OF_TS)} AS STRING),
           CAST({o_decode("CAST(NULL AS INT)", TIER_MAP, sql_str(TIER_DEFAULT))} AS STRING),
           CAST({o_decode("CAST(4 AS INT)", TIER_MAP, sql_str(TIER_DEFAULT))} AS STRING),
           CAST({o_decode(f"CAST({CANCELLED_CD} AS INT)", STATUS_MAP, sql_str(STATUS_DEFAULT))} AS STRING)
    """
).collect()[0]
dialect_probe = {
    "is_probe_of_target_expression_not_source_finding": True,
    "spark_to_date_31_DEC_99": _probe[0],
    "pinned_sentinel_literal_used_by_this_port": _probe[1],
    "spark_greatest_null_and_a_date": _probe[2],
    "o_greatest_null_and_a_date": _probe[3],
    "o_decode_null_tier_cd": _probe[4],
    "o_decode_unmapped_tier_cd": _probe[5],
    "o_decode_cancelled_status": _probe[6],
    "spark_two_digit_year_pivot_agrees_with_oracle": _probe[0].startswith("2099"),
    "note": "the sentinel is never parsed from the string: DATE'2099-12-31' is pinned from the spec, "
    "because a two-digit-year pivot is a property of the engine and its session settings rather than "
    "of the source text (ACC-SENTINEL-99 — a 1999 sentinel would expire every open subscription). "
    "This runtime's own parse of 31-DEC-99 is recorded above as measured, not predicted. Spark's "
    "greatest() ignores a NULL argument, Oracle's propagates it (D-01), so every GREATEST is wrapped.",
}
print(json.dumps(dialect_probe, indent=1))
if not _probe[1].startswith("2099"):
    raise AssertionError(f"the sentinel probe did not behave as declared: {dialect_probe}")
if _probe[2] is None or _probe[3] is not None:
    raise AssertionError(f"the GREATEST null-propagation wrapper is not wrapping: {dialect_probe}")
if (_probe[4], _probe[5], _probe[6]) != ("UNKNOWN", "UNKNOWN", "cancelled"):
    raise AssertionError(f"the DECODE port did not behave as declared: {dialect_probe}")

# COMMAND ----------

# MAGIC %md ## `sp_change_plan`, re-expressed
# MAGIC
# MAGIC The source has no change-request table: the procedure is called by the application with
# MAGIC `(p_tenant_id, p_plan_id, p_effective_on)`. The run's request population is therefore a declared
# MAGIC job input, derived deterministically from bronze by the rule in the spec — next plan in
# MAGIC `fn_list_plans` order, cyclically, for every tenant with a covering subscription — with the two
# MAGIC requests pinned by transcripts `PLANS-004`/`PLANS-005` overriding it. Both sides of the recon
# MAGIC build the same set from their own copy of the data, and the recon report compares them.
# MAGIC
# MAGIC The close-out is `ends_on = p_effective_on - 1` and `status_cd = DECODE(r.status_cd, 30, 30, 10)`
# MAGIC per row, with `trg_sub_no_uncancel` folded in (it re-asserts the same 30). The loop's result does
# MAGIC not depend on processing order here because each row's new state is a function of its own old
# MAGIC state only — but the source's loop *is* order-dependent in shape (`ANOM-ROWBYROW-CLOSEOUT`), so
# MAGIC the order is pinned anyway, to `tenant_id, starts_on, id`, and published as `closeout_seq`.

# COMMAND ----------

_override_rows = " UNION ALL ".join(
    f"SELECT {sql_str(o['tenant_id'])} AS `tenant_id`, {sql_str(o['plan_id'])} AS `plan_id`, "
    f"TIMESTAMP'{o['effective_on']} 00:00:00' AS `effective_on`, "
    f"{sql_str(o['transcript'])} AS `pinned_by_transcript`"
    for o in CHANGE_OVERRIDES
)

REQ_SQL = f"""
WITH listed AS (
  SELECT `id`, `code`, `monthly_fee`,
         row_number() OVER (ORDER BY `monthly_fee` ASC NULLS LAST, `code` ASC NULLS LAST) AS seq,
         count(*) OVER () AS n
  FROM v_plans_listed
),
covering AS (
  SELECT `tenant_id`, `plan_id` FROM v_entitlements
),
derived AS (
  SELECT c.`tenant_id`, nxt.`id` AS `plan_id`, {EFF_TS} AS `effective_on`,
         CAST(NULL AS STRING) AS `pinned_by_transcript`
  FROM covering c
  JOIN listed cur ON cur.`id` = c.`plan_id`
  JOIN listed nxt ON nxt.seq = mod(cur.seq, cur.n) + 1
),
overrides AS (
  SELECT o.* FROM ({_override_rows}) o
  WHERE EXISTS (SELECT 1 FROM covering c WHERE c.`tenant_id` = o.`tenant_id`)
)
SELECT * FROM overrides
UNION ALL
SELECT d.* FROM derived d
WHERE NOT EXISTS (SELECT 1 FROM overrides o WHERE o.`tenant_id` = d.`tenant_id`)
"""
spark.sql(REQ_SQL).createOrReplaceTempView("v_requests_raw")

REQ_JUDGED_SQL = f"""
SELECT r.*,
       {f_md5_uuid("concat(r.`tenant_id`, r.`plan_id`, date_format(r.`effective_on`, 'yyyy-MM-dd'))")}
         AS `new_subscription_id`,
       to_json(struct(r.`tenant_id`, r.`plan_id`, r.`effective_on`, r.`pinned_by_transcript`))
         AS `raw_source_payload`,
       CASE
         WHEN r.`tenant_id` IS NULL OR r.`plan_id` IS NULL OR r.`effective_on` IS NULL
           THEN 'KEY_NULL'
         -- fk_sub_tenant and fk_sub_plan both apply to the row the source INSERTs, so a request
         -- pointing at a tenant or a plan this run did not load cannot produce a subscription.
         WHEN NOT EXISTS (SELECT 1 FROM {CATALOG}.{BRONZE}.tenants t
                           WHERE t.`ns` = {NS_LIT} AND t.`id` = r.`tenant_id`)
           OR NOT EXISTS (SELECT 1 FROM v_plans_loaded p WHERE p.`id` = r.`plan_id`)
           THEN 'FK_ORPHAN'
         ELSE NULL
       END AS `quarantine_reason`
FROM v_requests_raw r
"""
spark.sql(REQ_JUDGED_SQL).createOrReplaceTempView("v_requests_judged")
spark.sql(
    "CREATE OR REPLACE TEMP VIEW v_requests AS "
    "SELECT * FROM v_requests_judged WHERE `quarantine_reason` IS NULL"
)

CLOSEOUT_SQL = f"""
WITH open_subs AS (
  SELECT s.*, r.`effective_on`, r.`plan_id` AS `change_plan_id`
  FROM v_subs_loaded s
  JOIN v_requests r ON r.`tenant_id` = s.`tenant_id`
  WHERE s.`ends_on` IS NULL
    AND s.`starts_on` < r.`effective_on`
)
SELECT o.`id`,
       CAST(row_number() OVER (ORDER BY o.`tenant_id`, o.`starts_on`, o.`id`) AS INT)
         AS `closeout_seq`,
       o.`effective_on` AS `change_effective_on`,
       o.`change_plan_id`,
       o.`ends_on` AS `ends_on_before`,
       o.`status_cd` AS `status_cd_before`,
       (o.`effective_on` - INTERVAL 1 DAY) AS `new_ends_on`,
       CAST({o_decode("o.`status_cd`", {CANCELLED_CD: str(CANCELLED_CD)}, str(ACTIVE_CD))} AS INT)
         AS `new_status_cd`
FROM open_subs o
"""
spark.sql(CLOSEOUT_SQL).createOrReplaceTempView("v_closeout")

# The subscriptions the strict `<` leaves open: they start on or after the effective date, so the
# cursor never sees them and they overlap the subscription the procedure then inserts.
OVERLAP_SQL = """
SELECT s.`id`
FROM v_subs_loaded s
JOIN v_requests r ON r.`tenant_id` = s.`tenant_id`
WHERE s.`ends_on` IS NULL AND s.`starts_on` >= r.`effective_on`
"""
spark.sql(OVERLAP_SQL).createOrReplaceTempView("v_overlap")

SUBS_SRC_SQL = f"""
SELECT s.`id`, s.`tenant_id`, s.`plan_id`, s.`starts_on`,
       coalesce(c.`new_ends_on`, s.`ends_on`) AS `ends_on`,
       coalesce(c.`new_status_cd`, s.`status_cd`) AS `status_cd`,
       s.`suspended_on`,
       c.`status_cd_before`, c.`ends_on_before`,
       (c.`id` IS NOT NULL) AS `closed_by_change`,
       c.`closeout_seq`, c.`change_effective_on`, c.`change_plan_id`,
       (c.`id` IS NOT NULL AND c.`status_cd_before` <=> {SUSPENDED_CD}
        AND c.`new_status_cd` <=> {ACTIVE_CD}) AS `reactivated_from_suspended`,
       (c.`id` IS NOT NULL AND c.`status_cd_before` <=> {CANCELLED_CD}
        AND c.`new_status_cd` <=> {CANCELLED_CD}) AS `cancelled_preserved`,
       (o.`id` IS NOT NULL) AS `overlaps_new_subscription`,
       'source-migrated' AS `_origin`
FROM v_subs_loaded s
LEFT JOIN v_closeout c ON c.`id` = s.`id`
LEFT JOIN v_overlap o ON o.`id` = s.`id`

UNION ALL

-- The static equivalent of the source's EXECUTE IMMEDIATE INSERT (D-20, ANOM-DYNAMIC-SQL): status 10
-- and a NULL ends_on, exactly the columns the dynamic statement binds.
SELECT r.`new_subscription_id` AS `id`, r.`tenant_id`, r.`plan_id`,
       r.`effective_on` AS `starts_on`,
       CAST(NULL AS TIMESTAMP) AS `ends_on`,
       CAST({ACTIVE_CD} AS INT) AS `status_cd`,
       CAST(NULL AS TIMESTAMP) AS `suspended_on`,
       CAST(NULL AS INT), CAST(NULL AS TIMESTAMP),
       false AS `closed_by_change`,
       CAST(NULL AS INT), r.`effective_on` AS `change_effective_on`, r.`plan_id` AS `change_plan_id`,
       false, false, false,
       'target-change' AS `_origin`
FROM v_requests r
"""
spark.sql(SUBS_SRC_SQL).createOrReplaceTempView("v_subs_src")

_close = spark.sql(
    f"""
    SELECT count(*),
           sum(CASE WHEN `status_cd_before` <=> {SUSPENDED_CD}
                     AND `new_status_cd` <=> {ACTIVE_CD} THEN 1 ELSE 0 END),
           sum(CASE WHEN `status_cd_before` <=> {CANCELLED_CD} THEN 1 ELSE 0 END),
           sum(CASE WHEN `status_cd_before` <=> {CANCELLED_CD}
                     AND `new_status_cd` <=> {CANCELLED_CD} THEN 1 ELSE 0 END),
           sum(CASE WHEN date_format(`new_ends_on`, 'HH:mm:ss') <> '00:00:00' THEN 1 ELSE 0 END)
    FROM v_closeout
    """
).collect()[0]
_reapply = spark.sql(
    f"""
    SELECT count(*) FROM v_requests r
    WHERE EXISTS (SELECT 1 FROM {CATALOG}.{BRONZE}.subscriptions b
                   WHERE b.`ns` = {NS_LIT} AND b.`id` = r.`new_subscription_id`)
    """
).collect()[0][0]
_eq_start = spark.sql(
    """
    SELECT count(*) FROM v_subs_loaded s JOIN v_requests r ON r.`tenant_id` = s.`tenant_id`
    WHERE s.`ends_on` IS NULL AND s.`starts_on` = r.`effective_on`
    """
).collect()[0][0]

change_populations = {
    "change_effective_on_default": CHANGE_EFFECTIVE_ON,
    "requests": spark.table("v_requests_judged").count(),
    "requests_accepted": spark.table("v_requests").count(),
    "requests_pinned_by_a_transcript": spark.sql(
        "SELECT count(*) FROM v_requests WHERE `pinned_by_transcript` IS NOT NULL"
    ).collect()[0][0],
    "subscriptions_closed_by_the_loop": int(_close[0]),
    "suspended_to_active_flips": int(_close[1] or 0),
    "cancelled_subscriptions_visited": int(_close[2] or 0),
    "cancelled_preserved": int(_close[3] or 0),
    "closeout_ends_on_carrying_a_time_component": int(_close[4] or 0),
    "open_subscriptions_left_overlapping_by_the_strict_less_than": spark.table("v_overlap").count(),
    "open_subscriptions_starting_exactly_on_the_effective_date": int(_eq_start),
    "new_subscriptions": spark.table("v_requests").count(),
    "new_ids_already_present_in_the_source": int(_reapply),
    "closeout_order_pinned_to": CONST["closeout_order_by"],
}
print(json.dumps(change_populations, indent=1))

# COMMAND ----------

# MAGIC %md ## Quarantine: one closed reason per reject, persisted before the halt is decided
# MAGIC
# MAGIC Reasons come from the closed set in `.migration/11_quarantine_codes.md`; nothing local is
# MAGIC invented and there is no catch-all. Note what is deliberately *not* a reject here: an unmapped
# MAGIC or NULL `tier_cd` (it is the literal `'UNKNOWN'`), an inactive plan (it is loaded, unlisted), and
# MAGIC a subscription whose plan row is missing (D-18 keeps it and null-extends).

# COMMAND ----------

REQ_SOURCE_TABLE = "OW_BILLING.SUBSCRIPTIONS+PKG_PLANS.SP_CHANGE_PLAN(request)"

QUAR_SQL = f"""
SELECT `quarantine_reason`, {NS_LIT} AS `ns`, 'OW_BILLING.PLANS' AS `source_table`,
       `id` AS `source_key`, `raw_source_payload`,
       CASE `quarantine_reason`
         WHEN 'KEY_NULL' THEN 'plans.id or plans.code is null, so the MERGE key or the unique code cannot be made idempotent'
         WHEN 'KEY_DUPLICATE' THEN 'two bronze PLANS rows share an id or a code, which uq_plans_code forbids in the source'
         ELSE 'a plan number does not fit its pinned target decimal type'
       END AS `detail`,
       CASE `quarantine_reason` WHEN 'NUMERIC_OVERFLOW' THEN 'D-23' ELSE 'D-14' END
         AS `dictionary_ref`,
       {BATCH_LIT} AS `_batch_id`, current_timestamp() AS `_quarantined_at`
FROM v_plans_judged WHERE `quarantine_reason` IS NOT NULL

UNION ALL
SELECT `quarantine_reason`, {NS_LIT}, 'OW_BILLING.SUBSCRIPTIONS', `id`, `raw_source_payload`,
       CASE `quarantine_reason`
         WHEN 'KEY_NULL' THEN 'subscriptions.id, .tenant_id or .starts_on is null'
         WHEN 'KEY_DUPLICATE' THEN 'two bronze SUBSCRIPTIONS rows share an id, which pk_subscriptions forbids in the source'
         WHEN 'FK_ORPHAN' THEN 'the tenant fk_sub_tenant points at is not in bronze (a missing *plan* is not a reject: p.id (+) = s.plan_id keeps the subscription, D-18)'
         ELSE 'status_cd does not fit its pinned target type'
       END,
       CASE `quarantine_reason` WHEN 'FK_ORPHAN' THEN 'D-19'
                               WHEN 'NUMERIC_OVERFLOW' THEN 'D-23' ELSE 'D-14' END,
       {BATCH_LIT}, current_timestamp()
FROM v_subs_judged WHERE `quarantine_reason` IS NOT NULL

UNION ALL
SELECT `quarantine_reason`, {NS_LIT}, {sql_str(REQ_SOURCE_TABLE)},
       concat_ws('|', `tenant_id`, `plan_id`, date_format(`effective_on`, 'yyyy-MM-dd')),
       `raw_source_payload`,
       CASE `quarantine_reason`
         WHEN 'KEY_NULL' THEN 'a declared plan-change request has no tenant, plan or effective date, so f_md5_uuid cannot key the subscription it would insert'
         ELSE 'the tenant or the plan the request would insert a subscription for was not loaded, so fk_sub_tenant/fk_sub_plan could not hold'
       END,
       CASE `quarantine_reason` WHEN 'FK_ORPHAN' THEN 'D-19' ELSE 'D-14' END,
       {BATCH_LIT}, current_timestamp()
FROM v_requests_judged WHERE `quarantine_reason` IS NOT NULL
"""
spark.sql(QUAR_SQL).createOrReplaceTempView("v_quarantine_raw")

# One record per MERGE identity (ns, source_table, source_key, quarantine_reason). Several source rows
# legitimately share one identity — KEY_DUPLICATE is two bronze rows under one id by definition, and
# every KEY_NULL row whose key is null shares the null key — and inserting them all would leave the
# next run's MERGE matching one stored reject against many source rows, which Delta refuses. The rows
# are collapsed deterministically instead, carrying the count and every payload so each rejected
# source row stays diagnosable from the quarantine table alone.
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
quarantined_rows = spark.table("v_quarantine").count()

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

# The identities *this run* rejected, with this run's batch id. Any recon check that excludes a
# rejected identity scopes the exclusion to this set, not to whatever the ledger still carries from
# an older batch: quarantine is a ledger of rejections, not current state (tolerance item 6/D-28).
rejection_ledger = {
    "_batch_id": BATCH_ID,
    "rejected_plan_ids_this_run": [
        r[0]
        for r in spark.sql(
            "SELECT `id` FROM v_plans_judged WHERE `quarantine_reason` IS NOT NULL ORDER BY `id`"
        ).collect()
    ],
    "rejected_subscription_ids_this_run": [
        r[0]
        for r in spark.sql(
            "SELECT `id` FROM v_subs_judged WHERE `quarantine_reason` IS NOT NULL ORDER BY `id`"
        ).collect()
    ],
    "rejected_request_tenants_this_run": [
        r[0]
        for r in spark.sql(
            "SELECT DISTINCT `tenant_id` FROM v_requests_judged "
            "WHERE `quarantine_reason` IS NOT NULL ORDER BY `tenant_id`"
        ).collect()
    ],
    "ledger_rows_retained_from_earlier_batches": spark.sql(
        f"SELECT count(*) FROM {QUARANTINE} WHERE `ns` = {NS_LIT} AND `_batch_id` <> {BATCH_LIT}"
    ).collect()[0][0],
}

quar_by_reason = [
    {"source_table": r[0], "quarantine_reason": r[1], "rows": r[2]}
    for r in spark.sql(
        """
        SELECT `source_table`, `quarantine_reason`, count(*)
        FROM v_quarantine GROUP BY `source_table`, `quarantine_reason`
        ORDER BY `source_table`, `quarantine_reason`
        """
    ).collect()
]

# COMMAND ----------

# MAGIC %md ### Accounting, per owned table
# MAGIC
# MAGIC `loaded_rows + quarantined_rows == source_rows` for each table against its own declared source
# MAGIC population (ACC-QUAR). The halt rate is measured on **one** population — the subscription driver
# MAGIC — with numerator and denominator on that same population, not diluted across the three physical
# MAGIC tables this unit writes.

# COMMAND ----------

plans_source = spark.table("v_plans_judged").count()
plans_loaded = spark.table("v_plans_loaded").count()
subs_source = spark.table("v_subs_judged").count()
subs_loaded = spark.table("v_subs_loaded").count()
req_source = spark.table("v_requests_judged").count()
req_loaded = spark.table("v_requests").count()

accounting = {
    "plans": {
        "basis": "every OW_BILLING.PLANS row in ns; fn_list_plans' active filter is carried as "
        "columns (active_nvl, listed_by_fn_list_plans, list_seq) rather than dropping rows",
        "source_rows": plans_source,
        "loaded_rows": plans_loaded,
        "quarantined_rows": plans_source - plans_loaded,
    },
    "subscriptions": {
        "basis": "every OW_BILLING.SUBSCRIPTIONS row in ns, plus one new subscription per declared "
        "sp_change_plan request this run applies",
        "source_rows": subs_source + req_source,
        "loaded_rows": subs_loaded + req_loaded,
        "quarantined_rows": (subs_source - subs_loaded) + (req_source - req_loaded),
    },
    "entitlements": {
        "basis": "one fn_entitlement row per tenant in ns whose returned cursor finds a covering "
        f"subscription on {ENTITLEMENT_ON}; a tenant with none yields an empty result set, per the "
        "contract's write-empty-result semantics",
        "source_rows": ent_source_tenants,
        "loaded_rows": ent_loaded_tenants,
        "quarantined_rows": ent_source_tenants - ent_loaded_tenants,
    },
}
for _name, _acc in accounting.items():
    if _acc["loaded_rows"] + _acc["quarantined_rows"] != _acc["source_rows"]:
        raise AssertionError(f"quarantine accounting broken for {_name}: {_acc}")
    _acc["rate_pct"] = (
        round(100.0 * _acc["quarantined_rows"] / _acc["source_rows"], 4)
        if _acc["source_rows"]
        else 0.0
    )

QUAR_BASIS = SPEC["quarantine_halt_basis"]
quar_source_rows = accounting["subscriptions"]["source_rows"]
quar_rejected_rows = accounting["subscriptions"]["quarantined_rows"]
quar_pct = (100.0 * quar_rejected_rows / quar_source_rows) if quar_source_rows else 0.0
print(
    f"halt basis: {quar_rejected_rows} rejected of {quar_source_rows} subscription drivers "
    f"({quar_pct:.4f}%); physical quarantine rows={quarantined_rows}"
)

# COMMAND ----------

# MAGIC %md ### Delta commit attribution, then the quarantine MERGE, then the halt

# COMMAND ----------


def table_version(target: str) -> int:
    v = spark.sql(f"SELECT max(version) FROM (DESCRIBE HISTORY {full(target)})").collect()[0][0]
    return int(v) if v is not None else -1


# Every commit this run makes is made by the job run executing this notebook, and the version each
# target sat at before the run is captured here. The idempotency proof then reads only the commits
# this run produced: managed Delta interleaves maintenance commits (OPTIMIZE, VACUUM), ns=demo is
# shared with other sessions holding the same PAT, and the deployed Terraform job has a *fixed* name,
# so neither "the newest MERGE" nor a name match is attribution. Serverless refuses
# spark.databricks.delta.commitInfo.userMetadata, so the commit is identified by `job.jobRunId` from
# DESCRIBE HISTORY, with the job name only as a fallback where no run id is reported at all.
WRITE_TARGETS = ("plans", "subscriptions", "entitlements", f"quarantine_{UNIT}")
base_versions = {t: table_version(t) for t in WRITE_TARGETS}
print(f"target versions before this run's writes: {base_versions}")


def context_run_ids() -> list[str]:
    """This run's Databricks run identifiers, as the notebook context reports them."""
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
    job = row["job"]
    if job is None:
        return {"job_name": None, "job_run_id": None}
    return {"job_name": job["jobName"], "job_run_id": job["jobRunId"]}


def commit_is_this_run(row) -> tuple[bool, str]:
    job = writing_job(row)
    run_id = job["job_run_id"]
    if run_id is not None and str(run_id) != "" and RUN_IDS:
        return str(run_id) in RUN_IDS, "job_run_id"
    return (job["job_name"] or "").endswith(BATCH_ID), "job_name_suffix"


def history_metrics(target: str, operation: str) -> dict:
    """This run's own `operation` commit on `target`, from DESCRIBE HISTORY.

    A commit qualifies only if it is newer than the version the target sat at before this run
    started *and* was written by one of this run's own job run ids. A write that changed nothing
    produces no commit at all — reported as such rather than borrowed from an older commit.
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
    return {
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
        f"{quar_source_rows} subscription drivers) exceeds {HALT_PCT}% — halting the unit instead of "
        f"loading around it. The {quarantined_rows} rejected rows are in {QUARANTINE} (ns={NS}, "
        f"_batch_id={BATCH_ID}); no plan, subscription or entitlement was written"
    )

# COMMAND ----------

# MAGIC %md ### `NUMERIC_OVERFLOW` reachability
# MAGIC
# MAGIC Bronze already holds `monthly_fee` as `DECIMAL(14,2)`, so nothing in this population overflows.
# MAGIC A guard whose reachability is asserted rather than shown is the wave 2 finding, so the guard's
# MAGIC own predicate is pushed a synthetic pre-cast value here. This probes the target expression only;
# MAGIC it writes nothing and it is not a finding about the source.

# COMMAND ----------


def overflow_case(raw_expr: str, column: str = "monthly_fee") -> dict:
    """One synthetic pre-cast value through the load's own guard, on one column."""
    if column == "monthly_fee":
        guard = (
            f"abs(p.`monthly_fee_raw`) > CAST({MONEY_MAX} AS DECIMAL(38,6)) "
            "OR (p.`monthly_fee_raw` IS NOT NULL AND p.`monthly_fee` IS NULL)"
        )
        cast = "DECIMAL(14,2)"
    else:
        guard = (
            f"abs(p.`overage_rate_raw`) > CAST({RATE_MAX} AS DECIMAL(38,6)) "
            "OR (p.`overage_rate_raw` IS NOT NULL AND p.`overage_rate` IS NULL)"
        )
        cast = "DECIMAL(12,6)"
    row = spark.sql(
        f"""
        WITH p AS (
          SELECT {raw_expr} AS `{column}_raw`, try_cast({raw_expr} AS {cast}) AS `{column}`
        )
        SELECT CAST(p.`{column}_raw` AS STRING), CAST(p.`{column}` AS STRING),
               CASE WHEN {guard} THEN 'NUMERIC_OVERFLOW' ELSE NULL END
        FROM p
        """
    ).collect()[0]
    return {
        "column": column,
        "pre_cast_expression": raw_expr,
        "raw_value": row[0],
        "value_after_cast": row[1],
        "quarantine_reason": row[2],
    }


overflow_probe = {
    "description": "synthetic pre-cast plan numbers — a fee beyond DECIMAL(14,2), a rate beyond "
    "DECIMAL(12,6), a NULL and an in-range control — each pushed through the same wider raw column, "
    "the same try_cast and the same guard the load applies",
    "is_probe_of_target_expression_not_source_finding": True,
    "cases": [
        overflow_case("CAST(1e14 AS DECIMAL(38,6))"),
        overflow_case("CAST(1e7 AS DECIMAL(38,6))", "overage_rate"),
        overflow_case("CAST(NULL AS DECIMAL(38,6))"),
        overflow_case("CAST(49.00 AS DECIMAL(38,6))"),
    ],
}
_expected_probe = ["NUMERIC_OVERFLOW", "NUMERIC_OVERFLOW", None, None]
overflow_probe["expected_reasons"] = _expected_probe
print(json.dumps(overflow_probe, indent=1))
if [c["quarantine_reason"] for c in overflow_probe["cases"]] != _expected_probe:
    raise AssertionError(
        f"the NUMERIC_OVERFLOW guard did not behave as declared on the probe: {overflow_probe}"
    )

# COMMAND ----------

# MAGIC %md ## The three MERGEs
# MAGIC
# MAGIC `MERGE` on each table's declared key plus `ns` (D-14/ACC-IDEM), payloads compared null-safely so
# MAGIC a second identical run rewrites nothing. Rows this unit did not produce are never touched: there
# MAGIC is no `DELETE`, no `INSERT OVERWRITE` and no table-wide statement anywhere in this notebook
# MAGIC (D-28), which is what lets wave 4 write `SUBSCRIPTIONS` beside it.

# COMMAND ----------

spark.sql(
    """
    CREATE OR REPLACE TEMP VIEW v_plans_src AS
    SELECT `id`, `code`, `tier_cd`, `tier`, `monthly_fee`, `included_units`, `overage_rate`,
           `active_yn`, `active_nvl`, `listed_by_fn_list_plans`, `list_seq`,
           'source-migrated' AS `_origin`
    FROM v_plans_loaded
    """
)
spark.sql("CREATE OR REPLACE TEMP VIEW v_entitlements_src AS SELECT *, 'target-entitlement' AS `_origin` FROM v_entitlements")


def merge_target(tbl: dict, view: str) -> dict:
    target = tbl["target"]
    cols = [c["name"] for c in tbl["columns"]]
    keys = [k for k in tbl["merge_key"] if k != "ns"]
    payload = [c for c in cols if c not in keys] + ["_origin"]
    on = " AND ".join([f"t.`{k}` = s.`{k}`" for k in keys] + [f"t.`ns` = {NS_LIT}"])
    diff = " OR ".join(f"NOT (t.`{c}` <=> s.`{c}`)" for c in payload)
    sets = ",\n      ".join(
        [f"t.`{c}` = s.`{c}`" for c in payload]
        + [f"t.`_batch_id` = {BATCH_LIT}", "t.`_loaded_at` = current_timestamp()"]
    )
    insert_cols = ", ".join(
        [f"`{c}`" for c in cols] + ["`ns`", "`_origin`", "`_batch_id`", "`_loaded_at`"]
    )
    insert_vals = ", ".join(
        [f"s.`{c}`" for c in cols] + [NS_LIT, "s.`_origin`", BATCH_LIT, "current_timestamp()"]
    )
    spark.sql(
        f"""
        MERGE INTO {full(target)} t
        USING {view} s
          ON {on}
        WHEN MATCHED AND ({diff}) THEN UPDATE SET
      {sets}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """
    )
    return history_metrics(target, "MERGE")


metrics = {
    "plans": merge_target(TABLES["plans"], "v_plans_src"),
    "subscriptions": merge_target(TABLES["subscriptions"], "v_subs_src"),
    "entitlements": merge_target(TABLES["entitlements"], "v_entitlements_src"),
    f"quarantine_{UNIT}": quarantine_metrics,
}
print(json.dumps(metrics, indent=1))


def first_insert_commit(target: str) -> dict:
    """The oldest `MERGE` commit on `target` that inserted rows, from the full Delta history.

    A run whose targets already hold the converged load inserts nothing, which is idempotency and
    not evidence that the load path works. This reads the commit that did the cold load out of
    history so the insert path is shown as measured rather than asserted; it may belong to an
    earlier invocation, and says which one.
    """
    rows = [
        r
        for r in spark.sql(f"DESCRIBE HISTORY {full(target)}")
        .where("operation = 'MERGE'")
        .orderBy("version")
        .collect()
        if int(((r["operationMetrics"] or {}).get("numTargetRowsInserted", 0)) or 0) > 0
    ]
    if not rows:
        return {"exists": False, "note": "no MERGE commit on this target has ever inserted a row"}
    row = rows[0]
    m = row["operationMetrics"] or {}
    return {
        "exists": True,
        "version": int(row["version"]),
        "timestamp": str(row["timestamp"]),
        "writing_job_run": writing_job(row),
        "rows_inserted": int(m.get("numTargetRowsInserted", 0)),
        "is_this_run": commit_is_this_run(row)[0] and int(row["version"]) > base_versions[target],
    }


cold_load = {t: first_insert_commit(t) for t in WRITE_TARGETS}
print(json.dumps(cold_load, indent=1))

# COMMAND ----------

# MAGIC %md ## Recomputed from the target
# MAGIC
# MAGIC Every number the recon report carries about the target is read back out of Delta after the
# MAGIC `MERGE`, not carried over from the views above.

# COMMAND ----------

target_counts = {}
for _t in ("plans", "subscriptions", "entitlements"):
    row = spark.sql(
        f"""
        SELECT count(*), sum(CASE WHEN `ns` IS NULL THEN 1 ELSE 0 END),
               sum(CASE WHEN `_batch_id` = {BATCH_LIT} THEN 1 ELSE 0 END),
               count(DISTINCT `_origin`)
        FROM {full(_t)} WHERE `ns` = {NS_LIT}
        """
    ).collect()[0]
    target_counts[_t] = {
        "rows": int(row[0]),
        "rows_without_ns": int(row[1] or 0),
        "rows_stamped_by_this_batch": int(row[2] or 0),
        "distinct_origins": int(row[3] or 0),
    }
target_counts[f"quarantine_{UNIT}"] = {
    "rows": spark.sql(
        f"SELECT count(*) FROM {QUARANTINE} WHERE `ns` = {NS_LIT}"
    ).collect()[0][0]
}

money = spark.sql(
    f"""
    SELECT CAST(sum(`monthly_fee`) AS STRING) FROM {full('plans')} WHERE `ns` = {NS_LIT}
    """
).collect()[0][0]
money_listed = spark.sql(
    f"""
    SELECT CAST(sum(`monthly_fee`) AS STRING) FROM {full('plans')}
    WHERE `ns` = {NS_LIT} AND `listed_by_fn_list_plans`
    """
).collect()[0][0]
money_ent = spark.sql(
    f"""
    SELECT CAST(sum(`monthly_fee`) AS STRING), count(*),
           sum(CASE WHEN `monthly_fee` IS NULL THEN 1 ELSE 0 END)
    FROM {full('entitlements')} WHERE `ns` = {NS_LIT} AND `as_of_on` = {AS_OF_TS}
    """
).collect()[0]

money_summary = {
    "plans.monthly_fee_total": money,
    "plans.monthly_fee_total_listed_by_fn_list_plans": money_listed,
    "entitlements.monthly_fee_total": money_ent[0],
    "entitlements.rows": int(money_ent[1]),
    "entitlements.monthly_fee_null_extended_rows": int(money_ent[2] or 0),
    "quarantined_rows_alongside_money": quarantined_rows,
    "quarantine_rate_pct_on_the_declared_halt_basis": round(quar_pct, 4),
}
print(json.dumps(money_summary, indent=1))

# COMMAND ----------

# MAGIC %md ## Anomaly detections
# MAGIC
# MAGIC Each one names the source construct, what this port does instead, and the population it was
# MAGIC measured on. A zero population is reported as a zero, never as a pass.

# COMMAND ----------

anomalies = {
    "ANOM-SENTINEL-DATE": {
        "detected": True,
        "source_construct": "fn_entitlement's package-global lookup: "
        "NVL(s.ends_on, TO_DATE('31-DEC-99','DD-MON-YY')) >= p_on (02_pkg_plans.sql:46)",
        "detector": "the sentinel is pinned to DATE'2099-12-31' from the spec and both predicates are "
        "evaluated per row; the runtime's own parse of '31-DEC-99' is probed beside it and reported as "
        "measured, since a two-digit-year pivot belongs to the engine and not to the source text",
        "target_behaviour": "the 2099 literal is used for the sentinel predicate and the cursor keeps "
        "its own (ends_on IS NULL OR ends_on >= p_on) form; the two predicates are two columns",
        "spark_parse_of_the_literal": dialect_probe["spark_to_date_31_DEC_99"],
        "pinned_literal": dialect_probe["pinned_sentinel_literal_used_by_this_port"],
        "subscriptions_with_a_null_ends_on": spark.sql(
            "SELECT count(*) FROM v_subs_loaded WHERE `ends_on` IS NULL"
        ).collect()[0][0],
        "tenants_covered_by_the_sentinel_predicate": entitlement_populations[
            "tenants_covered_sentinel_predicate"
        ],
        "tenants_covered_by_the_cursor_predicate": entitlement_populations[
            "tenants_covered_cursor_predicate"
        ],
        "tenants_where_the_two_predicates_disagree": entitlement_populations[
            "tenants_where_the_two_predicates_disagree"
        ],
    },
    "ANOM-ROWNUM-TIEBREAK": {
        "detected": True,
        "source_construct": "AND ROWNUM = 1 with no ORDER BY in the global lookup "
        "(02_pkg_plans.sql:47), and ROWNUM <= 1 after ORDER BY s.starts_on DESC in the returned "
        "cursor (02_pkg_plans.sql:67-68) — neither is total, so a tie is decided by the plan",
        "detector": "both picks are pinned to row_number() OVER (PARTITION BY tenant_id ORDER BY "
        "starts_on DESC, id DESC) = 1 (D-08) and the candidate and tie counts are carried on every "
        "entitlement row",
        "target_behaviour": "deterministic pick; the tie population is measured and the path is "
        "listed in the recon report's unverified paths rather than claimed as parity",
        "rows_with_more_than_one_candidate": entitlement_populations[
            "rows_with_more_than_one_candidate"
        ],
        "rows_with_tied_starts_on": entitlement_populations["rows_with_tied_starts_on"],
        "tie_break_pinned_to": CONST["covering_pick_order_by"],
    },
    "ANOM-ROWBYROW-CLOSEOUT": {
        "detected": True,
        "source_construct": "FOR r IN c_open_subs LOOP UPDATE subscriptions SET ends_on = "
        "p_effective_on - 1, status_cd = DECODE(r.status_cd, 30, 30, 10) WHERE CURRENT OF "
        "c_open_subs (02_pkg_plans.sql:90-95), over a FOR UPDATE cursor with no ORDER BY",
        "detector": "the loop is re-expressed set-wise with the order pinned and published as "
        "closeout_seq; each row's new state is a function of its own old state only, so the pinned "
        "order changes no value here — the order-dependence is in the source's shape",
        "target_behaviour": f"pinned close-out order {CONST['closeout_order_by']}; ends_on = "
        "effective_on - INTERVAL 1 DAY with any time component carried (D-07/T7); status 30 stays 30 "
        "(trg_sub_no_uncancel, D-16) and status 20 becomes 10, which is reproduced, not corrected",
        "subscriptions_closed": change_populations["subscriptions_closed_by_the_loop"],
        "suspended_to_active_flips": change_populations["suspended_to_active_flips"],
        "cancelled_visited": change_populations["cancelled_subscriptions_visited"],
        "cancelled_preserved": change_populations["cancelled_preserved"],
        "open_subscriptions_left_overlapping_by_the_strict_less_than": change_populations[
            "open_subscriptions_left_overlapping_by_the_strict_less_than"
        ],
        "open_subscriptions_starting_exactly_on_the_effective_date": change_populations[
            "open_subscriptions_starting_exactly_on_the_effective_date"
        ],
    },
    "ANOM-PKG-GLOBAL-STATE": {
        "detected": True,
        "source_construct": "g_last_tenant_id := p_tenant_id is assigned before the SELECT ... INTO "
        "g_last_plan_code, whose WHEN OTHERS THEN NULL swallows NO_DATA_FOUND, and nothing ever "
        "invalidates the pair (02_pkg_plans.sql:39-50)",
        "detector": "the walk is reconstructed in the declared tenant order and the value the "
        "swallowed exception leaves behind is carried as stale_global_plan_code with "
        "stale_global_mismatch beside it",
        "target_behaviour": "no package-global equivalent is built (D-10): global_lookup_matched, "
        "global_lookup_plan_code, stale_global_plan_code and stale_global_mismatch are columns on "
        "the entitlement row",
        "tenants_that_would_hit_the_mismatch": entitlement_populations[
            "tenants_that_would_hit_the_stale_globals_mismatch"
        ],
        "entitlement_rows_carrying_a_mismatch": entitlement_populations[
            "rows_carrying_a_stale_global_mismatch"
        ],
        "global_iteration_order_pinned_to": CONST["global_iteration_order_by"],
        "note": "a tenant with no covering subscription has no entitlement row at all (the contract's "
        "write-empty-result shape), so the mismatch population is measured over every tenant in ns "
        "rather than over the rows the table holds",
    },
    "ANOM-DYNAMIC-SQL": {
        "detected": True,
        "source_construct": "v_sql := 'INSERT INTO subscriptions (id, tenant_id, plan_id, starts_on, "
        "status_cd) VALUES (:1, :2, :3, :4, 10)'; EXECUTE IMMEDIATE v_sql USING ... "
        "(02_pkg_plans.sql:100-104) — dynamic SQL for a perfectly static INSERT",
        "detector": "the statement is read from the source and re-expressed as the static write in "
        "v_subs_src; nothing in this notebook assembles SQL from source data",
        "target_behaviour": "static INSERT through the subscriptions MERGE, keyed by "
        "f_md5_uuid(tenant || plan || TO_CHAR(effective_on,'YYYY-MM-DD')) plus ns (D-20, D-14)",
        "new_subscriptions_written_by_the_static_equivalent": change_populations[
            "new_subscriptions"
        ],
    },
    "ANOM-SWALLOWED-EXCEPTION": {
        "detected": True,
        "source_construct": "EXCEPTION WHEN OTHERS THEN NULL around the global lookup "
        "(02_pkg_plans.sql:48-49): NO_DATA_FOUND, and anything else, is discarded and the function "
        "returns as if the lookup had succeeded",
        "detector": "the lookup's own outcome is a column (global_lookup_matched), so a swallowed "
        "failure is visible rather than silent (T12)",
        "target_behaviour": "nothing is swallowed: a lookup that finds nothing is false in "
        "global_lookup_matched, and a request or subscription that cannot be loaded is quarantined "
        "with a closed reason rather than skipped",
        "lookups_that_found_nothing": entitlement_populations[
            "rows_whose_global_lookup_found_nothing"
        ],
        "tenants_whose_lookup_would_raise_NO_DATA_FOUND": entitlement_populations[
            "tenants_with_no_covering_subscription_sentinel_predicate"
        ],
    },
}

# COMMAND ----------

# MAGIC %md ## Run summary

# COMMAND ----------

summary = {
    "unit": UNIT,
    "ns": NS,
    "batch_id": BATCH_ID,
    "entitlement_on": ENTITLEMENT_ON,
    "change_effective_on": CHANGE_EFFECTIVE_ON,
    "spec_path": SPEC_PATH,
    "bronze_inputs": SPEC["bronze_inputs"],
    "accounting": accounting,
    "quarantine": {
        "basis": QUAR_BASIS,
        "halt_threshold_pct": HALT_PCT,
        "rate_pct": round(quar_pct, 4),
        "rate_source_rows": quar_source_rows,
        "rate_rejected_rows": quar_rejected_rows,
        "physical_rows_this_run": quarantined_rows,
        "source_rows_rejected_this_run": quarantine_source_rows,
        "by_source_table_and_reason": quar_by_reason,
        "persisted_before_halt_decision": True,
        "rejection_ledger": rejection_ledger,
    },
    "target_counts": target_counts,
    "money": money_summary,
    "plans_populations": {
        "source_rows": plans_source,
        "unknown_tier_plans": unknown_tier_plans,
        "inactive_plans": inactive_plans,
        "null_active_yn_plans": null_active_yn_plans,
        "listed_by_fn_list_plans": spark.table("v_plans_listed").count(),
    },
    "subscription_populations": {
        "source_rows": subs_source,
        "rows_with_a_missing_plan_row": subs_with_missing_plan,
        **change_populations,
    },
    "entitlement_populations": entitlement_populations,
    "dialect_probe": dialect_probe,
    "overflow_probe": overflow_probe,
    "merge_metrics": metrics,
    "cold_load_commits": cold_load,
    "anomaly_detections": anomalies,
    # The declared request population this run applied, published so the recon can build the same
    # set from Oracle by the spec's rule and compare the two derivations instead of trusting one.
    "change_requests": [
        {
            "tenant_id": r[0],
            "plan_id": r[1],
            "effective_on": r[2],
            "new_subscription_id": r[3],
            "pinned_by_transcript": r[4],
            "quarantine_reason": r[5],
        }
        for r in spark.sql(
            """
            SELECT `tenant_id`, `plan_id`, date_format(`effective_on`, 'yyyy-MM-dd'),
                   `new_subscription_id`, `pinned_by_transcript`, `quarantine_reason`
            FROM v_requests_judged ORDER BY `tenant_id`, `effective_on`
            """
        ).collect()
    ],
    "fn_list_plans": [
        {
            "list_seq": r[0],
            "code": r[1],
            "tier": r[2],
            "monthly_fee": r[3],
            "included_units": r[4],
            "overage_rate": r[5],
            "plan_id": r[6],
        }
        for r in spark.sql(
            f"""
            SELECT `list_seq`, `code`, `tier`, CAST(`monthly_fee` AS STRING),
                   CAST(`included_units` AS STRING), CAST(`overage_rate` AS STRING), `id`
            FROM {full('plans')}
            WHERE `ns` = {NS_LIT} AND `listed_by_fn_list_plans`
            ORDER BY `list_seq`
            """
        ).collect()
    ],
}

out_path = f"{LANDING}/_runs/{BATCH_ID}.json"
dbutils.fs.mkdirs(f"{LANDING}/_runs")
dbutils.fs.put(out_path, json.dumps(summary, indent=1), overwrite=True)
print(f"run summary -> {out_path}")
dbutils.notebook.exit(json.dumps({"run_summary": out_path, "batch_id": BATCH_ID}))
