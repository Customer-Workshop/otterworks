# Pipeline 3 — STOP E: cutover decision packet

**Pipeline:** OtterWorks product analytics — the five `etl/scripts/*.py` cron jobs and the
Scala `UsageRollupJob` → six Lakeflow Jobs and SQL on Delta in `ow_tp` (five built, one
removed from scope).
**Date:** 2026-09-15 · **Status:** final reissue — P3-Q3 closed, the analytics recon scope
recorded and re-run green, everything else awaiting customer decision · **Prepared by:** the
pipeline-3 migration session.

**Nothing here authorizes a cutover.** Every schedule is PAUSED, no consumer has been
repointed, no legacy script or crontab was changed, the converted cleanup job deletes nothing
and the converted audit job prunes nothing. Cutover needs the customer-held cutover principal
and an explicit reply.

---

## 1. What is being asked

| # | Decision | Recommendation |
|---|---|---|
| **P3-Q1** | **Provision `ow_tp/analytics_postgres_password`**, or accept that the serving leg stays unverified. The secret named in the brief does not exist in the workspace; scope `ow_tp` holds only `sftp_host`, `sftp_user`, `sftp_password`. `publish_summary` fails on the lookup, so the analytics job has never completed green end to end, and neither has the user-activity chain that depends on it. | **Provision it** (plus the serving host, database and user to pass) and I rerun the two tasks. No plaintext fallback was added and none should be. |
| **P3-Q2** | **Rotate the credentials in `etl/config.ini`** — plaintext AWS keys, the Postgres password and the MeiliSearch key, committed and therefore in source history. | **Rotate, customer-owned.** Migration removed them from the converted code, not from history. Rotation is not a migration action and was not performed. |
| **P3-Q3** | ~~Do the legacy report files still have consumers?~~ **Closed 2026-09-15 — no longer a customer question.** The files are restored and byte-compared; see §1a. | **Closed.** No decision needed. |
| **P3-Q4** | **Does the Scala usage rollup have a real input and a real consumer in production?** In this estate it reads a seed file baked into the image and writes to an `emptyDir` that dies with the pod (F-0.5, F-0.6) — a nightly job whose output nobody can read. It was migrated anyway (P3-D07) because it is cheap and the table is useful. | **Answer before unpausing it.** If production is the same shape, the honest move is to delete the CronJob rather than schedule its replacement. |
| **P3-Q5** | **Enable deletion in the storage-cleanup job?** Per P3-D03 the converted job computes and persists the delete set and never deletes. The delete set was proven equal to the legacy's, as a set of key+size. | **Leave it off.** Turn it on, if ever, as its own change with its own approval — never as a side effect of unpausing the schedule. |
| **P3-Q6** | **Prune the audit source after archiving?** Per P3-D04 the converted job archives and never prunes. The legacy tries and fails (F-0.4). | **Leave it off.** Pruning a compliance source is a customer action with its own retention decision behind it. |
| **P3-Q7** | **Confirm `search_reindex_weekly.py` stays a service-side job** (P3-D05, approved at STOP C). It reads two in-cluster HTTP services and writes MeiliSearch; there is no Databricks target in it. | **Confirm.** It is a declared coverage gap, not a delivered unit. Nothing on Databricks reindexes search after cutover. |
| **P3-Q8** | **The analytics job would run twice a day** if both schedules are activated as written: its own 02:00 trigger and the 05:00 `run_job_task` from user-activity. Idempotent, but paid for twice. | **Drop the analytics job's own schedule at cutover** and let user-activity drive it, or accept the second run. Do not solve it by going back to a time offset. |

---

## 1a. P3-Q3, closed: an acceptance criterion I dropped, and what put it back

This one is written up twice on purpose — the mistake and the fix — because only writing down
the fix hides how the gap got in.

**What I did wrong.** The plan declared, for three units, that the converted job writes the
legacy's report objects to an export volume and that a **byte compare against the legacy's own
file** is the acceptance gate. I shipped Delta tables only and reconciled the tables instead.
That is not a smaller version of the declared gate, it is a different one: table parity proves
the values, and says nothing about the bytes a consumer reads — key order in a JSON object,
number formatting, gzip framing, the `latest/` pointer, whether a file is written at all on an
empty day. I then justified it with "nothing in this repo reads those objects," which is not
evidence: the repo is the estate's code, not its consumers. An analyst pulling
`activity_report.json` off S3 leaves no trace in it. I removed an acceptance criterion without
a decision row, and reported the unit green against a gate I had quietly swapped.

**What put it back.** One follow-up PR per unit, each adding the export task and the byte gate:

| Unit | Objects restored | PR |
|---|---|---|
| `p3-analytics-daily` | `reports/analytics/daily/<date>/report.json`, and the gzipped `summary.json.gz`, `hourly_breakdown.json.gz`, `top_users.jsonl.gz` under `analytics/daily/year=/month=/day=/` | #1625 |
| `p3-audit-archive` | `audit-archive/<date>/audit_events.jsonl.gz`, `manifest.json`, `compliance_report.json` | #1626 |
| `p3-user-activity` | `reports/user-activity/<date>/activity_report.json`, `reports/user-activity/latest/activity_report.json`, `reports/user-activity/<date>/user_summaries.jsonl` | #1639 |
| all three | covered-date gate, whole-root unexpected-file detection, generated audit scan order | #1627 |

Each job now runs `export_*` after its gold tables, then `compare_*_objects`, which reads the
files **back off the volume** and compares them byte for byte against the legacy's own objects,
frozen at wave 0 in `databricks/migration/p3/exports/legacy_objects/`. The gate fails on a
missing object, a byte mismatch, an unexpected file anywhere under the export root, and on a
file written under a shape the legacy leaves empty. `generated_at` is the only normalized
field — it is a clock reading on both sides. A comparison run for a date the frozen manifest
does not cover **fails** rather than passing vacuously; a condition task gates the comparator
so a genuine other-date run skips it visibly instead.

Two things this surfaced that table parity could never have caught:

- **`actions_by_type` key order is shipped output.** The legacy builds that JSON object while
  walking the day's events in arrival order. Gold had aggregated the order away, so the report
  could not be rebuilt byte-exactly from Delta at all. Both action tables now carry
  `action_ordinal`, and the exporter refuses to build a report if any ordinal is NULL rather
  than guessing.
- **The audit archive's scan order** is likewise part of its bytes, and is now generated with
  the fixture and checksummed rather than assumed.

**What is still not proven.** The destination differs: the legacy writes to S3, the target
writes to a Unity Catalog volume, and no S3 write is performed or reconciled. Anyone who wants
the files to land in the legacy bucket needs a copy step and a decision about who owns it. The
Delta tables remain the governed output; the files are a compatibility output rebuilt from them.

---

## 1b. Recon scope: one unit's fixture was changing another unit's comparison

Restoring the exports surfaced a failure that looked like a broken conversion and was not.
Both halves are recorded, because the second one outlives pipeline 3.

**P3-D10 — the analytics mapping now names the day it was always about.**
`p3-analytics-daily`'s mapping compared whole gold tables against a one-day legacy baseline.
Wave 2 seeds the 33 days before the run date into those same gold tables, because
`user_activity_daily` reports over a 31-day window. The comparison therefore became 34 target
days against 1 legacy day and failed Tier 1 on row counts. The conversion did not change; the
shared table did. Every object in the mapping is now scoped on both sides with
`summary_date = DATE '${run_date}'`. **No tolerance was widened and no field was dropped.**

Official harness, re-run live from the change (#1640):

```
dbx-recon PASS: unit=p3-analytics-daily mode=live depth=full mapping=map-p3-v1
                tolerances=v1 merge_eligible=True
  Tier 1 counts_through_mapping    4 PASS
  Tier 2 per_field_aggregates     25 PASS
  Tier 3 keyed_diffs             224 PASS
  params: run_date=2026-09-15, batch=p3probe
```

The 224 keyed rows are the same 224 the unit reconciled before the history was seeded, which
is what shows the predicate selected the day rather than shrank the comparison.

**P3-D11 — the cause is general, and it will bite the next pipeline.**
`databricks/migration/p3/fixtures/seed_upstream_history.py` writes into gold tables that a
different unit reconciles, so one unit's fixture silently changes another unit's comparison.
Nothing in the harness detects it: the failure surfaces as a row-count mismatch that reads
like a broken conversion, and the tempting fix — widening a tolerance — would have buried it.

Pipeline 3's mitigation is that **every** mapping is now date- or batch-scoped, so a seeded
neighbour cannot contaminate a unit's comparison. Review of #1640 caught that this was not yet
true of `p3-audit-archive`, whose baseline loader rebuilds its source tables for one batch
while the target loads keep earlier batches; a second batch would have failed the same way.
Both audit objects are now scoped on `batch` / `snapshot_batch` + `run_date` and the unit was
re-reconciled live: **PASS**, `depth=full`, `merge_eligible=true`, unchanged rows (#1642).

The stronger fix, which pipeline 3 does **not** implement: namespace fixture writes away from
the reconciled tables entirely. Date scoping only works while every mapping remembers to apply
it, and a future unit that forgets gets a false failure with a misleading cause. **Whoever owns
the fixture layer should do this before the next pipeline reuses it.**

---

## 2. Delivery state

4 waves, 8 units, all closed. One PR per unit into `tp-run/databricks-20260915T045714Z`.

| Wave | Unit | Replaces | Recon | PR |
|---|---|---|---|---|
| 0 | `p3-foundations` | — (plan, record contract, fixtures, captured legacy baselines, mapping specs) | no data movement | #1612, #1614, #1615 |
| 1 | `p3-analytics-daily` | `etl/scripts/analytics_daily.py` | official **PASS**, live, full depth | #1616, #1617, #1625, #1640 |
| 1 | `p3-storage-cleanup` | `etl/scripts/storage_cleanup_daily.py` | official **PASS**, live, full depth | #1618 |
| 1 | `p3-audit-archive` | `etl/scripts/audit_archive_weekly.py` | official **PASS**, live, full depth | #1619, #1626, #1642 |
| 1 | `p3-usage-rollup` | `services/.../batch/UsageRollupJob.scala` | official **PASS**, live, full depth | #1620, #1621 |
| 1 | `p3-search-reindex` | `etl/scripts/search_reindex_weekly.py` | **not migrated** — declared coverage gap (P3-D05) | #1614 |
| 2 | `p3-user-activity` | `etl/scripts/user_activity_daily.py` | official **PASS**, live, full depth | #1622, #1639, #1641 |
| 3 | `p3-orchestration` | `etl/run.sh`, the five crontab rows, the Helm CronJob | structural only: no data movement | #1623 |

Every verdict is an official `dbx-recon` verdict with `merge_eligible=true`, recomputed from
the target, with idempotency proven by an actual rerun of the deployed job and whole-row
content hashes compared — not row counts. Each unit was reconciled against **the legacy's own
output**, captured by running the legacy job, never against a Python reimplementation of it.

Three PRs in that table are **open, not merged** at the time of writing: #1640 (analytics
mapping scope, P3-D10/P3-D11), #1642 (audit mapping scope) and #1641 (user-activity review
fixes: an unknown source action order now propagates as NULL instead of a plausible-looking
ordinal, and a backfill no longer moves the `latest/` report pointer backwards).

What the target looks like today:

```
/Volumes/ow_tp/bronze/landing/analytics/    landed events, inventory, audit, usage; nothing deleted
ow_tp.bronze.*_raw                          one row per source record, bytes preserved
ow_tp.silver.analytics_events, file_objects, audit_events
ow_tp.gold.analytics_daily_summary, analytics_hourly_breakdown,
           analytics_daily_top_users, analytics_daily_top_user_actions
ow_tp.gold.storage_orphan_delete_set, storage_cleanup_report
ow_tp.gold.audit_archive_manifest, audit_archive_compliance_report
ow_tp.gold.usage_rollup_daily
ow_tp.gold.user_activity_report, _report_days, _user_summary, _user_actions
ow_tp_p3_analytics_daily          0 0 2 * * ?     PAUSED
ow_tp_p3_storage_cleanup_daily    0 30 2 * * ?    PAUSED
ow_tp_p3_audit_archive_weekly     0 0 3 ? * SUN   PAUSED
ow_tp_p3_usage_rollup_daily       0 0 2 * * ?     PAUSED
ow_tp_p3_user_activity_daily      0 0 5 * * ?     PAUSED
```

Orchestration detail and the deployed job-graph audit are in
`docs/migration/Pipeline3_schedule_model.md`.

---

## 3. What we found in the estate — facts, not claims about production

These are properties of the code and configuration in this repository. Nothing here is a
statement about what the customer's production environment does; each is a question.

| id | Finding | Why it matters |
|---|---|---|
| **F-0.4** | **The audit archive job matches nothing the audit service writes.** Its DynamoDB scan filters on lowercase `timestamp`; `DynamoDbAuditRepository.SaveEventAsync` writes `Timestamp`, `id`/`Id`, and no `event_id`. A filter naming an absent attribute excludes the item, so the scan returns zero, `archive_count == 0`, and the job exits 0 having archived nothing and never reaching its delete loop. | If production looks like this, **no audit archive has ever been produced** and nothing was ever pruned. The converted job reproduces this exactly: against service-shaped records an empty archive is the correct, reconciled result. |
| **F-0.6** | **The Scala rollup throws its output away.** The Helm CronJob reads a seed file baked into the image and writes to an `emptyDir` destroyed when the pod exits. | No consumer can be reading it. See P3-Q4. |
| **F-0.3** | **The cleanup job points at buckets that do not exist here.** `etl/config.ini` names `otterworks-file-storage` and `otterworks-file-quarantine`; the file service uses `otterworks-files`. Against the estate as configured the job fails on the first `list_objects_v2` and exits 1 before deleting anything. | The one job in the estate that deletes may never have deleted. Confirm the production bucket names before anyone considers enabling deletion (P3-Q5). |
| **F-0.1** | `analytics_daily.py` **consumes** its SQS input — every batch read is deleted. The job cannot be re-run on the same input, and a second run the same day finds an empty queue. | Replaced by durable landing (P3-D01). It also means legacy idempotency could never be tested, only the target's. |
| **F-0.9** | **Two event-type vocabularies.** file-service and document-service publish snake_case (`file_uploaded`); analytics-service's own constants are dotted (`file.uploaded`). A dotted event reaching `analytics_daily.py` counts in `total_events` and the hourly breakdown but contributes to no document or file metric. | Preserved exactly, including the literal `NaN` key the legacy emits for a missing action type. If the two vocabularies ever meet in production, the daily numbers are already quietly wrong — a customer decision, not a migration fix. |
| **F-0.8** | All five Python jobs read credentials from committed plaintext. | See P3-Q2. |

---

## 4. Behaviour changes — what the target does *not* do the same way

| id | Change | Status |
|---|---|---|
| **P3-D01** | Events are landed durably instead of consumed off the queue. | Accepted at STOP C. No change to a single run's output; it makes reruns and backfill possible, which the legacy could not do at all. |
| **P3-D02** | A serving-layer (Postgres) failure now fails the run loudly instead of being swallowed after the report is written. | Accepted at STOP C. Differs only on a run the legacy would have half-completed. Note this is why the missing secret (P3-Q1) fails the whole job rather than being skipped. |
| **P3-D03** | The cleanup job computes and persists the delete set and never deletes. | Accepted at STOP C. Strictly safer; the delete set was proven equal as a set first. |
| **P3-D04** | The audit job archives and never prunes the source. | Accepted at STOP C. In this estate the legacy does not successfully prune either (F-0.4), so observable behaviour is identical. |
| **P3-D05** | `search_reindex_weekly.py` is out of Databricks scope. | Accepted at STOP C. See P3-Q7. |
| **P3-D06** | The Scala rollup became SQL on Delta — no JAR task, no cluster. | Accepted at STOP C. Reconciled against the real JVM job's own output, not a reimplementation. |
| **P3-D08** | `execution_date` / `run_date` is an explicit job parameter instead of the box's wall clock. | Additive. A same-day run is unchanged; a rerun for an older date is now possible. |
| **Orchestration** | `user_activity_daily`'s three-hour wait on `analytics_daily` became a dependency edge (`run_job_task` on the owning job). | Accepted. The legacy guess silently produced a shorter report when the 02:00 run was late; the edge cannot. See P3-Q8 for the cost. |
| **Exports** | The three units that wrote report files write Delta tables **and** rebuild the legacy report objects on an export volume, byte-compared against the legacy's own files. | **Restored.** Shipping tables only was an unrecorded substitution and my error; both the substitution and the restoration are written up in §1a. The only remaining difference is the destination: a Unity Catalog volume, not S3. |

---

## 5. What the reconciliation does not cover

Stated plainly, because "all units passed" would be misleading.

- **`source_principal_read_only` is unverified for every pipeline-3 unit** (P3-D09). The
  factory doctor implements privilege queries for SQL Server and Postgres only, and this
  pipeline's source family is `databricks`, so the row can never go green at run time.
  Closing it properly needs a Databricks privilege query in the doctor plugin. It was **not**
  worked around, and readiness is honestly `ready=false`.
- **The fan-out was lost to that same row.** Wave 1 ran as five sequential in-session units
  under the identical gate rather than through `migration-fanout`, whose workflow re-runs the
  doctor and refuses unless `ready=true`.
- **The analytics serving leg has never run.** `publish_summary` fails on the missing secret
  (P3-Q1), so the Postgres write path is configured and unexercised.
- **The full two-job chain has never completed green.** The `run_job_task` edge is verified —
  analytics really is started and user-activity really does wait — but the upstream run ends in
  failure on that same secret, so the user-activity tasks were run and reconciled directly.
- **No schedule has ever fired.** Everything was exercised by explicit runs; the Quartz
  expressions are verified as configuration.
- **Retries and failure notifications are configured, not exercised.** `failure_webhooks` is
  empty in the `migration` target on purpose, so `on_failure` delivers nothing today.
- **Report files are byte-compared, but only for the date the frozen manifest covers** and only
  on the volume. The legacy's S3 destination is not written and not reconciled (§1a).
- **Rows, not structure.** The harness compares row data, not table properties, comments or
  grants — including grants on the landing volume.
- **Only the pinned fixture set** is exercised. Notably the audit unit's `A-estate` probe
  (service-shaped records) correctly produces an empty archive, so "archives correctly" is
  proven only for the `A-tsonly` and `A-full` shapes.
- **Wall-clock columns** (`generated_at` and friends) are excluded from diffs and fingerprints
  as target-side values with no legacy counterpart.
- **`search_reindex_weekly.py` is not covered at all** — no job, no recon, no target. After
  cutover nothing on Databricks maintains the search index.

---

## 6. Incident — a bucket created in the real AWS account

During a re-run of the audit-archive baseline capture, `AWS_ENDPOINT_URL` was not set, so
boto3 fell through from the local estate to the real demo AWS account and created an empty
bucket `otterworks-audit-archive` (us-east-1, account 599083837640).

- **What was left behind: nothing.** The run's own cleanup emptied the bucket and it was
  deleted. No objects were written to it, and nothing else in the account was touched.
- **Root cause was our own wave-0 tooling**, not a credential problem: `capture_p3_baseline.py`
  and `gen_p3_fixture.py` treated a missing endpoint as "use default AWS".
- **Fix, shipped in #1619:** both refuse to run without `AWS_ENDPOINT_URL`.

---

## 7. Ledger-hygiene gap

Three `mapping_spec.json` files written in wave 0 describe units with no row-level parity, so
they break the orchestrator-role doctor, which expects pipeline 2's `no_data_movement.json`
convention for those:

```
.migration/units/p3-foundations/mapping_spec.json
.migration/units/p3-orchestration/mapping_spec.json
.migration/units/p3-search-reindex/mapping_spec.json
```

The `no_data_movement.json` replacements are committed alongside them. The stray files could
not be removed: `.migration/units/` is not command-writable under the migration guard, and the
remedy the guard names (an `allowed_targets.json` entry plus a decision row) is the parent's
ledger, not a child's. Reported as a finding rather than routed around. Removing them is a
one-line ledger action for whoever owns `.migration/`.

---

## 8. What has not been touched

- No production cutover. The legacy scripts, `etl/crontab`, `etl/run.sh`, `etl/config.ini` and
  the analytics-service Helm CronJob are all unchanged.
- No new clusters. Everything is serverless alongside the existing warehouse `565cd2fd713738c4`.
- No live schedule: all five jobs are PAUSED, and the bundle target pins
  `presets.trigger_pause_status: PAUSED`, so nothing it deploys can run on a timer. There is no
  `prod` target in the bundle to deploy to by accident.
- No deletes anywhere: not from S3 (P3-D03), not from DynamoDB (P3-D04), not from the landing
  volume.
- No credentials in converted code — secret names only — and none in any log, artifact or PR.
- Nothing belonging to pipelines 1 or 2, and no Oracle access at any point: pipeline 1's Delta
  output was read, never Oracle itself.

---

## 9. Cutover sequence, once authorized

1. Answer §1. **P3-Q1** (the secret) gates whether the analytics and user-activity jobs are
   complete at all; the rest gate what is safe to unpause. P3-Q3 is closed (§1a).
2. Rotate the `etl/config.ini` credentials (P3-Q2) — independent of everything else, and worth
   doing whether or not cutover happens.
3. Set `failure_webhooks` to a real destination. Today a failed run notifies nobody.
4. Deploy the bundle to a production target, which drops the development-mode `[dev ...]` name
   prefix.
5. Run each job once by hand for a real day and compare against the legacy run for that day.
   Both chains can run side by side: the target deletes nothing and writes only under `ow_tp`.
6. Unpause in dependency order: `analytics_daily` first, confirm a clean day, then
   `user_activity_daily` (and decide P3-Q8 at that moment), then the independent
   `storage_cleanup`, `audit_archive` and `usage_rollup` jobs.
7. Disable the corresponding `etl/crontab` rows and the Helm CronJob — the only changes to the
   legacy estate, and the customer's to make. Keep the scripts in place as the rollback.
8. Rollback at any point: pause the jobs, re-enable the cron rows. The target has removed
   nothing the legacy chain needs.
9. Separately, and never as part of unpausing: the storage-cleanup delete flag (P3-Q5) and any
   audit-source pruning (P3-Q6).

**This packet does not authorize step 4 onward. Pipeline 3 stops here.**
