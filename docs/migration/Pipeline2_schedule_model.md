# Pipeline 2 — cron → Lakeflow Job schedule model (wave 0, shared with pipeline 3)

Status: **proposed, pinned at STOP C**. Pipeline 2 owns this model; pipeline 3 inherits it for
the five Python jobs in `etl/crontab`.

Cron and the `run_all.sh` sleep chain are **retired, not wrapped**
(`docs/migration/OtterWorks_target_state.md`). Timing is replaced by real task dependencies.

## 1. What the cron actually does today

`etl/legacy-extra/crontab` (CUSTBILL chain — pipeline 2):

| Cron | Job | Behaviour worth naming |
|---|---|---|
| `*/15 * * * *` | `sftp_ingest_poll.ksh` | overlaps its own previous run; writes `/tmp/sftp_ingest.lock` and never removes it |
| `5-59/15 * * * *` | `parse_custbill_fixedwidth.sh` | fires 5 min behind ingest on a *guess*; can read a half-written file |
| `10 2 * * *` | `finance_excel_report.pl` | overlaps `analytics_daily.py` at 02:00 on the same box |
| `0 6 * * 0` | `run_all.sh` | Sunday re-run of the whole chain, with two `sleep 600` calls standing in for dependencies, and every stage failure swallowed by `|| true` |

`etl/crontab` (shared Python jobs — **pipeline 3 implements, this model applies**):
`analytics_daily` 02:00, `storage_cleanup_daily` 02:30, `audit_archive_weekly` Sun 03:00,
`search_reindex_weekly` Sun 04:00, `user_activity_daily` 05:00.

Three defects are load-bearing and must not be carried over: the 5-minute guess instead of a
dependency, the self-overlap, and the swallowed failures.

## 2. Cron → Quartz conversion table

Databricks quartz expressions carry a seconds field and use `?` for the unused day slot.

| Legacy cron | Quartz | Job |
|---|---|---|
| `*/15 * * * *` | `0 0/15 * * * ?` | `ow_tp_p2_custbill_ingest` |
| `5-59/15 * * * *` | *(removed — becomes a task dependency)* | — |
| `10 2 * * *` | `0 10 2 * * ?` | `ow_tp_p2_finance_close` |
| `0 6 * * 0` | `0 0 6 ? * SUN` | *(proposed dropped — P2-D05)* |
| `0 2 * * *` | `0 0 2 * * ?` | pipeline 3 `analytics_daily` |
| `30 2 * * *` | `0 30 2 * * ?` | pipeline 3 `storage_cleanup_daily` |
| `0 3 * * 0` | `0 0 3 ? * SUN` | pipeline 3 `audit_archive_weekly` |
| `0 4 * * 0` | `0 0 4 ? * SUN` | pipeline 3 `search_reindex_weekly` |
| `0 5 * * *` | `0 0 5 * * ?` | pipeline 3 `user_activity_daily` |

**Timezone (P2-D04).** The legacy box runs in its own local time and `finance_excel_report.pl`
stamps the output filename from `localtime`. Every converted schedule and the report's date
stamp use a single declared `timezone_id`. Proposed: `UTC`. If the finance team reads the date
in the filename as a local business date, this is the one place a cutover can silently shift a
day boundary — so it is a named decision, not a default.

## 3. Target jobs

Two jobs. Both created **PAUSED**. Both on the existing serverless SQL warehouse
`565cd2fd713738c4`; no new clusters.

### `ow_tp_p2_custbill_ingest` — every 15 minutes

```
trigger: quartz 0 0/15 * * * ?  (PAUSED)
max_concurrent_runs: 1          # kills the self-overlap; a late run is skipped, not stacked
tasks:
  land_files      -> copy stable CUSTBILL*.dat into /Volumes/ow_tp/bronze/landing/custbill/
  custbill_pipeline (depends_on: land_files)
                  -> Lakeflow Spark Declarative Pipeline: bronze -> silver + quarantine
```

`parse` no longer has a schedule. It is `depends_on: land_files`, which is the whole point of
the conversion: the 5-minute guess and the half-written-file race are replaced by the pipeline
only ever seeing files the landing task has already committed.

The 1-second double-stat stability check is replaced by an atomic land: the file is written to
a staging name in the volume and renamed into place, so a partially written file is never
visible to the pipeline. This **removes** a legacy race rather than reproducing it — recorded
as **P2-D01** for the user to confirm, because it can change output on a day when the legacy
would have parsed a truncated file.

### `ow_tp_p2_finance_close` — daily 02:10

```
trigger: quartz 0 10 2 * * ?    (PAUSED)
max_concurrent_runs: 1
queue: enabled                  # a late ingest delays the close, it does not cancel it
tasks:
  await_silver    -> Lakeflow pipeline run (no-op when silver is already current)
  gold_close      (depends_on: await_silver)   -> ow_tp.gold.custbill_finance_close
  export_csv_xls  (depends_on: gold_close)     -> /Volumes/ow_tp/gold/exports/custbill/
                                                  finance_billing_<YYYYMMDD>.csv and .xls
  trailer_audit   (depends_on: await_silver)   -> non-fatal trailer-count reconciliation
```

No `sleep`. No `|| true`: any task failure fails the run.

The 02:00 / 02:10 collision with `analytics_daily.py` disappears — they no longer share a box,
and neither reads the other's output.

### Retries and failure notification

| Setting | Value |
|---|---|
| `max_retries` | 2 per task |
| `min_retry_interval_millis` | 300000 (5 min) |
| `retry_on_timeout` | true |
| `timeout_seconds` | 3600 per job |
| `on_failure` | notification destination `ow-migrations` |

The notification destination is a bundle **variable, left empty in the migration target**. A
child session does not wire a live pager. Populating it is a cutover step.

## 4. The Sunday `run_all.sh` re-run (P2-D05)

`run_all.sh` re-runs the whole chain on Sunday at 06:00. In the legacy that re-run does almost
nothing useful: ingest finds nothing left in the drop, parse finds every input already renamed
`.done`, and the report simply re-emits the same cumulative totals under a fresh date stamp.

Proposed: **drop it.** The daily close plus an idempotent pipeline already cover it, and
keeping it would only re-emit a duplicate report under a Sunday filename. The alternative —
keep a weekly `ow_tp_p2_custbill_full_recompute` job that rebuilds gold from all of silver and
runs the trailer audit over the full history — is available if finance relies on the Sunday
file existing. This is a STOP E question for the user.

## 5. Lock files

`/tmp/sftp_ingest.lock`, `/tmp/parse_custbill.lock` and `/tmp/finance_report.lock` are created,
never removed, and every job logs "lock exists, probably stale, proceeding" and carries on.
They provide no mutual exclusion. They are dropped; `max_concurrent_runs: 1` does the job they
were pretending to do.

## 6. What pipeline 3 inherits

The conversion table in §2, the timezone decision (P2-D04), `max_concurrent_runs: 1` as the
default, the retry/notification block in §3, and PAUSED-until-cutover. Pipeline 3 owns the
five Python jobs themselves; this document does not implement them.
