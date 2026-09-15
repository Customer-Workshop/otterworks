# Pipeline 3 — OtterWorks product analytics (Python cron + Scala rollup) → Lakeflow Jobs + SQL on Delta

**STOP C artifact.** Decision required: approve this plan, the record contract, and the
seven decisions in §3, so waves 0–3 can run.

- Record contract: [`Pipeline3_analytics_record_contract.md`](Pipeline3_analytics_record_contract.md)
- Schedule model (inherited, not re-invented): [`Pipeline2_schedule_model.md`](Pipeline2_schedule_model.md)
- Target conventions: [`OtterWorks_target_state.md`](OtterWorks_target_state.md)
- Census (accepted at STOP B): [`OtterWorks_inventory.md`](OtterWorks_inventory.md)

Working branch and PR base: `tp-run/databricks-20260915T045714Z`. One PR per unit, never a
stack. Pipelines 1 and 2 are merged into that branch and parked at STOP E; every unit rebases
before its PR.

## 1. What changed between the brief and this plan

Three things in the brief turned out to be different once the estate was read. They change
the work, so they lead:

1. **The Scala rollup is scheduled.** The brief says it has no crontab entry, which is true.
   It is scheduled in Helm instead: `infrastructure/helm/analytics-service` ships a CronJob
   with `cronjob.enabled: true` and `schedule: "0 2 * * *"`. "Is this still running" has an
   answer, and it is yes — nightly at 02:00 UTC, in the same slot as `analytics_daily.py`.
2. **But its output is thrown away.** That CronJob reads a seed file baked into the image and
   writes to an `emptyDir` volume that is destroyed when the pod exits. Nothing can be
   consuming it. The migration question is therefore not "how do we port this" — it is SQL,
   it ports in an afternoon — but "should this exist at all". That is P3-D06 and P3-D07.
3. **`storage_cleanup_daily.py` cannot be deleting anything in this estate.** It reads bucket
   `otterworks-file-storage` from `config.ini`; the estate's file storage is
   `otterworks-files`. The bucket in the config does not exist, so the job dies on its first
   list call. The same shape of problem hits `audit_archive_weekly.py`, which deletes on a
   key schema the table does not have and swallows the error, so it has never pruned
   anything. Both are recorded as contract facts F-0.3 and F-0.4 and as STOP E questions.

None of those are claims about a production deployment. They are what is true of the estate
in this repository, and each one is a question for the user rather than an assumption.

## 2. Scope, units, and write targets

Everything lands in catalog `ow_tp`. Existing serverless SQL warehouse `565cd2fd713738c4`.
No new clusters. Job names `ow_tp_p3_*`.

| Unit | Legacy object(s) | Lines | Wave |
|---|---|---:|---:|
| `p3-foundations` | `etl/run.sh`, `etl/config.ini`, `etl/crontab` (p3 rows), fixtures, baseline capture | 7 + 25 | 0 |
| `p3-analytics-daily` | `etl/scripts/analytics_daily.py` | 452 | 1 |
| `p3-storage-cleanup` | `etl/scripts/storage_cleanup_daily.py` | 217 | 1 |
| `p3-audit-archive` | `etl/scripts/audit_archive_weekly.py` | 224 | 1 |
| `p3-search-reindex` | `etl/scripts/search_reindex_weekly.py` | 319 | 1 |
| `p3-usage-rollup` | `UsageRollupJob.scala`, `UsageRollupAggregator.scala` | 96 + 54 | 1 |
| `p3-user-activity` | `etl/scripts/user_activity_daily.py` | 255 | 2 |
| `p3-orchestration` | p3 rows of `etl/crontab`, the analytics-service CronJob | 5 + 1 | 3 |

Nine census objects, eight units: `run.sh` and `config.ini` are shared objects and belong to
`p3-foundations`, and the two Scala files are one unit because the aggregator has no
independent existence.

### Write targets

| Unit | Write targets |
|---|---|
| `p3-foundations` | repo only (docs, fixture seeder, captured legacy baseline) plus `ow_tp.bronze.analytics_legacy_baseline_*`, volume path `/Volumes/ow_tp/bronze/landing/analytics/` |
| `p3-analytics-daily` | `ow_tp.bronze.analytics_events_raw`; `ow_tp.silver.analytics_events`; `ow_tp.gold.analytics_daily_summary`, `analytics_hourly_breakdown`, `analytics_top_users`, `analytics_daily_report`; volume path `/Volumes/ow_tp/gold/exports/analytics/` |
| `p3-storage-cleanup` | `ow_tp.bronze.file_inventory_raw`, `ow_tp.bronze.file_metadata_raw`; `ow_tp.silver.file_objects`; `ow_tp.gold.storage_orphan_delete_set`, `storage_cleanup_report` |
| `p3-audit-archive` | `ow_tp.bronze.audit_events_raw`; `ow_tp.silver.audit_events`; `ow_tp.gold.audit_archive_manifest`, `audit_archive_compliance_report`; volume path `/Volumes/ow_tp/gold/exports/audit-archive/` |
| `p3-search-reindex` | **none** — proposed scope removal (P3-D05); the unit ships a reasoned no-data-movement artifact only |
| `p3-usage-rollup` | `ow_tp.bronze.analytics_usage_events_raw`; `ow_tp.gold.usage_rollup_daily` |
| `p3-user-activity` | `ow_tp.gold.user_activity_report`, `user_activity_user_summaries`; volume path `/Volumes/ow_tp/gold/exports/user-activity/` |
| `p3-orchestration` | jobs `ow_tp_p3_analytics_daily`, `ow_tp_p3_storage_cleanup_daily`, `ow_tp_p3_audit_archive_weekly`, `ow_tp_p3_usage_rollup_daily` — all PAUSED |

### Collision check

Pipeline 1 owns `ow_tp.silver`/`gold` tables named `invoice*`, `customer*`, `plans`,
`subscriptions*`, `dunning_attempts`, `notifications`, `rating_*`, `codes`,
`billing_audit_log`, `entity_attr_value` and — importantly — **`usage_events`**. That is why
the Scala rollup's landing table is `analytics_usage_events_raw` and its output is
`usage_rollup_daily`: naming it `usage_events` would be a write-target collision with
`p1-usage-events` and a halt. Pipeline 2 owns `custbill*`. No name above collides with either.

Reads only, never writes: `p3-user-activity` reads `p3-analytics-daily`'s gold tables. No
pipeline-3 unit touches Oracle, Lakebase, or any pipeline-1 or pipeline-2 object.

### Transitive writes

The trap pipeline 1 lost two waves to. Traced here: `analytics_daily.py` **deletes the SQS
messages it reads** (a write to its own source, F-0.1), `storage_cleanup_daily.py` deletes
from the file-storage bucket, and `audit_archive_weekly.py` attempts to delete from DynamoDB.
All three are writes to legacy sources. None is reproduced: the legacy estate is read-only in
every phase, the two delete paths are covered by P3-D03/P3-D04, and the SQS delete is replaced
by a durable landing table.

## 3. Decisions to record

| id | Decision | Recommendation | When |
|---|---|---|---|
| **P3-D01** | `analytics_daily.py` consumes SQS destructively, so the legacy is not re-runnable and the target cannot read the same input twice. The target lands every event into `bronze.analytics_events_raw` once and recomputes everything from there. | Accept. It is the only way to get an idempotent, backfillable job, and it does not change what a single run produces. | STOP C |
| **P3-D02** | `analytics_daily.py` swallows a Postgres failure and still writes its S3 report (C-2.16). The target fails the task loudly and lets the retry policy handle it. | Accept the fix. It only differs on a run the legacy would have half-completed. | STOP C |
| **P3-D03** | `storage_cleanup_daily.py` deletes. The target computes the delete set, persists it, and never deletes unless a human sets an explicit job parameter. | Accept. The gate for this unit is exact set equality of the delete set, not a row count. | STOP C |
| **P3-D04** | `audit_archive_weekly.py` archives and then tries to prune DynamoDB. The target archives and **never** prunes. | Accept. Pruning the legacy source is a customer action after cutover, not a migration action. | STOP C |
| **P3-D05** | `search_reindex_weekly.py` has no Databricks target: it reads two in-cluster HTTP services and writes a MeiliSearch index. | **Remove from Databricks scope**; it stays a service-side job. Forcing it onto Databricks would add a warehouse-to-cluster network dependency and a job that cannot be reconciled, in exchange for nothing. | STOP C |
| **P3-D06** | The Scala rollup is pure set-based aggregation (C-7.1, C-7.2) with no JVM-specific behaviour. | Convert to SQL on Delta. No JAR task, no cluster, no `spark_jar_task`. | STOP C |
| **P3-D07** | The rollup's nightly CronJob reads a baked-in seed file and writes to an `emptyDir` (F-0.5, F-0.6). Migrating it produces a durable table nobody currently reads. | Migrate it — it is cheap and the output is obviously useful — but ask the user at STOP E whether the real production job has a real input and a real consumer, because this estate says it has neither. | STOP C + STOP E |

### Behaviour changes, named

Stated in every wave brief and in the STOP E packet, in prose.

| id | Change | Blast radius |
|---|---|---|
| **P3-D01** | Events are landed durably instead of consumed off a queue. | None to a single run's output. Makes reruns possible, which the legacy could not do at all. |
| **P3-D02** | A Postgres/serving-layer failure fails the run instead of being swallowed. | Differs only on a run where the legacy produced an S3 report without its matching summary row. |
| **P3-D03** | No deletes from S3 until a human enables them. | The target is strictly safer than the legacy. The delete set is proven equal first. |
| **P3-D04** | No deletes from DynamoDB, ever. | The legacy does not successfully delete either (F-0.4), so in this estate the observable behaviour is identical. |
| **P3-D08** | `execution_date` becomes an explicit parameter (C-1.2). | Additive. A same-day run is unchanged. |
| — | Converted code reads no credentials from `config.ini`; secrets are by name from scope `ow_tp`. | Operational only. |

Everything else reproduces the legacy exactly, including the 31-day/30-day window mismatch
(C-3.1), the `"unknown"` user appearing in `top_users` but not in `active_users` (C-2.7), the
hard-coded 2019 storage price (C-4.7), and the hard-coded compliance booleans (C-5.5).

## 4. Waves

Wave 1 has five independent batches, so it runs through `migration-fanout` / `run_workflow`
at width 5 — the first wave in this engagement wide enough to justify it. Waves 0, 2 and 3 are
single-batch and run serially, with manifests still written in the fan-out shape so the
collision check and the circuit breaker apply.

| Wave | Units | Depends on | Verify depth |
|---:|---|---|---|
| 0 | `p3-foundations` | — | none (no data movement); captures the legacy baseline |
| 1 | `p3-analytics-daily`, `p3-storage-cleanup`, `p3-audit-archive`, `p3-usage-rollup`, `p3-search-reindex` | wave 0 contract + baseline | full row parity per unit; `p3-storage-cleanup` adds delete-set equality; `p3-search-reindex` is structural (scope removal) |
| 2 | `p3-user-activity` | wave 1 (`p3-analytics-daily` gold) | full row parity on gold + report byte compare |
| 3 | `p3-orchestration` | wave 2 | structural: task graph, retries, concurrency, PAUSED state, no new cluster |

Circuit breaker: 3 same-class failures halts the wave and I stop and report. Recon re-runs
capped at 3 per unit. A write-target collision or an undeclared target is a halt, not a fix.

## 5. Recon gate

Source is DynamoDB, S3 and a seed file — not Oracle — so the harness's untested Oracle
adapter limitation does not apply. Both sides read through the tested `databricks` adapter and
the official harness verdict is the merge gate. Tolerances are the frozen ones in
`.migration/03_recon_tolerances.json`; changing them needs a human decision recorded by the
parent.

Independence, the same rule as pipeline 2 — never reconcile output against the artifact that
produced it:

1. **Source side.** Wave 0 seeds a deterministic pipeline-3 fixture into the estate's own
   LocalStack (DynamoDB `otterworks-analytics-events` and `otterworks-audit-events`, the data
   lake bucket, the file-storage buckets that `config.ini` names, and an SQS-shaped payload
   file standing in for the queue that does not exist), then runs the **real legacy scripts**
   over it. Their gzip/JSON outputs are loaded verbatim into `ow_tp.bronze.*_legacy_baseline_*`
   and never touched again.
2. **Target side.** The converted jobs read the **same raw inputs** and recompute from
   scratch. They never read a baseline table.
3. The harness compares the two, recomputing from the target platform.

### Two of the legacy jobs mutate the fixture they read

Step 1 above is not safe as written for `p3-storage-cleanup` or `p3-analytics-daily`. Both
legacy scripts destroy their own input: the cleanup job copies each orphan to quarantine and
then `delete_object`s the original, and `analytics_daily.py` deletes every SQS batch it reads
(F-0.1). Running the legacy first and then pointing the target at "the same raw inputs" would
hand the target a bucket the legacy had already emptied, and the delete-set equality gate in
§5 would be comparing two different inputs — it would pass trivially and prove nothing.

So wave 0 pins the input before the legacy touches it, and gives each side its own state:

- **Snapshot first, then run.** The fixture seeder writes an immutable input snapshot — for
  the cleanup unit, the full `list_objects_v2` listing (key, size, `last_modified`) of the
  file bucket plus the projected `s3_key` scan of `otterworks-file-metadata`; for analytics,
  the SQS-shaped payload file and the DynamoDB scan. The snapshot is written to the landing
  volume and is the declared input of **both** sides. It is produced before any legacy
  invocation and is never regenerated from post-run state.
- **Disjoint state per side.** The legacy runs against a per-run clone of the bucket
  (`ow-tp-p3-legacy-<run>`), seeded from the snapshot; the target reads the snapshot only and
  writes nothing to S3 at all. The two never share a mutable object.
- **Reseed between probes.** Each legacy probe re-seeds its clone from the snapshot first, so
  probe order cannot change probe results and a rerun is meaningful.

This keeps the legacy estate itself read-only — the clone is an `ow-tp-`-prefixed migration
resource, not the estate's bucket — and makes "equal delete sets" a real claim: both sides
derived a set from one pinned listing, independently.

The audit unit needs the same care for a different reason. F-0.4 says the legacy behaves
three different ways depending on record shape, so wave 0 runs all three probes (`A-estate`,
`A-tsonly`, `A-full`) against separately seeded table slices, and `A-estate` — the shape the
audit-service actually writes — has "produced nothing" as its expected baseline.

Idempotency is proven by an actual second run of each unit, not asserted. For
`p3-analytics-daily` that is only possible because of P3-D01: the legacy itself cannot be run
twice on the same input, which is recorded as an unverified path rather than papered over.

Per-unit gate:

| Unit | Merge evidence |
|---|---|
| `p3-analytics-daily` | row parity on the four gold outputs + byte compare of the three gzip members (`mtime=0` makes them reproducible) |
| `p3-user-activity` | row parity on gold + byte compare of `activity_report.json` modulo `generated_at` |
| `p3-storage-cleanup` | **set equality of the delete set** (key + size) derived by both sides from the same pinned pre-run inventory snapshot, plus row parity on the report |
| `p3-audit-archive` | all three F-0.4 probes: `A-estate` must produce no archive on either side, `A-tsonly` and `A-full` compare as set equality of archived ids including the three cutoff boundary probes, plus byte compare of the gzip archive member |
| `p3-usage-rollup` | row parity of `usage_rollup_daily` against the real Scala job's JSON over the same pinned NDJSON input |
| `p3-search-reindex` | no recon: no data movement (P3-D05) |
| `p3-orchestration` | structural only: no data movement |

`.migration/recon/<unit>/<unit>.recon.json`, `"kind": "recon-report"`, one live merge-evidence
run per unit.

## 6. Secrets

`etl/config.ini` holds plaintext AWS keys, a Postgres password and a MeiliSearch key, and it
is committed, so those credentials are in source history. Converted code references names
only, in scope `ow_tp`:

| Legacy `config.ini` field | Secret name |
|---|---|
| `aws.access_key`, `aws.secret_key` | `ow_tp/aws_migration_access_key_id`, `ow_tp/aws_migration_secret_access_key` |
| `database.password` | `ow_tp/analytics_postgres_password` |
| `services.meilisearch_api_key` | not migrated — P3-D05 removes the unit from scope |

Rotation of the exposed credentials is the customer's job, not mine. It is carried into the
STOP E packet as a follow-up with an owner, not fixed here.

## 7. Capability contract

```json
{
  "identity": "2e90bc1d-e9a1-4703-8c48-ad28ebb1864d",
  "host": "https://dbc-8bc9474f-40ae.cloud.databricks.com",
  "catalogs": ["ow_tp"],
  "guard_mode": "block",
  "stop_mode": "soft",
  "ready": true
}
```

`factory-doctor` at plan time: 15 ok, 2 fail. Identity, host, warehouse, allowlist,
`allowlist_matches_contract`, harness self-test, recon drivers, and both hook checks pass —
the platform hook probe was run in this session and the guard blocked it, naming its nonce.
The two fails are `delete_evidence` and `source_principal_read_only`, which need per-unit ids
and a source-secret name; they clear once the unit mapping specs under `.migration/units/p3-*/`
exist, which wave 0 adds. The doctor reruns before every wave.

## 8. Repo gates before each PR

`make tp-validate-contracts`, `make tp-validate-recon`, `make tp-validate-schemas`,
`make tp-smoke`, the repo's `tp-pre-pr-self-check` checklist, and the unit's live recon
verdict. No PR body names an individual, carries a credential value, or carries a real
distribution-list address.

## 9. Not done by this child

No production repoint, no schedule activation, no cutover, no credential rotation, no merge of
my own PRs, and no approval of any stop on the user's behalf. Pipeline 3 parks at STOP E.

## 10. Questions carried to STOP E

Each is stated as a fact about what is in this repository, with no claim about what a
production deployment does. None is answered by guessing.

| # | What we found | The question |
|---:|---|---|
| 1 | The Scala usage rollup runs nightly at 02:00 UTC from a Helm CronJob, reads a seed file baked into the image, and writes to an `emptyDir` that is destroyed on pod exit (F-0.5, F-0.6). | Does the real job have a real input and a real consumer? If not, is migrating it worth doing at all? |
| 2 | `storage_cleanup_daily.py` reads bucket `otterworks-file-storage` from `config.ini`; the estate's file storage is `otterworks-files`, so the job dies on its first list call (F-0.3). | Is the production config different, and if so has this job been deleting objects? Nothing here can answer that. |
| 3 | `audit_archive_weekly.py` filters on lowercase `timestamp`; the audit-service writes uppercase `Timestamp` and no `event_id`, so the scan matches nothing and the job exits 0 having archived nothing (F-0.4). Where records *do* carry `timestamp`, deletes fail on the key schema and are swallowed (F-0.4a) or the job crashes after uploading (F-0.4b). | Has audit archival been silently archiving nothing? This is a retention/compliance question, not a migration one, and it needs an owner. |
| 4 | `analytics_daily.py` deletes the SQS messages it reads (F-0.1), and neither the queue nor `otterworks-analytics-events` exists in this estate (F-0.2). | The SQS path is reconciled against a payload-file stand-in, not a live queue. That is an unverified path and is listed as one. |
| 5 | `config.ini` holds plaintext AWS keys, a Postgres password and a MeiliSearch key, committed to source history (F-0.8). | Rotation, by their owner. Converted code uses names only; the exposure in history is not something a migration can undo. |
| 6 | `search_reindex_weekly.py` writes MeiliSearch and reads two in-cluster HTTP services (F-0.7, P3-D05). | Confirmed out of Databricks scope as a coverage gap. Who owns it service-side after cutover? |
