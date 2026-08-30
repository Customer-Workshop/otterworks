# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_silver_dunning — `pkg_dunning` on Delta
# MAGIC
# MAGIC Wave 4 of the OW_BILLING → Databricks run, and the estate's only write-target collision, which
# MAGIC is why it runs alone in its wave. This notebook is the whole write path for
# MAGIC `ow_tp.silver.dunning_attempts`, `ow_tp.silver.notifications`, `ow_tp.silver.tenants` and
# MAGIC `ow_tp.silver.quarantine_silver_dunning`, plus **two columns** on the shared
# MAGIC `ow_tp.silver.subscriptions`. It is ported from
# MAGIC `services/legacy-billing/db/oracle/packages/05_pkg_dunning.sql`
# MAGIC (`fn_overdue_accounts`, `sp_schedule_dunning`, `sp_suspend_overdue`) and
# MAGIC `services/legacy-billing/db/oracle/schema/04_jobs.sql` (`JOB_NIGHTLY_DUNNING`), with the DDL and
# MAGIC triggers beside them.
# MAGIC
# MAGIC ## What it reads and what it writes
# MAGIC
# MAGIC | Object | Owner | This unit |
# MAGIC | --- | --- | --- |
# MAGIC | `ow_tp.silver.invoices` | `silver_invoicing` | **read only** — the `status_cd = 40` population |
# MAGIC | `ow_tp.bronze.tenants`, `.dunning_attempts`, `.notifications`, `.codes` | `bronze_core` | **read only** |
# MAGIC | `ow_tp.silver.dunning_attempts`, `.notifications`, `.tenants`, `.quarantine_silver_dunning` | this unit | create + `MERGE` |
# MAGIC | `ow_tp.silver.subscriptions` | `silver_plans` (wave 3) | `MERGE ... WHEN MATCHED THEN UPDATE` of `status_cd` and `suspended_on` **only** |
# MAGIC
# MAGIC The tenant-status output of `sp_suspend_overdue`'s `UPDATE TENANTS SET status_cd = 20` goes to
# MAGIC `ow_tp.silver.tenants` (this unit's own target, carrying `status_cd_ingest` beside `status_cd`),
# MAGIC never back to `ow_tp.bronze.tenants`. No statement here reads or writes anything outside
# MAGIC `ow_tp`, and every statement is filtered to the run's `ns`.
# MAGIC
# MAGIC ## The collision, stated as what the code does (D-30)
# MAGIC
# MAGIC On `ow_tp.silver.subscriptions` this notebook issues exactly one statement: a `MERGE` whose only
# MAGIC clause is `WHEN MATCHED AND <value changes> THEN UPDATE SET status_cd, suspended_on`, matched on
# MAGIC `(id, ns)`. There is no `WHEN NOT MATCHED`, so nothing is inserted; there is no `DELETE` clause
# MAGIC and no `DELETE` statement anywhere in this notebook, on any table; and there is no `CREATE`,
# MAGIC `ALTER` or `DROP` against that table, which is why this unit adds **no** audit column of its own
# MAGIC to it even though D-30 would allow one — adding a column is DDL on another unit's table. The
# MAGIC per-row evidence (which ids were updated, their prior `status_cd`/`suspended_on`, and a hash of
# MAGIC every *other* column before and after the merge) is published in the run summary and the recon
# MAGIC report instead. `_origin`, `_batch_id` and `_loaded_at` are wave 3's and are never in the
# MAGIC `UPDATE SET` list.
# MAGIC
# MAGIC What the attribution guard below actually protects, precisely: **before** the merge, every
# MAGIC `ow_tp.silver.subscriptions` row in this `ns` belonging to a tenant the sweep touches is checked
# MAGIC for an `_origin` this unit recognises as a merged unit's (`source-migrated`, `target-change`)
# MAGIC and a non-empty `_batch_id`; if any one of them fails, the notebook raises and writes nothing
# MAGIC to that table, and the operator escalates centrally. It does **not** protect against wave 3
# MAGIC concurrently rewriting the same rows (the waves are serialised for that), it does not verify
# MAGIC wave 3's *values*, and it is not a lock.
# MAGIC
# MAGIC ## One batch, two ordered tasks (ACC-TWO-ENTRYPOINTS)
# MAGIC
# MAGIC `JOB_NIGHTLY_DUNNING` is one job action: `sp_schedule_dunning(TRUNC(SYSDATE))` then
# MAGIC `sp_suspend_overdue(TRUNC(SYSDATE))`, over one state of the invoice table. The target is one job
# MAGIC with two ordered notebook tasks over **one** snapshot:
# MAGIC
# MAGIC * `phase=schedule` builds the overdue snapshot — every `status_cd = 40` invoice in the `ns`,
# MAGIC   carrying the three source predicates as columns — persists it once as JSON lines under
# MAGIC   `<landing>/<ns>/silver_dunning/snapshots/<batch_id>/`, with a `sha256` manifest, and then does
# MAGIC   `sp_schedule_dunning`'s work from it.
# MAGIC * `phase=suspend` (`depends_on` the first task) **reads that file** and never re-queries
# MAGIC   `ow_tp.silver.invoices` for its population. It fails closed if the snapshot for its `batch_id`
# MAGIC   is missing, if the manifest hash does not match, or if the snapshot's `as_of` is not its own.
# MAGIC
# MAGIC Three different populations come out of that one snapshot, because the source's three statements
# MAGIC do not share a predicate:
# MAGIC
# MAGIC * `fn_overdue_accounts`: `status_cd = 40` **and** `TO_CHAR(issued_at,'YYYYMMDD') <
# MAGIC   TO_CHAR(p_as_of,'YYYYMMDD')` — strictly less than, so an invoice issued earlier **on the same
# MAGIC   calendar day is not overdue** (D-07) → `overdue_by_fn`.
# MAGIC * `sp_schedule_dunning`: `status_cd = 40` and **no date filter at all** → `in_schedule_driver`.
# MAGIC   A same-day invoice that `fn_overdue_accounts` excludes still gets an attempt.
# MAGIC * `sp_suspend_overdue`: `status_cd = 40` and `TO_CHAR(issued_at,'YYYYMMDD') <=
# MAGIC   TO_CHAR(TRUNC(p_as_of) - 14,'YYYYMMDD')` — inclusive → `in_suspend_cutoff`.
# MAGIC
# MAGIC ## Source behaviour reproduced here
# MAGIC
# MAGIC * **`t.id (+) = i.tenant_id` keeps the invoice** when the tenant row is missing (D-18): the join
# MAGIC   is `LEFT JOIN` from invoices, `tenant_row_missing` records it, and `tenant_status` is the
# MAGIC   literal `'UNKNOWN'`.
# MAGIC * **`DECODE(t.status_cd, 10,'active', 20,'suspended','UNKNOWN')`** is null-safe (D-03): `<=>`,
# MAGIC   not `=`. A NULL or unmapped status is `'UNKNOWN'` — not a NULL, not a quarantine.
# MAGIC * **`days_overdue`** is `TRUNC(p_as_of) - TRUNC(CAST(i.issued_at AS DATE))`, an integer day
# MAGIC   count on truncated dates → `datediff(to_date(as_of), to_date(issued_at))`.
# MAGIC * **`ORDER BY i.issued_at, i.id`** is the snapshot's order and `overdue_seq` carries it.
# MAGIC * **Attempt numbering** is `NVL(MAX(attempt_no),0)+1` per invoice, read in the source per loop
# MAGIC   iteration with no lock. Here it is one set-wise `max()` over the **ingest** attempt population
# MAGIC   (`ow_tp.bronze.dunning_attempts`) **plus this unit's own rows from strictly earlier `as_of`
# MAGIC   values**, computed in `BIGINT` so a candidate past `INT` is quarantined rather than wrapped.
# MAGIC   The two halves say different things: excluding this run's own `as_of` makes the ids a function
# MAGIC   of `(ns, as_of, ingest state)`, so a rerun of the same night recomputes the same ids and is a
# MAGIC   true no-op; including earlier nights makes the next night append attempt `n+1`, the way a
# MAGIC   later source night does, instead of merging over the night before it. Two consequences are
# MAGIC   measured rather than asserted away:
# MAGIC   every attempt this run schedules is collision-exposed in the source (a concurrent run reads
# MAGIC   the same `MAX` and computes the same `f_md5_uuid(invoice_id || attempt_no)`), and a source
# MAGIC   rerun on the same `p_as_of` *appends* another attempt per overdue invoice rather than raising.
# MAGIC * **The weekend shift** (ACC-WEEKEND-SHIFT, D-24, ANOM-LOCALE-DAY):
# MAGIC   `TO_CHAR(v_next,'DY','NLS_DATE_LANGUAGE=ENGLISH')` compared to `'SAT'`/`'SUN'` in a `DECODE`,
# MAGIC   shifting `+2`/`+1`. Reproduced by indexing the **source's own English abbreviation array**
# MAGIC   with `dayofweek()`, whose origin day is *proved* against pinned dates in the probe cell before
# MAGIC   it is used. `date_format(dt,'EEE')` is never emitted: its output is locale- and
# MAGIC   case-dependent, would never equal `'SAT'`, and every attempt would silently land unshifted.
# MAGIC   `source_day_of_week`, `weekend_shift_days` and `unshifted_scheduled_for` are persisted per
# MAGIC   attempt so the shift is evidence, not a claim.
# MAGIC * **`WHEN OTHERS THEN NULL` around the attempt INSERT is deliberately not reproduced**
# MAGIC   (ACC-NO-SWALLOW, T12). A write this unit cannot do fails the unit loudly, and an attempt the
# MAGIC   *source* could not have written is quarantined with its closed reason code and counted. What
# MAGIC   the swallow actually does, stated precisely: the id is `f_md5_uuid(invoice_id || attempt_no)`
# MAGIC   and `attempt_no` is `MAX+1`, so a same-day rerun does **not** raise `ORA-00001` — it inserts
# MAGIC   the next attempt number. The errors the handler really hides are (a) `ORA-02291` on
# MAGIC   `fk_da_tenant` for an invoice whose tenant row is missing — an invoice `fn_overdue_accounts`
# MAGIC   deliberately keeps — and (b) `ORA-00001` on `pk_dunning_attempts`/`uq_dunning_attempts` when
# MAGIC   two runs interleave on the unlocked `MAX`. In every case `g_scheduled_cnt` is left understated
# MAGIC   while `pkg_ow_util.log_msg` reports it as the night's count.
# MAGIC * **The sweep** (ACC-SUSPENSION): the `DISTINCT tenant_id` cursor is the inclusive 14-day
# MAGIC   string-compared cut; `IF v_active > 0` means only a tenant at `status_cd = 10` is swept, and
# MAGIC   the count is over the **current** tenant state, so a tenant this sweep already suspended is
# MAGIC   skipped by a later run (that is the source's `TENANTS` table read back, D-27's
# MAGIC   recompute-from-own-effect shape checked for this unit: here it makes the source
# MAGIC   *self-suppressing* across `p_as_of` values, and the target reproduces it by reading its own
# MAGIC   `ow_tp.silver.tenants` state, not by re-reading ingest). Only subscriptions at `status_cd = 10`
# MAGIC   are updated: `20` and `30` are left exactly as they are, which is also `trg_sub_no_uncancel`
# MAGIC   (D-16) — a cancelled subscription can never leave `30`. `suspended_on` is `TRUNC(p_as_of)`,
# MAGIC   the date, not the run timestamp.
# MAGIC * **`trg_subscriptions_hist`** fires once per subscription the source updates, writing a
# MAGIC   `SUBSCRIPTIONS_HIST` row with `HIST_DT` as a `'DD-MON-YY HH24:MI:SS'` string. Retired (D-17):
# MAGIC   no `_HIST` write from the target; Delta history covers the change from the first target run
# MAGIC   forward.
# MAGIC * **The notification INSERT is guarded in the source** —
# MAGIC   `WHERE NOT EXISTS (SELECT 1 FROM notifications WHERE tenant_id = ... AND kind_cd = 3 AND
# MAGIC   sent_at = CAST(TRUNC(p_as_of) AS TIMESTAMP))` — so a legacy rerun on the **same** `p_as_of`
# MAGIC   does *not* duplicate. `uq_notifications (tenant_id, kind_cd, sent_at)` backs that up: without
# MAGIC   the guard the INSERT would raise `ORA-00001`, and `sp_suspend_overdue` has **no** exception
# MAGIC   handler, so the sweep would abort mid-loop. This notebook reproduces the guard
# MAGIC   (`suppressed_by_not_exists` counts what it suppressed) and keys its own write on
# MAGIC   `f_md5_uuid(tenant_id || 'suspension' || TO_CHAR(TRUNC(p_as_of),'YYYY-MM-DD'))` plus `ns`.
# MAGIC   The populations a *different* `p_as_of` would add are measured in the run summary.
# MAGIC * **Package globals** `g_last_run_dt` / `g_scheduled_cnt` are not reproduced (D-10): they are
# MAGIC   run-level output fields (`as_of`, `scheduled_count`) in the run summary. `pkg_ow_util.log_msg`'s
# MAGIC   autonomous `BILLING_AUDIT_LOG` write is out of parity scope (D-20).
# MAGIC * **Empty input is a no-op**: no `status_cd = 40` invoice means no attempts, no notifications, no
# MAGIC   suspensions, and prior output left intact. Nothing here clears `dunning_attempts` (D-28), and
# MAGIC   D-31's carve-out does not apply to this unit at all — its driver is the source's own overdue
# MAGIC   population, not a job-parameter request list, so no row it writes could qualify and it issues
# MAGIC   no `DELETE`.
# MAGIC
# MAGIC ## Quarantine and the halt
# MAGIC
# MAGIC Closed reason codes only (`.migration/11_quarantine_codes.md`, no `OTHER`). Rows are persisted
# MAGIC **before** any threshold is evaluated (tolerance item 6) and the ledger row carries this run's
# MAGIC `_batch_id`. The 5% is evaluated on **each** declared population with its own paired numerator
# MAGIC and denominator, and the unit raises if **any** one of them exceeds it (tolerance item 5):
# MAGIC `dunning_attempts` and (in phase 2) `tenants`, `notifications`, `subscriptions_swept`. A halt in
# MAGIC phase 1 stops phase 2 through the task dependency.

# COMMAND ----------

import datetime as dt
import hashlib
import json
import pathlib
import re

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "silver")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("landing_root", "/Volumes/ow_tp/bronze/landing")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/silver_dunning_spec.json")
dbutils.widgets.text("batch_id", "")
dbutils.widgets.text("as_of", "2026-02-28")
dbutils.widgets.text("phase", "schedule")
dbutils.widgets.text("invoice_source", "silver")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRONZE = dbutils.widgets.get("bronze_schema").strip()
LANDING_ROOT = dbutils.widgets.get("landing_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()
AS_OF = dbutils.widgets.get("as_of").strip()
PHASE = dbutils.widgets.get("phase").strip()
INVOICE_SOURCE = dbutils.widgets.get("invoice_source").strip()

UNIT = "silver_dunning"

if not NS:
    raise ValueError("ns is required: every target row and every volume path is ns-scoped")
if CATALOG != "ow_tp":
    raise ValueError("this unit only reads and writes the ow_tp catalog")
if SCHEMA != "silver":
    raise ValueError("this unit owns targets in ow_tp.silver only")
if PHASE not in ("schedule", "suspend"):
    raise ValueError(
        f"phase={PHASE!r}: JOB_NIGHTLY_DUNNING has exactly two ordered entrypoints, "
        "'schedule' (sp_schedule_dunning) then 'suspend' (sp_suspend_overdue)"
    )
if INVOICE_SOURCE not in ("silver", "bronze"):
    raise ValueError(
        f"invoice_source={INVOICE_SOURCE!r} must be 'silver' (ow_tp.silver.invoices, the migrated "
        "namespaces) or 'bronze' (ow_tp.bronze.invoices, generated fixture namespaces only)"
    )
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", AS_OF):
    raise ValueError(f"as_of={AS_OF!r} must be YYYY-MM-DD: it is the source's TRUNC(p_as_of)")
if not BATCH_ID:
    raise ValueError(
        "batch_id is required: both tasks of one run must agree on it, because phase 2 reads the "
        "overdue snapshot phase 1 persisted under it (ACC-TWO-ENTRYPOINTS)"
    )
for _pname, _pval in (("ns", NS), ("batch_id", BATCH_ID)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", _pval):
        raise ValueError(f"{_pname}={_pval!r} must match ^[A-Za-z0-9_-]+$")

LANDING = f"{LANDING_ROOT}/{NS}/{UNIT}"
SNAPSHOT_DIR = f"{LANDING}/snapshots/{BATCH_ID}"
SNAPSHOT_PATH = f"{SNAPSHOT_DIR}/overdue_snapshot.json"
SNAPSHOT_MANIFEST = f"{SNAPSHOT_DIR}/manifest.json"
QUARANTINE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"


def read_text_file(path: str) -> str:
    """Volume and workspace files read directly.

    A workspace path is also tried under `/Workspace`, the way the merged units read their spec: on
    serverless the DBFS root is disabled, so `dbutils.fs.head` on `/Shared/...` raises
    `DBFS_DISABLED` rather than reading the workspace file.
    """
    candidates = [path]
    if not path.startswith(("/Workspace", "/Volumes", "dbfs:", "/dbfs")):
        candidates.append(f"/Workspace{path}")
    for cand in candidates:
        try:
            return pathlib.Path(cand).read_text()
        except OSError:
            continue
    return dbutils.fs.head(path, 64 * 1024 * 1024)


SPEC = json.loads(read_text_file(SPEC_PATH))

if SPEC["unit"] != UNIT:
    raise ValueError(f"spec at {SPEC_PATH} is for {SPEC['unit']!r}, not {UNIT!r}")

K = SPEC["dunning_constants"]
HALT_PCT = float(SPEC["quarantine_halt_threshold_pct"])
HALT_BASES = SPEC["quarantine_halt_bases"]
REASONS = set(SPEC["quarantine_reasons"])
DAY_ABBR = list(K["day_abbreviations_english"])
RECOGNISED_ORIGINS = list(SPEC["shared_write_policy"]["recognised_origins"])
SHARED_UPDATABLE = list(SPEC["shared_write_policy"]["updatable_columns"])

spark.conf.set("spark.sql.session.timeZone", "UTC")
spark.sql(f"USE CATALOG {CATALOG}")

print(
    json.dumps(
        {
            "unit": UNIT,
            "phase": PHASE,
            "ns": NS,
            "as_of": AS_OF,
            "batch_id": BATCH_ID,
            "invoice_source": INVOICE_SOURCE,
            "landing": LANDING,
            "snapshot": SNAPSHOT_PATH,
        },
        indent=1,
    )
)

# COMMAND ----------


def full(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"


def bronze(table: str) -> str:
    return f"{CATALOG}.{BRONZE}.{table}"


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


NS_LIT = lit(NS)
BATCH_LIT = lit(BATCH_ID)
AS_OF_LIT = f"DATE'{AS_OF}'"
INVOICES = full("invoices") if INVOICE_SOURCE == "silver" else bronze("invoices")


def f_md5_uuid(expr: str) -> str:
    """pkg_ow_util.f_md5_uuid: lower(md5(input)) sliced 8-4-4-4-12 (D-14)."""
    return (
        f"concat_ws('-', substr(lower(md5({expr})), 1, 8), substr(lower(md5({expr})), 9, 4), "
        f"substr(lower(md5({expr})), 13, 4), substr(lower(md5({expr})), 17, 4), "
        f"substr(lower(md5({expr})), 21, 12))"
    )


def scalar(statement: str):
    return spark.sql(statement).collect()[0][0]


def table_version(table: str) -> int:
    rows = spark.sql(f"DESCRIBE HISTORY {table}").select("version").collect()
    return max((int(r[0]) for r in rows), default=-1)


def table_exists(table: str) -> bool:
    return spark.catalog.tableExists(table)


def context_run_ids() -> list[str]:
    """The run ids Delta commit metadata can be attributed to (tolerance item 7)."""
    ids: list[str] = []
    try:
        ctx = json.loads(
            dbutils.notebook.entry_point.getDbutils().notebook().getContext().safeToJson()
        )
    except Exception as exc:  # noqa: BLE001 - context shape is not guaranteed
        print(f"notebook context carries no run id ({exc}); attribution falls back to the job name")
        return ids
    attrs = ctx.get("attributes") or {}
    for key in (
        "multitaskParentRunId",
        "jobRunId",
        "rootRunId",
        "currentRunId",
        "runId",
        "idInJob",
    ):
        val = attrs.get(key)
        if val not in (None, "") and str(val) not in ids:
            ids.append(str(val))
    return ids


RUN_IDS = context_run_ids()
# The deployed job passes `{{job.run_id}}` as the batch id, so a numeric batch id is itself a run id.
if BATCH_ID.isdigit() and BATCH_ID not in RUN_IDS:
    RUN_IDS.append(BATCH_ID)
ATTRIBUTION = (
    "version > the target's pre-run version AND the commit's job.jobRunId is one of this run's own "
    f"run ids ({', '.join(RUN_IDS) if RUN_IDS else 'none reported'}); where DESCRIBE HISTORY reports "
    "no job run id at all, the fallback is the commit's job.jobName ending with this run's batch id"
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


def history_metrics(table: str, operation: str = "MERGE") -> dict:
    """This run's own `operation` commit on `table`, read out of DESCRIBE HISTORY.

    A commit qualifies only if it is newer than the version the target sat at before this run
    started *and* was written by one of this run's own job run ids: managed Delta interleaves its
    own maintenance commits, ns=demo is shared with other sessions holding the same token, and the
    deployed job's name is fixed, so neither "the newest MERGE" nor a name match is attribution. A
    write that changed nothing produces no commit, and that is what gets reported rather than an
    older commit borrowed to look like this run's.
    """
    rows = (
        spark.sql(f"DESCRIBE HISTORY {table}")
        .where(f"operation = '{operation}' AND version > {PRE_VERSIONS[table]}")
        .orderBy("version", ascending=False)
        .collect()
    )
    judged = [(r,) + commit_is_this_run(r) for r in rows]
    mine = [(r, rule) for r, is_mine, rule in judged if is_mine]
    if not mine:
        return {
            "operation": operation,
            "version": None,
            "commit_from_this_run": False,
            "attributed_by": ATTRIBUTION,
            "pre_run_version": PRE_VERSIONS[table],
            "newer_commits_by_other_runs": [
                {"version": int(r["version"]), "writing_job_run": writing_job(r)}
                for r, _is_mine, _rule in judged
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
        "pre_run_version": PRE_VERSIONS[table],
        "writing_job_run": writing_job(row),
        "rows_inserted": int(m.get("numTargetRowsInserted", 0)),
        "rows_updated": int(m.get("numTargetRowsUpdated", 0)),
        "rows_deleted": int(m.get("numTargetRowsDeleted", 0)),
    }


# COMMAND ----------

# MAGIC %md
# MAGIC ## D-24 probe: the day-number origin is proved, not assumed
# MAGIC
# MAGIC The source compares `TO_CHAR(v_next,'DY','NLS_DATE_LANGUAGE=ENGLISH')` against `'SAT'`/`'SUN'`.
# MAGIC The translation indexes the source's own English abbreviation array with `dayofweek()`, so the
# MAGIC array's origin day has to be right. These pinned dates are checked before any attempt is
# MAGIC scheduled, and they are the same dates the `DUNNING-002`/`DUNNING-003` transcripts turn on
# MAGIC (`2026-02-14` is a Saturday, `2026-02-17` a Tuesday). `date_format(dt,'EEE')` is evaluated here
# MAGIC **only** to show why it is not used: it is locale- and case-dependent and never equals `'SAT'`.

# COMMAND ----------

DOW_ARRAY_SQL = "array(" + ", ".join(lit(d) for d in DAY_ABBR) + ")"


def dow_abbr(date_expr: str) -> str:
    return f"element_at({DOW_ARRAY_SQL}, dayofweek({date_expr}))"


PROBE_DATES = {
    "2026-02-14": "SAT",
    "2026-02-15": "SUN",
    "2026-02-16": "MON",
    "2026-02-17": "TUE",
    "2026-02-28": "SAT",
    "2026-03-01": "SUN",
}
probe = spark.sql(
    "SELECT "
    + ", ".join(
        f"dayofweek(DATE'{d}') AS n_{d.replace('-', '')}, "
        f"{dow_abbr(f'DATE{chr(39)}{d}{chr(39)}')} AS a_{d.replace('-', '')}, "
        f"date_format(DATE'{d}', 'EEE') AS locale_{d.replace('-', '')}"
        for d in PROBE_DATES
    )
).collect()[0]
dow_probe = {}
for d, expected in PROBE_DATES.items():
    key = d.replace("-", "")
    actual = probe[f"a_{key}"]
    dow_probe[d] = {
        "dayofweek": int(probe[f"n_{key}"]),
        "english_abbr": actual,
        "date_format_EEE": probe[f"locale_{key}"],
        "expected": expected,
    }
    if actual != expected:
        raise AssertionError(
            f"D-24: dayofweek() origin is not what {DAY_ABBR} assumes — {d} came back {actual!r}, "
            f"source NLS says {expected!r}. Refusing to schedule attempts off an unproven day number."
        )
if any(v["date_format_EEE"] == v["expected"] for v in dow_probe.values()):
    raise AssertionError(
        "date_format(dt,'EEE') matched the source's uppercase abbreviation on this cluster locale; "
        "the D-24 note assumes it does not. Stopping rather than shipping a locale-dependent path."
    )
print(json.dumps(dow_probe, indent=1))

SHIFT_SQL = (
    f"CASE WHEN {dow_abbr(AS_OF_LIT)} = 'SAT' THEN {int(K['weekend_shift_days']['SAT'])} "
    f"WHEN {dow_abbr(AS_OF_LIT)} = 'SUN' THEN {int(K['weekend_shift_days']['SUN'])} ELSE 0 END"
)
AS_OF_DOW, AS_OF_SHIFT = spark.sql(
    f"SELECT {dow_abbr(AS_OF_LIT)}, {SHIFT_SQL}"
).collect()[0]
AS_OF_SHIFT = int(AS_OF_SHIFT)
print(f"as_of {AS_OF} is {AS_OF_DOW} in the source's NLS abbreviations -> shift +{AS_OF_SHIFT} days")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Targets this unit owns
# MAGIC
# MAGIC Created here, with liquid clustering on the declared natural key plus `ns` (D-22). Nothing in
# MAGIC this cell touches `ow_tp.silver.subscriptions`: that table is wave 3's and this unit runs no DDL
# MAGIC on it.

# COMMAND ----------

TABLES = {t["target"]: t for t in SPEC["tables"]}
PHASE_TARGETS = {"schedule": ["dunning_attempts"], "suspend": ["tenants", "notifications"]}[PHASE]


def ensure_target(tbl: dict) -> None:
    cols = ",\n  ".join(f"`{c['name']}` {c['target_type']}" for c in tbl["columns"])
    cluster = ", ".join(f"`{c}`" for c in tbl["cluster_by"])
    comment = (
        f"{UNIT}: {tbl['source_table']} ported from pkg_dunning; ns-scoped, MERGE on "
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


for _name in PHASE_TARGETS:
    ensure_target(TABLES[_name])

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
      `population` STRING,
      `phase` STRING,
      `_batch_id` STRING NOT NULL,
      `_quarantined_at` TIMESTAMP NOT NULL
    )
    USING DELTA
    CLUSTER BY (`source_table`, `quarantine_reason`, `ns`)
    COMMENT {lit(f"{UNIT}: rejection ledger, closed reason codes, rows persisted before the 5% halt")}
    """
)

PRE_VERSIONS = {
    full(t): (table_version(full(t)) if table_exists(full(t)) else -1)
    for t in list(TABLES) + ["subscriptions"]
}
PRE_VERSIONS[QUARANTINE] = table_version(QUARANTINE)
print(json.dumps(PRE_VERSIONS, indent=1))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Forward-only nightly numbering: a backfill behind an already-run night is refused
# MAGIC
# MAGIC This check runs before **any** write of this run — before the overdue snapshot is persisted,
# MAGIC before any `MERGE` — because a refusal has to leave nothing behind.
# MAGIC
# MAGIC The attempt basis is the ingest population plus this unit's rows at `as_of <` this run's
# MAGIC `as_of`, so an `as_of` behind one that already ran would recompute an `attempt_no` the later
# MAGIC night already used, and `f_md5_uuid(invoice_id || attempt_no)` would `MERGE` over that night's
# MAGIC row. The source does not settle it: `05_pkg_dunning.sql:43-44` is
# MAGIC `SELECT NVL(MAX(attempt_no),0)+1 ... WHERE invoice_id = inv.id` with **no** `p_as_of`
# MAGIC predicate, so Oracle run out of order appends `max(all) + 1` and its numbering is a function of
# MAGIC execution order — a backfill appends a further attempt, and a rerun of the later night then
# MAGIC appends again on unchanged input. `JOB_NIGHTLY_DUNNING` only ever moves forward, so neither
# MAGIC renumber-by-date nor append-by-execution-order is a behaviour the nightly job produces; both
# MAGIC are operator decisions, and this unit takes neither silently.

# COMMAND ----------

if PHASE == "schedule":
    later_nights = [
        str(r[0])
        for r in spark.sql(
            f"""
            SELECT DISTINCT `as_of` FROM {full('dunning_attempts')}
             WHERE `ns` = {NS_LIT} AND `as_of` > to_date({AS_OF_LIT}) ORDER BY `as_of`
            """
        ).collect()
    ]
    if later_nights:
        raise AssertionError(
            "STOPA-DUNNING-BACKFILL: "
            f"{full('dunning_attempts')} already holds attempts for ns={NS} at strictly later as_of "
            f"values {later_nights}, and this run was asked for as_of={AS_OF}. Nothing has been "
            "written by this run: no overdue snapshot, no MERGE on any target. Attempt numbering "
            "here is forward-only (basis = ingest attempts plus this unit's rows at as_of < this "
            "run's as_of), so a backfill behind an already-run night would recompute an attempt_no "
            "a later night already used and its f_md5_uuid(invoice_id || attempt_no) id would MERGE "
            "over that night's row. The source does not decide it either: 05_pkg_dunning.sql:43-44 "
            "selects NVL(MAX(attempt_no),0)+1 with no p_as_of predicate, so Oracle would append by "
            "execution order rather than renumber by date, and a rerun of the later night would "
            "then append again on unchanged input. Choosing between renumber-by-date and "
            "append-by-execution-order is an operator decision; escalate rather than backfilling."
        )
    print(f"forward-only check: no attempts at an as_of later than {AS_OF} in ns={NS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inputs: codes, tenants as ingest left them, and the invoice population
# MAGIC
# MAGIC `ow_tp.bronze.tenants` is read, never written. Two ingest anomalies are handled explicitly
# MAGIC rather than allowed to fan out a join: a duplicated tenant id (impossible in Oracle, where
# MAGIC `TENANTS.id` is the primary key, so it can only be an ingest defect) is deduplicated for the
# MAGIC outer join and quarantined as `KEY_DUPLICATE` on the tenant population in phase 2; a missing
# MAGIC tenant row is *kept* by the outer join per D-18.

# COMMAND ----------

spark.sql(
    f"""
    CREATE OR REPLACE TEMP VIEW v_codes AS
    SELECT `code_type`, `code_val`, `code_desc` FROM {bronze('codes')} WHERE `ns` = {NS_LIT}
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TEMP VIEW v_tenants_raw AS
    SELECT `id`, `name`, `tax_exempt_yn`, `status_cd`,
           count(*) OVER (PARTITION BY `id`) AS `id_rows`,
           row_number() OVER (PARTITION BY `id` ORDER BY `status_cd`, `name`) AS `id_seq`
      FROM {bronze('tenants')} WHERE `ns` = {NS_LIT}
    """
)
spark.sql(
    """
    CREATE OR REPLACE TEMP VIEW v_tenants AS
    SELECT `id`, `name`, `tax_exempt_yn`, `status_cd`, `id_rows` FROM v_tenants_raw WHERE `id_seq` = 1
    """
)

if PHASE == "schedule":
    # Only phase 1 reads the invoice table at all: phase 2's population is the persisted snapshot,
    # and this view is not created in that phase so it cannot be read there by accident.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_invoices AS
        SELECT `id`, `tenant_id`, `issued_at`, `total`, `status_cd`
          FROM {INVOICES} WHERE `ns` = {NS_LIT}
        """
    )

DECODE_TENANT_STATUS = (
    "CASE WHEN t.`status_cd` <=> 10 THEN 'active' "
    "WHEN t.`status_cd` <=> 20 THEN 'suspended' ELSE 'UNKNOWN' END"
)

# COMMAND ----------

if PHASE == "schedule":
    # fn_overdue_accounts, plus the two predicates the other statements use, over one read of the
    # invoice population. This view *is* the snapshot both tasks work from.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_snapshot AS
        SELECT i.`id` AS `invoice_id`, i.`tenant_id`, i.`total` AS `invoice_total`,
               i.`issued_at` AS `invoice_issued_at`,
               datediff(to_date({AS_OF_LIT}), to_date(i.`issued_at`)) AS `days_overdue`,
               {DECODE_TENANT_STATUS} AS `tenant_status`,
               t.`status_cd` AS `tenant_status_cd_ingest`,
               t.`id` IS NULL AS `tenant_row_missing`,
               date_format(i.`issued_at`, {lit(K['date_compare_format'])})
                 < date_format({AS_OF_LIT}, {lit(K['date_compare_format'])}) AS `overdue_by_fn`,
               date_format(i.`issued_at`, {lit(K['date_compare_format'])})
                 <= date_format(date_sub({AS_OF_LIT}, {int(K['suspend_cutoff_days'])}),
                                {lit(K['date_compare_format'])}) AS `in_suspend_cutoff`,
               true AS `in_schedule_driver`,
               row_number() OVER (ORDER BY i.`issued_at`, i.`id`) AS `overdue_seq`
          FROM v_invoices i LEFT JOIN v_tenants t ON t.`id` = i.`tenant_id`
         WHERE i.`status_cd` = {int(K['overdue_status_cd'])}
        """
    )
    snap_rows = spark.sql(
        """
        SELECT `overdue_seq`, `invoice_id`, `tenant_id`, CAST(`invoice_total` AS STRING) AS `invoice_total`,
               date_format(`invoice_issued_at`, 'yyyy-MM-dd HH:mm:ss') AS `invoice_issued_at`,
               `days_overdue`, `tenant_status`, `tenant_status_cd_ingest`, `tenant_row_missing`,
               `overdue_by_fn`, `in_suspend_cutoff`, `in_schedule_driver`
          FROM v_snapshot ORDER BY `overdue_seq`
        """
    ).collect()
    if len(snap_rows) > 200000:
        raise AssertionError(
            f"{len(snap_rows)} overdue invoices exceeds the row-level diff ceiling in "
            ".migration/03_recon_tolerances.md; the snapshot transport needs re-deciding centrally"
        )
    payload = "\n".join(json.dumps({k: r[k] for k in r.asDict()}, default=str) for r in snap_rows)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    manifest = {
        "unit": UNIT,
        "ns": NS,
        "as_of": AS_OF,
        "batch_id": BATCH_ID,
        "invoice_source": INVOICES,
        "rows": len(snap_rows),
        "sha256": digest,
        "money_total_overdue": str(
            scalar("SELECT coalesce(sum(`invoice_total`), 0) FROM v_snapshot") or "0"
        ),
        "written_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "written_by_run_ids": RUN_IDS,
        "note": (
            "one snapshot per run, written by phase 'schedule' and read by phase 'suspend' "
            "(ACC-TWO-ENTRYPOINTS); phase 2 never re-queries the invoice table for its population"
        ),
    }
    dbutils.fs.mkdirs(SNAPSHOT_DIR)
    dbutils.fs.put(SNAPSHOT_PATH, payload, overwrite=True)
    dbutils.fs.put(SNAPSHOT_MANIFEST, json.dumps(manifest, indent=1), overwrite=True)
    print(json.dumps(manifest, indent=1))
else:
    # Phase 2 reads the file phase 1 wrote. Fail closed: no snapshot, a hash that does not match, or
    # a different as_of means the two entrypoints would not be working on one batch.
    manifest = json.loads(read_text_file(SNAPSHOT_MANIFEST))
    payload = read_text_file(SNAPSHOT_PATH)
    if hashlib.sha256(payload.encode()).hexdigest() != manifest["sha256"]:
        raise AssertionError(
            f"overdue snapshot at {SNAPSHOT_PATH} does not match its manifest sha256: the sweep "
            "would be running on a different population than sp_schedule_dunning did"
        )
    for field, mine in (("ns", NS), ("as_of", AS_OF), ("batch_id", BATCH_ID)):
        if str(manifest.get(field)) != str(mine):
            raise AssertionError(
                f"snapshot {field}={manifest.get(field)!r} but this task has {mine!r}: "
                "ACC-TWO-ENTRYPOINTS requires one snapshot for one batch"
            )
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if len(rows) != int(manifest["rows"]):
        raise AssertionError(f"snapshot rows {len(rows)} != manifest {manifest['rows']}")
    if rows:
        spark.createDataFrame(
            [
                (
                    int(r["overdue_seq"]),
                    r["invoice_id"],
                    r["tenant_id"],
                    r["invoice_total"],
                    r["invoice_issued_at"],
                    int(r["days_overdue"]) if r["days_overdue"] is not None else None,
                    r["tenant_status"],
                    int(r["tenant_status_cd_ingest"])
                    if r["tenant_status_cd_ingest"] is not None
                    else None,
                    bool(r["tenant_row_missing"]),
                    bool(r["overdue_by_fn"]),
                    bool(r["in_suspend_cutoff"]),
                    bool(r["in_schedule_driver"]),
                )
                for r in rows
            ],
            "overdue_seq INT, invoice_id STRING, tenant_id STRING, invoice_total STRING, "
            "invoice_issued_at STRING, days_overdue INT, tenant_status STRING, "
            "tenant_status_cd_ingest INT, tenant_row_missing BOOLEAN, overdue_by_fn BOOLEAN, "
            "in_suspend_cutoff BOOLEAN, in_schedule_driver BOOLEAN",
        ).createOrReplaceTempView("v_snapshot_raw")
    else:
        spark.sql(
            """
            CREATE OR REPLACE TEMP VIEW v_snapshot_raw AS
            SELECT CAST(NULL AS INT) AS `overdue_seq`, CAST(NULL AS STRING) AS `invoice_id`,
                   CAST(NULL AS STRING) AS `tenant_id`, CAST(NULL AS STRING) AS `invoice_total`,
                   CAST(NULL AS STRING) AS `invoice_issued_at`, CAST(NULL AS INT) AS `days_overdue`,
                   CAST(NULL AS STRING) AS `tenant_status`,
                   CAST(NULL AS INT) AS `tenant_status_cd_ingest`,
                   CAST(NULL AS BOOLEAN) AS `tenant_row_missing`,
                   CAST(NULL AS BOOLEAN) AS `overdue_by_fn`,
                   CAST(NULL AS BOOLEAN) AS `in_suspend_cutoff`,
                   CAST(NULL AS BOOLEAN) AS `in_schedule_driver`
             WHERE false
            """
        )
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_snapshot AS
        SELECT `overdue_seq`, `invoice_id`, `tenant_id`,
               CAST(`invoice_total` AS DECIMAL(14,2)) AS `invoice_total`,
               CAST(`invoice_issued_at` AS TIMESTAMP) AS `invoice_issued_at`,
               `days_overdue`, `tenant_status`, `tenant_status_cd_ingest`, `tenant_row_missing`,
               `overdue_by_fn`, `in_suspend_cutoff`, `in_schedule_driver`
          FROM v_snapshot_raw
        """
    )
    print(
        json.dumps(
            {"snapshot_read": SNAPSHOT_PATH, "rows": len(rows), "manifest": manifest}, indent=1
        )
    )

SNAPSHOT_ROWS = int(scalar("SELECT count(*) FROM v_snapshot"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quarantine plumbing
# MAGIC
# MAGIC One closed reason per rejected row, persisted **before** any threshold is evaluated, ledger rows
# MAGIC carrying this run's batch. `accounting` holds one entry per declared population and every one of
# MAGIC them is checked against the 5% independently.

# COMMAND ----------

accounting: dict[str, dict] = {}


def reason_case(rules: list[tuple[str, str]]) -> str:
    """First matching rule wins, so every rejected row carries exactly one reason."""
    for reason, _cond in rules:
        if reason not in REASONS:
            raise ValueError(f"{reason} is not in the unit's declared closed reason set {REASONS}")
    whens = " ".join(f"WHEN {cond} THEN {lit(reason)}" for reason, cond in rules)
    return f"CASE {whens} ELSE NULL END"


def persist_quarantine(view: str, source_table: str, population: str) -> int:
    """Write the rejects, then return how many there were. Nothing evaluates the halt before this.

    The ledger identity is `(ns, source_table, source_key, quarantine_reason, _batch_id)`, and
    `source_key` carries an occurrence ordinal. Both halves matter:

    * `_batch_id` is part of the identity, not a column the merge overwrites. A rejection that
      recurs on a later night becomes that night's own ledger row, so an earlier batch keeps the
      rows its own halt was evaluated on — tolerance item 3 wants the ledger scoped to a run's
      batch, which is only true if a later run cannot re-stamp an earlier run's row.
    * The ordinal makes the key unique inside one batch even when two *physical* rejected rows
      carry the same natural key and reason (two identical duplicate ingest rows, for instance).
      Every physical payload gets its own ledger row; without it the MERGE would either match
      several source rows to one target row and fail, or keep one payload and drop the rest while
      the accounting still counted them.

    A retry of the same batch is idempotent — same ns, key, reason and batch match, and the payload
    columns are refreshed — while a later batch appends.
    """
    n = int(scalar(f"SELECT count(*) FROM {view} WHERE `quarantine_reason` IS NOT NULL"))
    if n:
        spark.sql(
            f"""
            CREATE OR REPLACE TEMP VIEW v_quarantine_batch AS
            SELECT `quarantine_reason`, `raw_source_payload`, `detail`, `dictionary_ref`,
                   CASE WHEN `occurrence` = 1 THEN `source_key`
                        ELSE concat_ws('|#', `source_key`, CAST(`occurrence` AS STRING)) END
                     AS `ledger_key`
              FROM (
                SELECT `quarantine_reason`, `source_key`, `raw_source_payload`, `detail`,
                       `dictionary_ref`,
                       row_number() OVER (PARTITION BY `source_key`, `quarantine_reason`
                                          ORDER BY `raw_source_payload`, `detail`) AS `occurrence`
                  FROM {view} WHERE `quarantine_reason` IS NOT NULL
              )
            """
        )
        prepared = int(scalar("SELECT count(*) FROM v_quarantine_batch"))
        if prepared != n:
            raise AssertionError(
                f"quarantine ledger for {population} prepared {prepared} of {n} rejected rows"
            )
        spark.sql(
            f"""
            MERGE INTO {QUARANTINE} t
            USING v_quarantine_batch s
              ON t.`ns` = {NS_LIT} AND t.`source_table` = {lit(source_table)}
             AND t.`source_key` <=> s.`ledger_key`
             AND t.`quarantine_reason` = s.`quarantine_reason`
             AND t.`_batch_id` = {BATCH_LIT}
            WHEN MATCHED THEN UPDATE SET
              t.`raw_source_payload` = s.`raw_source_payload`,
              t.`detail` = s.`detail`,
              t.`dictionary_ref` = s.`dictionary_ref`,
              t.`population` = {lit(population)},
              t.`phase` = {lit(PHASE)},
              t.`_quarantined_at` = current_timestamp()
            WHEN NOT MATCHED THEN INSERT (
              `quarantine_reason`, `ns`, `source_table`, `source_key`, `raw_source_payload`,
              `detail`, `dictionary_ref`, `population`, `phase`, `_batch_id`, `_quarantined_at`
            ) VALUES (
              s.`quarantine_reason`, {NS_LIT}, {lit(source_table)}, s.`ledger_key`,
              s.`raw_source_payload`, s.`detail`, s.`dictionary_ref`, {lit(population)},
              {lit(PHASE)}, {BATCH_LIT}, current_timestamp()
            )
            """
        )
    return n


def quarantine_persisted(source_table: str, population: str) -> int:
    """How many ledger rows this batch actually holds, read back from the Delta table.

    The halt is evaluated on the accounting numbers; this is the proof those numbers are rows on
    disk and not just rows a view counted.
    """
    return int(
        scalar(
            f"""
            SELECT count(*) FROM {QUARANTINE}
             WHERE `ns` = {NS_LIT} AND `source_table` = {lit(source_table)}
               AND `population` = {lit(population)} AND `_batch_id` = {BATCH_LIT}
            """
        )
    )


def declare_population(
    name: str,
    source_rows: int,
    loaded_rows: int,
    quarantined_rows: int,
    ledger_source_table: str | None = None,
) -> None:
    """Declare a population, and prove its rejected count is on disk before the halt reads it.

    `quarantined_rows` is the number the 5% is evaluated on, so every one of those rows has to be a
    ledger row this batch actually wrote: a reject that is counted but not persisted is a reject the
    reviewer cannot see, and it was how the tenant duplicates used to be handled.
    """
    persisted = (
        quarantine_persisted(ledger_source_table, name) if ledger_source_table is not None else None
    )
    if persisted is not None:
        if persisted != int(quarantined_rows):
            raise AssertionError(
                f"{name}: {quarantined_rows} rejected rows are counted but {QUARANTINE} holds "
                f"{persisted} for batch {BATCH_ID} — the halt would read a number the ledger does "
                "not carry"
            )
    accounting[name] = {
        "basis": HALT_BASES[name],
        "source_rows": int(source_rows),
        "loaded_rows": int(loaded_rows),
        "quarantined_rows": int(quarantined_rows),
        "quarantine_ledger_rows_this_batch": persisted,
    }


def evaluate_halt() -> dict:
    """Tolerance item 5: every declared population, paired numerator and denominator, any one fires."""
    bases = {}
    for name, acc in accounting.items():
        if acc["loaded_rows"] + acc["quarantined_rows"] != acc["source_rows"]:
            raise AssertionError(f"quarantine accounting broken for {name}: {acc}")
        # The decision is integer arithmetic on the pair, and the percentage is for reading. A
        # population at 5.000001% rounds to 5.0 at four decimals, and a halt that decided on the
        # rounded number would not fire on a breach it had already measured.
        over_threshold = acc["quarantined_rows"] * 100.0 > HALT_PCT * acc["source_rows"]
        exact = (
            100.0 * acc["quarantined_rows"] / acc["source_rows"] if acc["source_rows"] else 0.0
        )
        rate = round(exact, 4)
        acc["rate_pct"] = rate
        bases[name] = {
            "basis": acc["basis"],
            "source_rows": acc["source_rows"],
            "loaded_rows": acc["loaded_rows"],
            "rejected_rows": acc["quarantined_rows"],
            "quarantine_ledger_rows_this_batch": acc["quarantine_ledger_rows_this_batch"],
            "rate_pct": rate,
            "rate_pct_unrounded": repr(exact),
            "threshold_pct": HALT_PCT,
            "decided_by": (
                "rejected_rows * 100 > threshold_pct * source_rows, on the unrounded pair; "
                "rate_pct is the rounded figure for reading and is not what the halt compares"
            ),
            "over_threshold": over_threshold,
        }
    over = {n: b for n, b in bases.items() if b["over_threshold"]}
    print(json.dumps(bases, indent=1))
    if over:
        raise AssertionError(
            "STOPA-QUARANTINE: quarantine rate exceeds "
            f"{HALT_PCT}% on {sorted(over)} — {json.dumps(over)}. Rejected rows are already "
            f"persisted in {QUARANTINE} for batch {BATCH_ID}; escalate rather than reporting green "
            "on the surviving population."
        )
    return bases

# COMMAND ----------

# MAGIC %md
# MAGIC # Phase `schedule` — `sp_schedule_dunning(TRUNC(SYSDATE))`
# MAGIC
# MAGIC The cursor is `SELECT id, tenant_id FROM invoices WHERE status_cd = 40 ORDER BY issued_at, id`
# MAGIC — no date filter. Per invoice: `attempt_no = NVL(MAX(attempt_no),0)+1` over the ingest attempt
# MAGIC population, the weekend shift on `TRUNC(p_as_of)`, and
# MAGIC `id = f_md5_uuid(invoice_id || TO_CHAR(attempt_no))`.
# MAGIC
# MAGIC The migrated `OW_BILLING.DUNNING_ATTEMPTS` rows and the rows this run schedules are judged and
# MAGIC loaded as **one** population, which is also the halt basis: the accounting identity then holds
# MAGIC on the whole table rather than on the newly scheduled slice.

# COMMAND ----------

if PHASE == "schedule":
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_ingest_attempts AS
        SELECT `id`, `tenant_id`, `invoice_id`, `attempt_no`, `scheduled_for`, `status_cd`
          FROM {bronze('dunning_attempts')} WHERE `ns` = {NS_LIT}
        """
    )
    # `NVL(MAX(attempt_no),0)+1` reads the source's own DUNNING_ATTEMPTS, which holds both the
    # migrated rows and every attempt earlier nights scheduled, so on night two an invoice gets
    # attempt 2. The basis here is that same population: the ingest rows plus this unit's own target
    # rows from **earlier** `as_of` values. Excluding this run's own `as_of` is what keeps a restart
    # of one night idempotent — the ids are then a function of `(ns, as_of, ingest state, earlier
    # nights)`, a rerun recomputes the same ids and changes nothing, and a genuinely later night
    # appends a new attempt instead of merging over the previous night's row. The `as_of` filter is
    # also why the lazy re-evaluation of this view after the MERGE is harmless: the rows this run
    # writes carry this run's `as_of` and can never enter its own basis.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_prior_night_attempts AS
        SELECT `invoice_id`, `attempt_no` FROM {full('dunning_attempts')}
         WHERE `ns` = {NS_LIT} AND `as_of` < to_date({AS_OF_LIT})
        """
    )
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_attempt_basis AS
        SELECT `invoice_id`, coalesce(max(`attempt_no`), 0) AS `basis` FROM (
          SELECT `invoice_id`, CAST(`attempt_no` AS BIGINT) AS `attempt_no` FROM v_ingest_attempts
          UNION ALL
          SELECT `invoice_id`, CAST(`attempt_no` AS BIGINT) AS `attempt_no`
            FROM v_prior_night_attempts
        ) GROUP BY `invoice_id`
        """
    )

    # BIGINT, and cast to the target's INT only once the row has passed judgement: computing the
    # candidate in INT would overflow before NUMERIC_OVERFLOW could reject it, so the reason code
    # would be unreachable exactly where it is needed.
    ATTEMPT_NO = "CAST(coalesce(b.`basis`, 0) AS BIGINT) + 1"
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_attempts_scheduled AS
        SELECT {f_md5_uuid(f"concat(s.`invoice_id`, CAST({ATTEMPT_NO} AS STRING))")} AS `id`,
               s.`tenant_id`, s.`invoice_id`, {ATTEMPT_NO} AS `attempt_no`,
               CAST(date_add(to_date({AS_OF_LIT}), {AS_OF_SHIFT}) AS TIMESTAMP) AS `scheduled_for`,
               {int(K['attempt_scheduled_status_cd'])} AS `status_cd`,
               CAST(coalesce(b.`basis`, 0) AS INT) AS `attempt_no_basis`,
               {lit(AS_OF_DOW)} AS `source_day_of_week`,
               {AS_OF_SHIFT} AS `weekend_shift_days`,
               CAST(to_date({AS_OF_LIT}) AS TIMESTAMP) AS `unshifted_scheduled_for`,
               s.`invoice_total`, s.`invoice_issued_at`, s.`days_overdue`, s.`overdue_by_fn`,
               s.`tenant_status`, s.`tenant_row_missing`, 'target-schedule' AS `_origin`
          FROM v_snapshot s LEFT JOIN v_attempt_basis b ON b.`invoice_id` = s.`invoice_id`
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_attempts_migrated AS
        SELECT a.`id`, a.`tenant_id`, a.`invoice_id`, CAST(a.`attempt_no` AS BIGINT) AS `attempt_no`,
               a.`scheduled_for`, a.`status_cd`,
               CAST(NULL AS INT) AS `attempt_no_basis`,
               CAST(NULL AS STRING) AS `source_day_of_week`,
               CAST(NULL AS INT) AS `weekend_shift_days`,
               CAST(NULL AS TIMESTAMP) AS `unshifted_scheduled_for`,
               i.`total` AS `invoice_total`, i.`issued_at` AS `invoice_issued_at`,
               datediff(to_date({AS_OF_LIT}), to_date(i.`issued_at`)) AS `days_overdue`,
               date_format(i.`issued_at`, {lit(K['date_compare_format'])})
                 < date_format({AS_OF_LIT}, {lit(K['date_compare_format'])}) AS `overdue_by_fn`,
               {DECODE_TENANT_STATUS} AS `tenant_status`,
               t.`id` IS NULL AS `tenant_row_missing`, 'source-migrated' AS `_origin`
          FROM v_ingest_attempts a
          LEFT JOIN v_invoices i ON i.`id` = a.`invoice_id`
          LEFT JOIN v_tenants t ON t.`id` = a.`tenant_id`
        """
    )
    spark.sql("CREATE OR REPLACE TEMP VIEW v_attempts AS SELECT * FROM v_attempts_migrated UNION ALL SELECT * FROM v_attempts_scheduled")

    # Judgement. First match wins, so exactly one closed reason per rejected row.
    #  * KEY_NULL      — a column of the declared MERGE key, or a NOT NULL source column, is null.
    #  * KEY_DUPLICATE — two rows on the same id, or on the source's uq_dunning_attempts
    #                    (invoice_id, attempt_no); MERGE cannot resolve either deterministically.
    #  * FK_ORPHAN     — fk_da_invoice / fk_da_tenant are mandatory in the source, so an attempt whose
    #                    invoice or tenant row is absent is a row the source's INSERT could not have
    #                    written: it raises ORA-02291 and WHEN OTHERS THEN NULL hides it.
    #  * CODE_UNKNOWN  — status_cd with no CODES('DUN_STATUS') row.
    #  * NUMERIC_OVERFLOW — a value that does not fit the declared target type. The attempt candidate
    #                    is `NVL(MAX(attempt_no),0)+1`, computed in BIGINT above, so an invoice whose
    #                    highest attempt is already INT_MAX produces a candidate outside the target's
    #                    INT and is rejected here before anything casts it: that path is exercised in
    #                    ns=dunning_edge. The money half of the rule cannot fire from bronze's own
    #                    DECIMAL(14,2) column and is measured rather than assumed.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_attempts_judged AS
        SELECT a.*,
               count(*) OVER (PARTITION BY a.`id`) AS `id_rows`,
               count(*) OVER (PARTITION BY a.`invoice_id`, a.`attempt_no`) AS `uq_rows`,
               i.`id` IS NULL AS `invoice_missing`,
               c.`code_val` IS NULL AS `status_unknown`
          FROM v_attempts a
          LEFT JOIN v_invoices i ON i.`id` = a.`invoice_id`
          LEFT JOIN (SELECT `code_val` FROM v_codes WHERE `code_type` = 'DUN_STATUS') c
                 ON c.`code_val` = a.`status_cd`
        """
    )
    ATTEMPT_RULES = [
        (
            "KEY_NULL",
            "`id` IS NULL OR `tenant_id` IS NULL OR `invoice_id` IS NULL OR `attempt_no` IS NULL "
            "OR `scheduled_for` IS NULL OR `status_cd` IS NULL",
        ),
        ("KEY_DUPLICATE", "`id_rows` > 1 OR `uq_rows` > 1"),
        ("FK_ORPHAN", "`invoice_missing` OR `tenant_row_missing`"),
        ("CODE_UNKNOWN", "`status_unknown`"),
        (
            "NUMERIC_OVERFLOW",
            "`attempt_no` > 2147483647 OR `attempt_no` < -2147483648 "
            "OR abs(coalesce(`invoice_total`, 0)) > 999999999999.99",
        ),
    ]
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_attempts_ledger AS
        SELECT {reason_case(ATTEMPT_RULES)} AS `quarantine_reason`,
               -- the physical row's own id closes the key: two ingest rows colliding on
               -- uq_dunning_attempts(invoice_id, attempt_no) are two rejected rows and each gets its
               -- own ledger row, which a key of (invoice_id, attempt_no, _origin) alone would merge
               -- into one.
               concat_ws('|', `invoice_id`, CAST(`attempt_no` AS STRING), `_origin`, `id`)
                 AS `source_key`,
               to_json(struct(`id`, `tenant_id`, `invoice_id`, `attempt_no`,
                              CAST(`scheduled_for` AS STRING) AS `scheduled_for`, `status_cd`,
                              `_origin`)) AS `raw_source_payload`,
               concat_ws('; ',
                 CASE WHEN `id_rows` > 1 THEN concat('id repeats ', CAST(`id_rows` AS STRING), ' times') END,
                 CASE WHEN `uq_rows` > 1 THEN 'uq_dunning_attempts(invoice_id, attempt_no) collision' END,
                 CASE WHEN `invoice_missing` THEN 'fk_da_invoice: no invoice row' END,
                 CASE WHEN `tenant_row_missing` THEN
                   'fk_da_tenant: no tenant row, so the source INSERT raises ORA-02291 and WHEN OTHERS THEN NULL hides it' END,
                 CASE WHEN `status_unknown` THEN concat('no CODES(DUN_STATUS) row for ', CAST(`status_cd` AS STRING)) END,
                 CASE WHEN `attempt_no` > 2147483647 OR `attempt_no` < -2147483648 THEN
                   concat('attempt candidate ', CAST(`attempt_no` AS STRING),
                          ' (NVL(MAX(attempt_no),0)+1 in BIGINT) is outside the INT the target column ',
                          'declares, so it is rejected before any cast') END,
                 CASE WHEN abs(coalesce(`invoice_total`, 0)) > 999999999999.99 THEN
                   concat('invoice total ', CAST(`invoice_total` AS STRING),
                          ' is outside DECIMAL(14,2)') END
               ) AS `detail`,
               'D-14, D-16, D-18, D-23, T12' AS `dictionary_ref`,
               *
          FROM v_attempts_judged
        """
    )
    attempt_rejects = persist_quarantine(
        "v_attempts_ledger", "OW_BILLING.DUNNING_ATTEMPTS", "dunning_attempts"
    )
    attempt_source_rows = int(scalar("SELECT count(*) FROM v_attempts"))
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_attempts_load AS
        SELECT * FROM v_attempts_ledger WHERE `quarantine_reason` IS NULL
        """
    )
    declare_population(
        "dunning_attempts",
        attempt_source_rows,
        int(scalar("SELECT count(*) FROM v_attempts_load")),
        attempt_rejects,
        ledger_source_table="OW_BILLING.DUNNING_ATTEMPTS",
    )
    HALT_RESULT = evaluate_halt()

# COMMAND ----------

if PHASE == "schedule":
    ATTEMPT_COLS = [c["name"] for c in TABLES["dunning_attempts"]["columns"]]
    # pk_codes is (code_type, code_val), so the lookup is single-valued; the aggregate is what Spark
    # requires of a correlated scalar subquery and does not widen it.
    status_desc = (
        "(SELECT max(`code_desc`) FROM v_codes WHERE `code_type` = 'DUN_STATUS' "
        "AND `code_val` = s.`status_cd`)"
    )
    select_load = f"""
        SELECT s.`id`, s.`tenant_id`, s.`invoice_id`,
               -- judged in BIGINT above; every surviving row is inside INT by NUMERIC_OVERFLOW
               CAST(s.`attempt_no` AS INT) AS `attempt_no`, s.`scheduled_for`,
               s.`status_cd`, {status_desc} AS `status`, to_date({AS_OF_LIT}) AS `as_of`,
               s.`attempt_no_basis`, s.`source_day_of_week`, s.`weekend_shift_days`,
               s.`unshifted_scheduled_for`, s.`invoice_total`, s.`invoice_issued_at`,
               s.`days_overdue`, s.`overdue_by_fn`, s.`tenant_status`,
               {NS_LIT} AS `ns`, s.`_origin`, {BATCH_LIT} AS `_batch_id`,
               current_timestamp() AS `_loaded_at`
          FROM v_attempts_load s
    """
    spark.sql(f"CREATE OR REPLACE TEMP VIEW v_attempts_final AS {select_load}")
    set_cols = ",\n              ".join(
        f"t.`{c}` = s.`{c}`" for c in ATTEMPT_COLS + ["_origin", "_batch_id", "_loaded_at"]
    )
    change_pred = " OR ".join(
        f"NOT (t.`{c}` <=> s.`{c}`)" for c in ATTEMPT_COLS if c not in ("id",)
    )
    merge_metrics = spark.sql(
        f"""
        MERGE INTO {full('dunning_attempts')} t
        USING v_attempts_final s ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
        WHEN MATCHED AND ({change_pred}) THEN UPDATE SET
              {set_cols}
        WHEN NOT MATCHED THEN INSERT *
        """
    ).collect()[0].asDict()
    print(json.dumps({k: str(v) for k, v in merge_metrics.items()}, indent=1))

    # Measurements, recomputed from the Delta target after the write.
    scheduled_by_run = int(
        scalar(
            f"""
            SELECT count(*) FROM {full('dunning_attempts')}
             WHERE `ns` = {NS_LIT} AND `_origin` = 'target-schedule' AND `as_of` = {AS_OF_LIT}
            """
        )
    )
    by_dow = {
        r[0]: int(r[1])
        for r in spark.sql(
            f"""
            SELECT coalesce(`source_day_of_week`, 'migrated'), count(*)
              FROM {full('dunning_attempts')} WHERE `ns` = {NS_LIT} GROUP BY 1 ORDER BY 1
            """
        ).collect()
    }
    shifted = {
        int(r[0] if r[0] is not None else -1): int(r[1])
        for r in spark.sql(
            f"""
            SELECT `weekend_shift_days`, count(*) FROM {full('dunning_attempts')}
             WHERE `ns` = {NS_LIT} AND `_origin` = 'target-schedule' GROUP BY 1 ORDER BY 1
            """
        ).collect()
    }
    phase1_summary = {
        "phase": "schedule",
        "source_entrypoint": "pkg_dunning.sp_schedule_dunning",
        "as_of": AS_OF,
        "as_of_day_of_week_english": AS_OF_DOW,
        "as_of_weekend_shift_days": AS_OF_SHIFT,
        "day_number_origin_probe": dow_probe,
        # D-10: g_last_run_dt and g_scheduled_cnt as explicit run-level output, not package state.
        "g_last_run_dt_equivalent": AS_OF,
        "scheduled_count": scheduled_by_run,
        "scheduled_count_note": (
            "the source's g_scheduled_cnt counts only INSERTs that did not raise; this count is "
            "every attempt actually written, and the attempts the source's handler would have "
            "swallowed are the quarantined rows below"
        ),
        "snapshot": manifest,
        "overdue_snapshot_rows": SNAPSHOT_ROWS,
        "merge_metrics": {k: str(v) for k, v in merge_metrics.items()},
        "attempts_by_source_day_of_week": by_dow,
        "attempts_by_weekend_shift_days": shifted,
        "attempts_moved_by_weekend_shift": sum(v for k, v in shifted.items() if k > 0),
        "swallowed_insert_exposure": {
            "fk_da_tenant_orphans": int(
                scalar(
                    "SELECT count(*) FROM v_attempts_ledger WHERE `_origin` = 'target-schedule' "
                    "AND `tenant_row_missing`"
                )
            ),
            "fk_da_invoice_orphans": int(
                scalar(
                    "SELECT count(*) FROM v_attempts_ledger WHERE `_origin` = 'source-migrated' "
                    "AND `invoice_missing`"
                )
            ),
            "uq_collisions": int(
                scalar("SELECT count(*) FROM v_attempts_ledger WHERE `uq_rows` > 1")
            ),
            "concurrency_exposed_attempts": scheduled_by_run,
            "concurrency_note": (
                "every attempt this run scheduled is exposed: attempt_no is NVL(MAX,0)+1 read with "
                "no lock and the id is a pure function of (invoice_id, attempt_no), so a concurrent "
                "source run computes the same id and one of the two INSERTs raises ORA-00001 into "
                "WHEN OTHERS THEN NULL. The target's job is max_concurrent_runs = 1 and its MERGE "
                "makes the second writer a no-op instead of a silent loss"
            ),
            "rerun_would_append": scheduled_by_run,
            "rerun_note": (
                "a source rerun on the same p_as_of appends this many more attempts (MAX+1 again); "
                "this port pins attempt_no to the ingest population, so its rerun is a no-op "
                "(DIV-RERUN-APPENDS, D-27)"
            ),
        },
        "outer_join": {
            "invoices_kept_with_no_tenant_row": int(
                scalar("SELECT count(*) FROM v_snapshot WHERE `tenant_row_missing`")
            ),
            "tenant_status_unknown": int(
                scalar("SELECT count(*) FROM v_snapshot WHERE `tenant_status` = 'UNKNOWN'")
            ),
            "same_day_invoices_scheduled_but_not_overdue_by_fn": int(
                scalar("SELECT count(*) FROM v_snapshot WHERE NOT `overdue_by_fn`")
            ),
        },
        "money": {
            "overdue_total_snapshot": str(
                scalar("SELECT coalesce(sum(`invoice_total`), 0) FROM v_snapshot")
            ),
            "scheduled_attempt_invoice_total": str(
                scalar(
                    f"""
                    SELECT coalesce(sum(`invoice_total`), 0) FROM {full('dunning_attempts')}
                     WHERE `ns` = {NS_LIT} AND `_origin` = 'target-schedule' AND `as_of` = {AS_OF_LIT}
                    """
                )
            ),
            "quarantined_rows": attempt_rejects,
        },
        "accounting": accounting,
    }

# COMMAND ----------

# MAGIC %md
# MAGIC # Phase `suspend` — `sp_suspend_overdue(TRUNC(SYSDATE))`
# MAGIC
# MAGIC Driven **only** by the snapshot phase 1 persisted. Three writes, in the source's order: tenant
# MAGIC status (to this unit's own `ow_tp.silver.tenants`), the shared subscriptions columns, then the
# MAGIC suspension notification with the source's `NOT EXISTS` guard.
# MAGIC
# MAGIC `IF v_active > 0` counts `TENANTS` rows at `status_cd = 10` — the *current* state, which the
# MAGIC sweep itself changes. The target reads its own `ow_tp.silver.tenants` state first and falls back
# MAGIC to ingest for a tenant it has not loaded yet, so a tenant an earlier run suspended is skipped
# MAGIC exactly as the source skips it (D-27's recompute-from-own-effect shape, checked for this unit).
# MAGIC That read is taken **once**, before the first write, and held as literals: a temp view over the
# MAGIC target would be re-evaluated by the statements below, and the subscription and notification
# MAGIC steps would then read the suspension the tenant `MERGE` had just written and skip every tenant
# MAGIC they exist to act on. The notification guard's `NOT EXISTS` population is frozen the same way.

# COMMAND ----------

if PHASE == "suspend":
    # The source's cursor: SELECT DISTINCT i.tenant_id FROM invoices WHERE status_cd = 40 AND the
    # inclusive 14-day string compare. A candidate whose tenant row is missing stays in the cursor
    # and is then skipped by IF v_active > 0, which is measured, not filtered away.
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_sweep_candidates AS
        SELECT `tenant_id`, count(*) AS `overdue_invoices`, min(`invoice_issued_at`) AS `first_overdue_issued_at`
          FROM v_snapshot WHERE `in_suspend_cutoff` GROUP BY `tenant_id`
        """
    )
    # `IF v_active > 0` reads TENANTS as it stands when the sweep begins, so this reads the target's
    # own tenant status once, here, and holds it as literals. A temp view over the table would be
    # re-evaluated by every later statement, and the tenant MERGE further down is such a statement:
    # the subscription and notification steps would then read the status this very sweep had just
    # written and skip the tenants they exist to act on.
    candidate_ids = [
        r[0]
        for r in spark.sql(
            "SELECT `tenant_id` FROM v_sweep_candidates WHERE `tenant_id` IS NOT NULL"
        ).collect()
    ]
    frozen_status = (
        spark.sql(
            f"""
            SELECT `id`, `status_cd` FROM {full('tenants')}
             WHERE `ns` = {NS_LIT} AND `id` IN ({", ".join(lit(i) for i in candidate_ids)})
            """
        ).collect()
        if candidate_ids
        else []
    )
    frozen_values = ", ".join(
        f"({lit(r['id'])}, {'CAST(NULL AS INT)' if r['status_cd'] is None else int(r['status_cd'])})"
        for r in frozen_status
    )
    spark.sql(
        "CREATE OR REPLACE TEMP VIEW v_silver_tenants_current AS "
        + (
            f"SELECT * FROM VALUES {frozen_values} AS v(`id`, `status_cd`)"
            if frozen_values
            else "SELECT CAST(NULL AS STRING) AS `id`, CAST(NULL AS INT) AS `status_cd` WHERE false"
        )
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_tenant_sweep AS
        SELECT t.`id`, t.`name`, t.`tax_exempt_yn`,
               t.`status_cd` AS `status_cd_ingest`,
               coalesce(s.`status_cd`, t.`status_cd`) AS `status_cd_at_run`,
               c.`tenant_id` IS NOT NULL AS `sweep_candidate`,
               coalesce(c.`overdue_invoices`, 0) AS `overdue_invoices`,
               c.`first_overdue_issued_at`,
               c.`tenant_id` IS NOT NULL
                 AND coalesce(s.`status_cd`, t.`status_cd`) = {int(K['active_tenant_status_cd'])}
                 AS `newly_suspended`,
               t.`id_rows`
          FROM v_tenants t
          LEFT JOIN v_silver_tenants_current s ON s.`id` = t.`id`
          LEFT JOIN v_sweep_candidates c ON c.`tenant_id` = t.`id`
        """
    )
    NEW_STATUS = (
        f"CASE WHEN `newly_suspended` THEN {int(K['suspended_tenant_status_cd'])} "
        "ELSE `status_cd_at_run` END"
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_tenants_computed AS
        SELECT `id`, `name`, `tax_exempt_yn`, {NEW_STATUS} AS `status_cd`, `status_cd_ingest`,
               `status_cd_at_run`, `sweep_candidate`, `newly_suspended`,
               ({NEW_STATUS} = {int(K['suspended_tenant_status_cd'])}
                 AND `status_cd_ingest` = {int(K['active_tenant_status_cd'])}) AS `suspended_by_sweep`,
               (`sweep_candidate` AND NOT (`status_cd_ingest` <=> {int(K['active_tenant_status_cd'])}))
                 AS `skipped_inactive_at_ingest`,
               `overdue_invoices`, `first_overdue_issued_at`, `id_rows`
          FROM v_tenant_sweep
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_tenants_judged AS
        SELECT t.*, c.`code_val` IS NULL AS `status_unknown`
          FROM v_tenants_computed t
          LEFT JOIN (SELECT `code_val` FROM v_codes WHERE `code_type` = 'TENANT_STATUS') c
                 ON c.`code_val` = t.`status_cd`
        """
    )
    TENANT_RULES = [
        ("KEY_NULL", "`id` IS NULL OR `status_cd` IS NULL"),
        ("KEY_DUPLICATE", "`id_rows` > 1"),
        ("CODE_UNKNOWN", "`status_unknown`"),
    ]
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_tenants_ledger AS
        SELECT {reason_case(TENANT_RULES)} AS `quarantine_reason`, `id` AS `source_key`,
               to_json(struct(`id`, `name`, `tax_exempt_yn`, `status_cd_ingest`)) AS `raw_source_payload`,
               concat_ws('; ',
                 CASE WHEN `id_rows` > 1 THEN concat('tenant id repeats ', CAST(`id_rows` AS STRING),
                      ' times in ow_tp.bronze.tenants, impossible under the source primary key') END,
                 CASE WHEN `status_unknown` THEN concat('no CODES(TENANT_STATUS) row for ',
                      CAST(`status_cd` AS STRING)) END
               ) AS `detail`,
               'D-16, D-30' AS `dictionary_ref`, *
          FROM v_tenants_judged
        """
    )
    tenant_rejects = persist_quarantine("v_tenants_ledger", "OW_BILLING.TENANTS", "tenants")
    # The outer join collapses a repeated tenant id to one row, and that row is rejected as
    # KEY_DUPLICATE above. The physical rows it collapsed are rejects too — they are counted in the
    # tenants accounting below — so each one gets its own ledger row carrying its own payload,
    # keyed by its ordinal. Counting a reject the ledger does not hold would put the halt on a
    # number no reviewer can read back out of the table.
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_tenant_collapsed_ledger AS
        SELECT 'KEY_DUPLICATE' AS `quarantine_reason`,
               concat_ws('|', `id`, CAST(`id_seq` AS STRING)) AS `source_key`,
               to_json(struct(`id`, `name`, `tax_exempt_yn`, `status_cd`, `id_seq`, `id_rows`))
                 AS `raw_source_payload`,
               concat('tenant id repeats ', CAST(`id_rows` AS STRING),
                      ' times in ow_tp.bronze.tenants, impossible under the source primary key; ',
                      'this is the physical row at ordinal ', CAST(`id_seq` AS STRING),
                      ', collapsed before the sweep join and rejected on its own payload')
                 AS `detail`,
               'D-16, D-30' AS `dictionary_ref`
          FROM v_tenants_raw WHERE `id_rows` > 1 AND `id_seq` > 1
        """
    )
    tenant_collapsed_rejects = persist_quarantine(
        "v_tenant_collapsed_ledger", "OW_BILLING.TENANTS", "tenants"
    )
    tenant_source_rows = int(scalar(f"SELECT count(*) FROM {bronze('tenants')} WHERE `ns` = {NS_LIT}"))
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_tenants_load AS
        SELECT * FROM v_tenants_ledger WHERE `quarantine_reason` IS NULL
        """
    )
    tenant_loaded = int(scalar("SELECT count(*) FROM v_tenants_load"))
    tenant_dupes_collapsed = tenant_source_rows - int(scalar("SELECT count(*) FROM v_tenants_judged"))
    if tenant_collapsed_rejects != tenant_dupes_collapsed:
        raise AssertionError(
            f"{tenant_dupes_collapsed} bronze tenant rows are collapsed by the id de-duplication but "
            f"{tenant_collapsed_rejects} were written to the ledger"
        )
    declare_population(
        "tenants",
        tenant_source_rows,
        tenant_loaded,
        tenant_rejects + tenant_collapsed_rejects,
        ledger_source_table="OW_BILLING.TENANTS",
    )

# COMMAND ----------

if PHASE == "suspend":
    # The shared table. Everything about this cell is deliberately narrow: it reads the rows the
    # source's UPDATE would match, refuses to proceed on state it cannot attribute to a merged unit,
    # captures a hash of every column it is not allowed to write, updates only status_cd and
    # suspended_on on matched rows, and then proves those hashes did not move.
    SUBS = full("subscriptions")
    sub_cols = [f.name for f in spark.table(SUBS).schema.fields]
    other_cols = [c for c in sub_cols if c not in SHARED_UPDATABLE]
    other_struct = ", ".join(f"`{c}`" for c in other_cols)
    # The same struct, qualified, for the join below: v_tenants_load carries columns of its own that
    # share these names. `struct(s.`c`)` and `struct(`c`)` name their fields identically, so the two
    # hashes are comparable.
    other_struct_s = ", ".join(f"s.`{c}`" for c in other_cols)
    for c in SHARED_UPDATABLE:
        if c not in sub_cols:
            raise AssertionError(f"{SUBS} has no column {c!r}: the D-30 column list does not fit")

    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_subs_swept_tenants AS
        SELECT s.`id`, s.`tenant_id`, s.`status_cd`, s.`suspended_on`, s.`_origin`, s.`_batch_id`,
               md5(to_json(struct({other_struct_s}))) AS `other_hash_before`
          FROM {SUBS} s JOIN v_tenants_load t ON t.`id` = s.`tenant_id`
         WHERE s.`ns` = {NS_LIT} AND t.`newly_suspended`
        """
    )
    origins_in = "(" + ", ".join(lit(o) for o in RECOGNISED_ORIGINS) + ")"
    unattributable = spark.sql(
        f"""
        SELECT `id`, `tenant_id`, `_origin`, `_batch_id`, `status_cd` FROM v_subs_swept_tenants
         WHERE `_origin` IS NULL OR `_origin` NOT IN {origins_in}
            OR `_batch_id` IS NULL OR `_batch_id` = ''
        """
    ).collect()
    if unattributable:
        raise AssertionError(
            "ACC-COLLISION / D-30: "
            f"{len(unattributable)} row(s) in {SUBS} (ns={NS}) belonging to a tenant this sweep "
            f"touches cannot be attributed to a merged unit (recognised _origin values "
            f"{RECOGNISED_ORIGINS} with a non-empty _batch_id). Nothing was written to that table. "
            "Escalate centrally rather than resolving it here. Rows: "
            + json.dumps([r.asDict() for r in unattributable], default=str)
        )
    attribution = {
        r[0]: int(r[1])
        for r in spark.sql(
            "SELECT `_origin`, count(*) FROM v_subs_swept_tenants GROUP BY 1 ORDER BY 1"
        ).collect()
    }

    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_subs_updates AS
        SELECT `id`, `tenant_id`, `status_cd` AS `status_cd_before`, `suspended_on` AS `suspended_on_before`,
               `_origin`, `_batch_id`, `other_hash_before`,
               {int(K['suspended_subscription_status_cd'])} AS `new_status_cd`,
               CAST(to_date({AS_OF_LIT}) AS TIMESTAMP) AS `new_suspended_on`
          FROM v_subs_swept_tenants
         WHERE `status_cd` = {int(K['active_subscription_status_cd'])}
        """
    )
    SUB_RULES = [("KEY_NULL", "`id` IS NULL")]
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_subs_ledger AS
        SELECT {reason_case(SUB_RULES)} AS `quarantine_reason`, `id` AS `source_key`,
               to_json(struct(`id`, `tenant_id`, `status_cd_before`, `_origin`)) AS `raw_source_payload`,
               'shared-table match key null, so the MERGE could not be made idempotent' AS `detail`,
               'D-30, D-14' AS `dictionary_ref`, *
          FROM v_subs_updates
        """
    )
    sub_rejects = persist_quarantine(
        "v_subs_ledger", "OW_BILLING.SUBSCRIPTIONS", "subscriptions_swept"
    )
    sub_matched = int(scalar("SELECT count(*) FROM v_subs_updates"))
    before_rows = [
        r.asDict()
        for r in spark.sql(
            """
            SELECT `id`, `tenant_id`, `status_cd_before`,
                   date_format(`suspended_on_before`, 'yyyy-MM-dd HH:mm:ss') AS `suspended_on_before`,
                   `_origin`, `_batch_id`, `other_hash_before`
              FROM v_subs_ledger WHERE `quarantine_reason` IS NULL ORDER BY `id`
            """
        ).collect()
    ]
    left_alone = {
        str(r[0]): int(r[1])
        for r in spark.sql(
            "SELECT CAST(`status_cd` AS STRING), count(*) FROM v_subs_swept_tenants "
            f"WHERE `status_cd` <> {int(K['active_subscription_status_cd'])} GROUP BY 1 ORDER BY 1"
        ).collect()
    }

    declare_population(
        "subscriptions_swept",
        sub_matched,
        len(before_rows),
        sub_rejects,
        ledger_source_table="OW_BILLING.SUBSCRIPTIONS",
    )

    # The three subscription counts this unit's own tenant rows carry are **state** counts over the
    # end state this run leaves, not counts of what this run changed: a rerun updates nothing, so a
    # delta count would fall back to zero and the rerun would not be a no-op (ACC-IDEM). The planned
    # end state is the live shared table with this run's matched updates applied.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_subs_planned AS
        SELECT s.`tenant_id`, s.`id`,
               CASE WHEN u.`id` IS NOT NULL THEN {int(K['suspended_subscription_status_cd'])}
                    ELSE s.`status_cd` END AS `planned_status_cd`,
               CASE WHEN u.`id` IS NOT NULL THEN CAST(to_date({AS_OF_LIT}) AS TIMESTAMP)
                    ELSE s.`suspended_on` END AS `planned_suspended_on`
          FROM {SUBS} s LEFT JOIN v_subs_updates u ON u.`id` = s.`id`
         WHERE s.`ns` = {NS_LIT}
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_subs_planned_agg AS
        SELECT `tenant_id`,
               count_if(`planned_status_cd` = {int(K['suspended_subscription_status_cd'])}
                        AND `planned_suspended_on` <=> CAST(to_date({AS_OF_LIT}) AS TIMESTAMP))
                 AS `suspended_on_as_of`,
               count_if(`planned_status_cd` = {int(K['suspended_subscription_status_cd'])}
                        AND NOT (`planned_suspended_on` <=> CAST(to_date({AS_OF_LIT}) AS TIMESTAMP)))
                 AS `left_suspended`,
               count_if(`planned_status_cd` = {int(K['cancelled_subscription_status_cd'])})
                 AS `left_cancelled`
          FROM v_subs_planned GROUP BY 1
        """
    )

# COMMAND ----------

if PHASE == "suspend":
    # The notification INSERT, guard included. NOT EXISTS is evaluated against the notification
    # population as it stands *before* this run writes: the migrated ingest rows plus whatever this
    # namespace already holds. Suppressed rows are counted, not dropped silently.
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_ingest AS
        SELECT `id`, `tenant_id`, `kind_cd`, `sent_at` FROM {bronze('notifications')}
         WHERE `ns` = {NS_LIT}
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_existing AS
        SELECT `id`, `tenant_id`, `kind_cd`, `sent_at` FROM v_notifications_ingest
        UNION
        SELECT `id`, `tenant_id`, `kind_cd`, `sent_at` FROM {full('notifications')}
         WHERE `ns` = {NS_LIT}
        """
    )
    NOTIF_SENT_AT = f"CAST(to_date({AS_OF_LIT}) AS TIMESTAMP)"
    NOTIF_ID = f_md5_uuid(
        f"concat(t.`id`, 'suspension', date_format(to_date({AS_OF_LIT}), 'yyyy-MM-dd'))"
    )
    sweep_notifications = spark.sql(
        f"""
        SELECT {NOTIF_ID} AS `id`, t.`id` AS `tenant_id`,
               {int(K['notification_kind_suspension_cd'])} AS `kind_cd`,
               {NOTIF_SENT_AT} AS `sent_at`, t.`status_cd_at_run` AS `tenant_status_before`,
               EXISTS (SELECT 1 FROM v_notifications_existing n
                        WHERE n.`tenant_id` = t.`id`
                          AND n.`kind_cd` = {int(K['notification_kind_suspension_cd'])}
                          AND n.`sent_at` = {NOTIF_SENT_AT}) AS `suppressed_by_not_exists`
          FROM v_tenants_load t WHERE t.`newly_suspended`
        """
    ).collect()
    # Frozen as literals for the same reason the tenant status above is: the guard is the source's
    # NOT EXISTS over the notification population *before* this run writes, and a view holding that
    # subquery would be re-evaluated after the write, when every row it produced suppresses itself.
    spark.sql(
        "CREATE OR REPLACE TEMP VIEW v_notifications_sweep AS "
        + (
            "SELECT * FROM VALUES "
            + ", ".join(
                "("
                + ", ".join(
                    [
                        lit(r["id"]),
                        lit(r["tenant_id"]),
                        str(int(r["kind_cd"])),
                        f"CAST({lit(r['sent_at'].strftime('%Y-%m-%d %H:%M:%S'))} AS TIMESTAMP)",
                        "CAST(NULL AS INT)"
                        if r["tenant_status_before"] is None
                        else str(int(r["tenant_status_before"])),
                        "true" if r["suppressed_by_not_exists"] else "false",
                    ]
                )
                + ")"
                for r in sweep_notifications
            )
            + " AS v(`id`, `tenant_id`, `kind_cd`, `sent_at`, `tenant_status_before`,"
            " `suppressed_by_not_exists`)"
            if sweep_notifications
            else """
            SELECT CAST(NULL AS STRING) AS `id`, CAST(NULL AS STRING) AS `tenant_id`,
                   CAST(NULL AS INT) AS `kind_cd`, CAST(NULL AS TIMESTAMP) AS `sent_at`,
                   CAST(NULL AS INT) AS `tenant_status_before`,
                   CAST(NULL AS BOOLEAN) AS `suppressed_by_not_exists` WHERE false
            """
        )
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_all AS
        SELECT `id`, `tenant_id`, `kind_cd`, `sent_at`, CAST(NULL AS INT) AS `tenant_status_before`,
               false AS `written_by_sweep`, false AS `suppressed_by_not_exists`,
               'source-migrated' AS `_origin`
          FROM v_notifications_ingest
        UNION ALL
        SELECT `id`, `tenant_id`, `kind_cd`, `sent_at`, `tenant_status_before`,
               true AS `written_by_sweep`, `suppressed_by_not_exists`, 'target-suspension' AS `_origin`
          FROM v_notifications_sweep WHERE NOT `suppressed_by_not_exists`
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_judged AS
        SELECT n.*, count(*) OVER (PARTITION BY n.`id`) AS `id_rows`,
               count(*) OVER (PARTITION BY n.`tenant_id`, n.`kind_cd`, n.`sent_at`) AS `uq_rows`,
               t.`id` IS NULL AS `tenant_row_missing`,
               c.`code_val` IS NULL AS `kind_unknown`
          FROM v_notifications_all n
          LEFT JOIN v_tenants t ON t.`id` = n.`tenant_id`
          LEFT JOIN (SELECT `code_val` FROM v_codes WHERE `code_type` = 'NOTIF_KIND') c
                 ON c.`code_val` = n.`kind_cd`
        """
    )
    NOTIF_RULES = [
        ("KEY_NULL", "`id` IS NULL OR `tenant_id` IS NULL OR `kind_cd` IS NULL OR `sent_at` IS NULL"),
        ("KEY_DUPLICATE", "`id_rows` > 1 OR `uq_rows` > 1"),
        ("FK_ORPHAN", "`tenant_row_missing`"),
        ("CODE_UNKNOWN", "`kind_unknown`"),
    ]
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_ledger AS
        SELECT {reason_case(NOTIF_RULES)} AS `quarantine_reason`, `id` AS `source_key`,
               to_json(struct(`id`, `tenant_id`, `kind_cd`, CAST(`sent_at` AS STRING) AS `sent_at`,
                              `_origin`)) AS `raw_source_payload`,
               concat_ws('; ',
                 CASE WHEN `id_rows` > 1 THEN 'pk_notifications collision' END,
                 CASE WHEN `uq_rows` > 1 THEN 'uq_notifications(tenant_id, kind_cd, sent_at) collision' END,
                 CASE WHEN `tenant_row_missing` THEN 'fk_notif_tenant: no tenant row' END,
                 CASE WHEN `kind_unknown` THEN concat('no CODES(NOTIF_KIND) row for ',
                      CAST(`kind_cd` AS STRING)) END
               ) AS `detail`,
               'D-14, D-16' AS `dictionary_ref`, *
          FROM v_notifications_judged
        """
    )
    notif_rejects = persist_quarantine(
        "v_notifications_ledger", "OW_BILLING.NOTIFICATIONS", "notifications"
    )
    notif_source_rows = int(scalar("SELECT count(*) FROM v_notifications_all"))
    spark.sql(
        """
        CREATE OR REPLACE TEMP VIEW v_notifications_load AS
        SELECT * FROM v_notifications_ledger WHERE `quarantine_reason` IS NULL
        """
    )
    declare_population(
        "notifications",
        notif_source_rows,
        int(scalar("SELECT count(*) FROM v_notifications_load")),
        notif_rejects,
    )
    # Every one of this phase's four populations is now judged and its rejects persisted, so the
    # threshold is evaluated on all of them before a single row is written.
    HALT_RESULT = evaluate_halt()

# COMMAND ----------

if PHASE == "suspend":
    # Writes, in the source's own order: UPDATE TENANTS, then UPDATE SUBSCRIPTIONS, then the
    # notification INSERT. Nothing above this cell wrote a row to a target table.
    tenant_status_desc = (
        "(SELECT max(`code_desc`) FROM v_codes WHERE `code_type` = 'TENANT_STATUS' "
        "AND `code_val` = s.`status_cd`)"
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_tenants_final AS
        SELECT s.`id`, s.`name`, s.`tax_exempt_yn`, s.`status_cd`,
               {tenant_status_desc} AS `status`, s.`status_cd_ingest`, to_date({AS_OF_LIT}) AS `as_of`,
               s.`sweep_candidate`, s.`suspended_by_sweep`, s.`skipped_inactive_at_ingest`,
               CAST(s.`overdue_invoices` AS INT) AS `overdue_invoices`, s.`first_overdue_issued_at`,
               CAST(coalesce(p.`suspended_on_as_of`, 0) AS INT) AS `subscriptions_suspended`,
               CAST(coalesce(p.`left_suspended`, 0) AS INT) AS `subscriptions_left_suspended`,
               CAST(coalesce(p.`left_cancelled`, 0) AS INT) AS `subscriptions_left_cancelled`,
               {NS_LIT} AS `ns`, 'source-migrated' AS `_origin`, {BATCH_LIT} AS `_batch_id`,
               current_timestamp() AS `_loaded_at`
          FROM v_tenants_load s
          LEFT JOIN v_subs_planned_agg p ON p.`tenant_id` = s.`id`
        """
    )
    TENANT_COLS = [c["name"] for c in TABLES["tenants"]["columns"]]
    t_set = ",\n              ".join(
        f"t.`{c}` = s.`{c}`" for c in TENANT_COLS + ["_origin", "_batch_id", "_loaded_at"]
    )
    t_change = " OR ".join(f"NOT (t.`{c}` <=> s.`{c}`)" for c in TENANT_COLS if c != "id")
    tenant_metrics = (
        spark.sql(
            f"""
            MERGE INTO {full('tenants')} t
            USING v_tenants_final s ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
            WHEN MATCHED AND ({t_change}) THEN UPDATE SET
                  {t_set}
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        .collect()[0]
        .asDict()
    )

    # The shared table, second, exactly as sp_suspend_overdue orders it. One statement, matched-only,
    # two columns, and the hash of every other column is re-read afterwards to prove they held.
    sub_merge_metrics: dict = {}
    if before_rows:
        sub_merge_metrics = (
            spark.sql(
                f"""
                MERGE INTO {SUBS} t
                USING (SELECT * FROM v_subs_ledger WHERE `quarantine_reason` IS NULL) s
                   ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
                WHEN MATCHED AND (NOT (t.`status_cd` <=> s.`new_status_cd`)
                                  OR NOT (t.`suspended_on` <=> s.`new_suspended_on`)) THEN UPDATE SET
                      t.`status_cd` = s.`new_status_cd`,
                      t.`suspended_on` = s.`new_suspended_on`
                """
            )
            .collect()[0]
            .asDict()
        )
        print(json.dumps({k: str(v) for k, v in sub_merge_metrics.items()}, indent=1))
    else:
        print(
            "no ow_tp.silver.subscriptions row matched this sweep: no MERGE issued against the "
            "shared table at all"
        )

    ids_lit = "(" + ", ".join(lit(r["id"]) for r in before_rows) + ")" if before_rows else None
    after_rows = (
        [
            r.asDict()
            for r in spark.sql(
                f"""
                SELECT `id`, `status_cd`,
                       date_format(`suspended_on`, 'yyyy-MM-dd HH:mm:ss') AS `suspended_on`,
                       md5(to_json(struct({other_struct}))) AS `other_hash_after`
                  FROM {SUBS} WHERE `ns` = {NS_LIT} AND `id` IN {ids_lit} ORDER BY `id`
                """
            ).collect()
        ]
        if ids_lit
        else []
    )
    after_by_id = {r["id"]: r for r in after_rows}
    shared_evidence = []
    for b in before_rows:
        a = after_by_id.get(b["id"])
        if a is None:
            raise AssertionError(f"subscription {b['id']} vanished from {SUBS}: this unit never deletes")
        if b["other_hash_before"] != a["other_hash_after"]:
            raise AssertionError(
                f"D-30 violation: columns outside {SHARED_UPDATABLE} changed on subscription "
                f"{b['id']} ({other_cols})"
            )
        if int(a["status_cd"]) != int(K["suspended_subscription_status_cd"]):
            raise AssertionError(f"subscription {b['id']} did not reach status 20 after the sweep")
        shared_evidence.append(
            {
                "id": b["id"],
                "tenant_id": b["tenant_id"],
                "status_cd_before": int(b["status_cd_before"]),
                "status_cd_after": int(a["status_cd"]),
                "suspended_on_before": b["suspended_on_before"],
                "suspended_on_after": a["suspended_on"],
                "_origin_preserved": b["_origin"],
                "_batch_id_preserved": b["_batch_id"],
                "other_columns_hash_before": b["other_hash_before"],
                "other_columns_hash_after": a["other_hash_after"],
                "other_columns_unchanged": True,
            }
        )

    notif_kind_desc = (
        "(SELECT max(`code_desc`) FROM v_codes WHERE `code_type` = 'NOTIF_KIND' "
        "AND `code_val` = s.`kind_cd`)"
    )
    spark.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW v_notifications_final AS
        SELECT s.`id`, s.`tenant_id`, s.`kind_cd`, s.`sent_at`, {notif_kind_desc} AS `kind`,
               to_date({AS_OF_LIT}) AS `as_of`, s.`written_by_sweep`, s.`tenant_status_before`,
               {NS_LIT} AS `ns`, s.`_origin`, {BATCH_LIT} AS `_batch_id`,
               current_timestamp() AS `_loaded_at`
          FROM v_notifications_load s
        """
    )
    NOTIF_COLS = [c["name"] for c in TABLES["notifications"]["columns"]]
    n_set = ",\n              ".join(
        f"t.`{c}` = s.`{c}`" for c in NOTIF_COLS + ["_origin", "_batch_id", "_loaded_at"]
    )
    n_change = " OR ".join(f"NOT (t.`{c}` <=> s.`{c}`)" for c in NOTIF_COLS if c != "id")
    notif_metrics = (
        spark.sql(
            f"""
            MERGE INTO {full('notifications')} t
            USING v_notifications_final s ON t.`id` = s.`id` AND t.`ns` = {NS_LIT}
            WHEN MATCHED AND ({n_change}) THEN UPDATE SET
                  {n_set}
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        .collect()[0]
        .asDict()
    )
    print(
        json.dumps(
            {
                "tenants": {k: str(v) for k, v in tenant_metrics.items()},
                "notifications": {k: str(v) for k, v in notif_metrics.items()},
            },
            indent=1,
        )
    )

# COMMAND ----------

if PHASE == "suspend":
    # Measurements, recomputed from the Delta targets after the writes. Every one of them is a count
    # over a population this run actually looked at; where a population is empty in this namespace it
    # is reported as zero and the recon report says a zero here is not a detection.
    swept = int(
        scalar(
            f"SELECT count(*) FROM {full('tenants')} WHERE `ns` = {NS_LIT} "
            f"AND `suspended_by_sweep` AND `_batch_id` = {BATCH_LIT}"
        )
    )
    swept_ever = int(
        scalar(f"SELECT count(*) FROM {full('tenants')} WHERE `ns` = {NS_LIT} AND `suspended_by_sweep`")
    )
    candidates = int(scalar("SELECT count(*) FROM v_sweep_candidates"))
    candidates_no_row = int(
        scalar(
            "SELECT count(*) FROM v_sweep_candidates c LEFT JOIN v_tenants t ON t.`id` = c.`tenant_id` "
            "WHERE t.`id` IS NULL"
        )
    )
    skipped_inactive = int(
        scalar(
            f"SELECT count(*) FROM {full('tenants')} WHERE `ns` = {NS_LIT} AND `skipped_inactive_at_ingest`"
        )
    )
    skipped_already_suspended_at_run = int(
        scalar(
            "SELECT count(*) FROM v_tenants_computed WHERE `sweep_candidate` AND NOT `newly_suspended`"
        )
    )
    # ANOM-NOTIFICATION-SIDE-EFFECT, measured on both shapes it can take.
    later_as_of_candidates = int(
        scalar(
            f"""
            SELECT count(DISTINCT s.`tenant_id`) FROM v_snapshot s
              JOIN {full('tenants')} t ON t.`id` = s.`tenant_id` AND t.`ns` = {NS_LIT}
             WHERE NOT s.`in_suspend_cutoff` AND t.`status_cd` = {int(K['active_tenant_status_cd'])}
            """
        )
    )
    second_notification_population = int(
        scalar(
            f"""
            SELECT count(DISTINCT t.`id`) FROM {full('tenants')} t
              JOIN {full('notifications')} n ON n.`tenant_id` = t.`id` AND n.`ns` = {NS_LIT}
             WHERE t.`ns` = {NS_LIT} AND t.`status_cd` = {int(K['active_tenant_status_cd'])}
               AND n.`kind_cd` = {int(K['notification_kind_suspension_cd'])}
               AND n.`sent_at` <> CAST(to_date({AS_OF_LIT}) AS TIMESTAMP)
            """
        )
    )
    # Measured, not asserted: how many of this sweep's notifications a legacy rerun on the *same*
    # p_as_of would still add, evaluated the way the source's NOT EXISTS would evaluate it against
    # the notification population as it now stands.
    rerun_would_add = int(
        scalar(
            f"""
            SELECT count(*) FROM v_notifications_sweep s
             WHERE NOT EXISTS (
                   SELECT 1 FROM {full('notifications')} n
                    WHERE n.`ns` = {NS_LIT} AND n.`tenant_id` = s.`tenant_id`
                      AND n.`kind_cd` = {int(K['notification_kind_suspension_cd'])}
                      AND n.`sent_at` = CAST(to_date({AS_OF_LIT}) AS TIMESTAMP))
            """
        )
    )
    phase2_summary = {
        "phase": "suspend",
        "source_entrypoint": "pkg_dunning.sp_suspend_overdue",
        "as_of": AS_OF,
        "suspend_cutoff_date": str(
            scalar(f"SELECT date_sub(to_date({AS_OF_LIT}), {int(K['suspend_cutoff_days'])})")
        ),
        "snapshot_read": {"path": SNAPSHOT_PATH, "rows": SNAPSHOT_ROWS, "manifest": manifest},
        "sweep": {
            "candidate_tenants": candidates,
            "candidates_with_no_tenant_row": candidates_no_row,
            "tenants_swept": swept,
            "tenants_suspended_by_a_sweep_in_this_namespace_including_earlier_runs": swept_ever,
            "tenants_skipped_inactive_at_ingest": skipped_inactive,
            "tenants_skipped_not_active_at_run": skipped_already_suspended_at_run,
            "tenants_total": int(
                scalar(f"SELECT count(*) FROM {full('tenants')} WHERE `ns` = {NS_LIT}")
            ),
        },
        "subscriptions_shared": {
            "table": full("subscriptions"),
            "owned_by": SPEC["shared_write_policy"]["owned_by"],
            "match_key": SPEC["shared_write_policy"]["match_key"],
            "columns_written": SHARED_UPDATABLE,
            "columns_not_written": other_cols,
            "rows_matched_by_sweep": int(scalar("SELECT count(*) FROM v_subs_swept_tenants")),
            "rows_updated": len(shared_evidence),
            "rows_left_at_status": left_alone,
            "attribution_origins_seen": attribution,
            "merge_metrics": {k: str(v) for k, v in sub_merge_metrics.items()},
            "inserts": 0,
            "deletes": 0,
            "ddl_statements": 0,
            "rows": shared_evidence,
        },
        "notifications": {
            "written_by_sweep": int(
                scalar(
                    f"""
                    SELECT count(*) FROM {full('notifications')}
                     WHERE `ns` = {NS_LIT} AND `_origin` = 'target-suspension' AND `as_of` = {AS_OF_LIT}
                    """
                )
            ),
            "written_by_sweep_note": (
                "written_by_sweep is the standing count for this as_of, read back from the target: it "
                "includes a row an earlier run of this unit wrote on the same as_of, so it is not this "
                "run's contribution. population_rows_contributed_by_this_sweep is this run's "
                "contribution to the declared notifications population"
            ),
            "population_rows_contributed_by_this_sweep": int(
                scalar(
                    "SELECT count(*) FROM v_notifications_sweep WHERE NOT `suppressed_by_not_exists`"
                )
            ),
            "suppressed_by_not_exists": int(
                scalar("SELECT count(*) FROM v_notifications_sweep WHERE `suppressed_by_not_exists`")
            ),
            "same_as_of_rerun_would_add": rerun_would_add,
            "later_as_of_new_candidate_tenants": later_as_of_candidates,
            "tenants_active_with_suspension_notice_on_another_date": second_notification_population,
            "note": (
                "the source's INSERT carries WHERE NOT EXISTS on (tenant_id, kind_cd = 3, sent_at = "
                "CAST(TRUNC(p_as_of) AS TIMESTAMP)), so a legacy rerun on the same p_as_of adds "
                "nothing; a run on a different p_as_of adds a second notification only for a tenant "
                "still at status_cd = 10, and the sweep's own UPDATE TENANTS SET status_cd = 20 takes "
                "the tenants it just suspended out of that population"
            ),
        },
        "merge_metrics": {
            "tenants": {k: str(v) for k, v in tenant_metrics.items()},
            "notifications": {k: str(v) for k, v in notif_metrics.items()},
        },
        "money": {
            "overdue_total_in_cutoff": str(
                scalar(
                    "SELECT coalesce(sum(`invoice_total`), 0) FROM v_snapshot WHERE `in_suspend_cutoff`"
                )
            ),
            "quarantined_rows": tenant_rejects + notif_rejects + sub_rejects,
        },
        "accounting": accounting,
    }

# COMMAND ----------

summary = {
    "unit": UNIT,
    "phase": PHASE,
    "ns": NS,
    "as_of": AS_OF,
    "batch_id": BATCH_ID,
    "run_ids": RUN_IDS,
    "spec_path": SPEC_PATH,
    "invoice_source": INVOICES,
    "catalog": CATALOG,
    "pre_run_versions": PRE_VERSIONS,
    "post_run_versions": {
        t: (table_version(t) if table_exists(t) else -1) for t in PRE_VERSIONS
    },
    "quarantine": {
        "table": QUARANTINE,
        "threshold_pct": HALT_PCT,
        "persisted_before_threshold_evaluated": True,
        "halt_bases": HALT_RESULT,
        "populations_over_threshold": [n for n, b in HALT_RESULT.items() if b["over_threshold"]],
        "by_reason_this_batch": {
            r[0]: int(r[1])
            for r in spark.sql(
                f"""
                SELECT `quarantine_reason`, count(*) FROM {QUARANTINE}
                 WHERE `ns` = {NS_LIT} AND `_batch_id` = {BATCH_LIT} GROUP BY 1 ORDER BY 1
                """
            ).collect()
        },
        "rejection_ledger": [
            {
                "quarantine_reason": r[0],
                "source_table": r[1],
                "source_key": r[2],
                "detail": r[3],
                "population": r[4],
            }
            for r in spark.sql(
                f"""
                SELECT `quarantine_reason`, `source_table`, `source_key`, `detail`, `population`
                  FROM {QUARANTINE} WHERE `ns` = {NS_LIT} AND `_batch_id` = {BATCH_LIT}
                 ORDER BY `source_table`, `quarantine_reason`, `source_key`
                """
            ).collect()
        ],
    },
    "deletes_issued": 0,
    "ddl_on_shared_tables": 0,
    # The tables this phase can commit to, and the commit each one carries from *this* run. The
    # shared subscriptions table is listed in phase 2 because the sweep MERGEs it; a phase that
    # matched nothing reports no commit rather than an older one.
    "commit_metrics": {
        t: history_metrics(t)
        for t in (
            [full("dunning_attempts"), QUARANTINE]
            if PHASE == "schedule"
            else [full("tenants"), full("notifications"), full("subscriptions"), QUARANTINE]
        )
    },
}
summary.update(phase1_summary if PHASE == "schedule" else phase2_summary)

out_path = f"{LANDING}/_runs/{BATCH_ID}-{PHASE}.json"
dbutils.fs.mkdirs(f"{LANDING}/_runs")
dbutils.fs.put(out_path, json.dumps(summary, indent=1, default=str), overwrite=True)
print(f"run summary -> {out_path}")
dbutils.notebook.exit(
    json.dumps({"run_summary": out_path, "batch_id": BATCH_ID, "phase": PHASE, "ns": NS})
)
