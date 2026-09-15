# Pipeline 3 — product analytics record contract (wave 0)

Status: **proposed, pinned at STOP C**. Nothing in pipeline 3 is built before this is
approved.

This is the behavioural contract for the five Python cron jobs and the Scala usage rollup.
It is written from the legacy source and from the estate's own configuration, not from the
comments in the scripts. Where the legacy is wrong, the wrong behaviour is the contract
(`.migration/06_decisions.md`, dirty-output rule); where reproducing it is unsafe or
impossible, the deviation is named here and carried into every wave brief, unit PR and the
STOP E packet.

Evidence tags:

- `source` — read directly out of the legacy file cited.
- `estate` — read out of the estate's own infrastructure (crontab, Helm chart,
  `scripts/localstack-init.sh`, `docker-compose.yml`).
- `wave-0 probe` — to be produced in wave 0 by running the real legacy script over a pinned
  fixture and capturing its output. Clauses tagged this way are **proposed** until the probe
  lands; the probe either confirms the clause or the contract is corrected before wave 1.

---

## 0. Estate facts that change the shape of the work

| id | Fact | Evidence |
|---|---|---|
| **F-0.1** | `analytics_daily.py` **consumes** its SQS input: every batch it reads is deleted with `delete_message_batch`. The legacy job is therefore not re-runnable on the same input, and a second run the same day finds an empty queue. | `analytics_daily.py:104`, `source` |
| **F-0.2** | The SQS queue it polls, `.../123456789012/otterworks-analytics`, and the DynamoDB table it scans, `otterworks-analytics-events`, are created by nothing in this estate. `scripts/localstack-init.sh` creates neither. | `estate` |
| **F-0.3** | `storage_cleanup_daily.py` reads buckets `otterworks-file-storage` and `otterworks-file-quarantine` from `etl/config.ini`. Neither exists in the estate; the file-service uses `otterworks-files`. Against the estate as configured, the job fails on the first `list_objects_v2` call and exits 1 before deleting anything. | `etl/config.ini:22-23`, `scripts/localstack-init.sh:14`, `docker-compose.yml:112`, `estate` |
| **F-0.4** | `audit_archive_weekly.py` **matches nothing the audit-service writes.** Its scan filter is `#ts < :cutoff` with `#ts` → `timestamp` (lowercase). `DynamoDbAuditRepository.SaveEventAsync` writes `id`, `Id`, `UserId`, `Action`, `ResourceType`, `ResourceId`, `Timestamp` — uppercase `Timestamp`, in .NET round-trip `"O"` format, and no lowercase `timestamp` and no `event_id` at all. A DynamoDB filter expression excludes items that do not have the named attribute, so against service-written records the scan returns zero items, `archive_count == 0`, and the job `sys.exit(0)`s at `:93`. It writes no archive, no compliance report, and never reaches the delete loop. | `audit_archive_weekly.py:70-93`, `services/audit-service/src/Services/DynamoDbAuditRepository.cs:24-35`, `estate` |
| **F-0.4a** | The wrong-key-schema delete is therefore **second-order**: it only happens on records that carry a lowercase `timestamp`. On such a record the delete key is `{event_id, timestamp}` while the table's key schema is `id` alone, every `delete_item` raises a validation error, and every one is swallowed by a bare `except: pass` (`:152-154`, `:164-165`). The archive is written, the source is never pruned, and `events_deleted_from_source` reports 0. | `audit_archive_weekly.py:139-169`, `scripts/localstack-init.sh:60-64`, `source` |
| **F-0.4b** | A record carrying lowercase `timestamp` but **no** `event_id` is worse than either: `key = {"event_id": event["event_id"], ...}` at `:140-143` sits **outside** the `try`, so the `KeyError` propagates to the top-level handler and the job exits 1 — after the archive has already been uploaded. Archive-written-then-fail is a real path and the retry re-uploads under the same key. | `audit_archive_weekly.py:139-155`, `source` |
| **F-0.5** | The Scala rollup **is** scheduled, in Helm rather than crontab: `infrastructure/helm/analytics-service` ships a CronJob, `cronjob.enabled: true`, `schedule: "0 2 * * *"` (02:00 UTC nightly). | `infrastructure/helm/analytics-service/values.yaml:67`, `estate` |
| **F-0.6** | That CronJob's input is `/seed/usage-events.ndjson`, a deterministic seed baked into the image, and its output goes to `/var/lib/otterworks/usage-rollup.json` on an `emptyDir` volume, which is destroyed when the pod exits. The nightly rollup aggregates a fixed file and throws the result away. No consumer can be reading it. | `templates/cronjob.yaml:58-64`, `values.yaml:74-76`, `estate` |
| **F-0.7** | `search_reindex_weekly.py` reads two live HTTP services and writes a MeiliSearch index. There is no Databricks target in it at any point. | `search_reindex_weekly.py`, `source` |
| **F-0.8** | All five Python jobs read plaintext AWS keys, a Postgres password and a MeiliSearch key out of `/opt/etl/config.ini`, which is committed. | `etl/config.ini`, `source` |
| **F-0.9** | **The estate has two event-type vocabularies and pipeline 3 spans both.** `analytics_daily.py` compares `eventType` against snake_case literals (`document_created`, `file_uploaded`, …), which is what file-service (`events.rs`, camelCase envelope: `eventType`/`ownerId`/`fileId`/`sizeBytes`) and document-service publish to SNS→SQS. `analytics-service`'s own `EventType` constants are dotted (`document.created`, `file.uploaded`) and are what the usage rollup consumes. The two never meet in the legacy, so each unit is correct on its own input — but a dotted event reaching `analytics_daily.py` is counted in `total_events` and the hourly breakdown while contributing to none of the document or file metrics. | `analytics_daily.py:203-245`, `file-service/src/events.rs:85-95`, `document-service/app/services/document_service.py:72`, `analytics-service/.../model/AnalyticsEvent.scala:38-43`, `source` |
| **F-0.10** | **A single non-numeric `sizeBytes` aborts the entire analytics run.** `bytes_uploaded` is a pandas `.sum()` over the column, which raises `TypeError: unsupported operand type(s) for +: 'int' and 'str'` on a mixed int/str column. The top-level handler catches it, the job exits 1, and **nothing** is written — not the summary, not the hourly breakdown, not the report. One malformed record therefore costs the whole day's output, not one row. file-service types `size_bytes` as `u64` so the estate cannot currently produce this, which is why it is a latent fault rather than an observed one. | `analytics_daily.py:238`, `file-service/src/events.rs:24`, `source`; reproduced by `gen_p3_fixture.py --poison` |

F-0.2, F-0.3, F-0.4 and F-0.6 are stated as what is true of **this repository's estate**. They
are not a claim about what a production deployment does; each one is a STOP E question, listed
in the plan.

**Consequence of F-0.4 for the baseline.** `audit_archive_weekly.py` has three distinct
behaviours depending on the shape of the records in the table, and which one is "the legacy
behaviour" is not a matter of opinion — it depends on who wrote the record. Wave 0 probes all
three rather than picking one:

| probe | record shape | expected legacy behaviour |
|---|---|---|
| `A-estate` | as `DynamoDbAuditRepository` writes them: `id`, `Id`, `Timestamp` | scan returns 0, exit 0, **no archive object, no compliance report** |
| `A-tsonly` | `id` + lowercase `timestamp`, no `event_id` | archive uploaded, then `KeyError` → exit 1 (F-0.4b) |
| `A-full` | `id` + `timestamp` + `event_id` | archive uploaded, all deletes fail and are swallowed, compliance report written with `events_deleted_from_source: 0` (F-0.4a) |

`scripts/tp_seed/seed_audit_events.py` writes the `A-full` shape. It is a useful probe of the
archive path, but it is **not** the estate's record shape, and a recon that only exercises it
would be green about a path the running system never takes. The archive/serialisation clauses
in §5 are contract for `A-full` and `A-tsonly`; for `A-estate` the contract is "produces
nothing", and that emptiness is itself the thing to reconcile.

---

## 1. Shared conventions

| Clause | Contract | Evidence |
|---|---|---|
| C-1.1 | Every job derives its partition date as `datetime.now(tz=utc).strftime("%Y-%m-%d")` at the moment it starts. There is no execution-date parameter and no backfill path: a job run late on 2026-09-15 writes the 2026-09-15 partition regardless of when its input happened. | all five scripts, `source` |
| C-1.2 | The target takes `execution_date` as an explicit job parameter defaulting to the run's UTC date. This is a **behaviour addition**: it makes reruns and backfills possible without changing what a same-day run produces. | derived |
| C-1.3 | `generated_at` / `updated_at` fields are target-side wall clock and are excluded from every recon comparison. | all scripts, `source` |
| C-1.4 | Timestamps are compared ISO-canonicalized; counts and byte totals are compared exactly; derived floats within 1e-9 relative, per the frozen tolerances. | `.migration/03_recon_tolerances.json` |
| C-1.5 | No converted artefact reads `etl/config.ini`. Every credential is referenced by secret name in scope `ow_tp`. No literal, no environment default that falls back to a literal, no value in a log, notebook output, PR body or recon artefact. | guardrail |

## 2. `analytics_daily.py`

### 2.1 Input

| Clause | Contract | Evidence |
|---|---|---|
| C-2.1 | Input is the union of (a) everything currently in the SQS queue, up to 10 000 messages read 10 at a time, and (b) every DynamoDB item whose `event_date` **string-prefix-matches** today's date. | `:52-142`, `source` |
| C-2.2 | The SQS side is **not** date-filtered. An event of any age sitting in the queue is counted into today's partition. | `:60-109`, `source` |
| C-2.3 | A message whose body is not valid JSON is dropped silently and is **not** deleted from the queue, so it is re-read on every subsequent run forever. | `:100-102`, `source` |
| C-2.4 | Three consecutive SQS receive failures end the poll loop and the job continues with whatever it has. A partial read is indistinguishable from a complete one in the output. | `:78-85`, `source` |
| C-2.5 | Zero total events → the job prints a warning and `sys.exit(0)` **before writing anything**. No S3 object, no Postgres row. Yesterday's report stays in place and is silently stale. | `:148-150`, `source` |

### 2.2 Derivation

| Clause | Contract | Evidence |
|---|---|---|
| C-2.6 | `resolved_user_id` is the first non-null, non-empty value in strict order `ownerId`, `editedBy`, `authorId`, `deletedBy`, `userId`; otherwise the literal string `"unknown"`. | `:163-167`, `source` |
| C-2.7 | `active_users` counts distinct `resolved_user_id` **excluding** `"unknown"`. But `top_users` **includes** `"unknown"` as if it were a user, and it is usually the largest row. The two numbers disagree by design. | `:183-200`, `source` |
| C-2.8 | `hour` is the two-digit hour of `timestamp` parsed as ISO-8601 with a trailing `Z` accepted. Anything that is not a parseable string — missing, numeric, malformed, null — becomes `"00"` and is bucketed together with genuine midnight events. If the input has no `timestamp` column at all, every event is hour `"00"`. | `:170-180`, `source` |
| C-2.9 | `eventType` falls back to `event_type`, then to the literal `"unknown"` if neither column exists. The fallback is **column-level, not row-level**: if any row has `eventType`, rows missing it get pandas `NaN`, not `"unknown"`. | `:157-160`, `source`; confirmed by `wave-0 probe` |
| C-2.10 | `bytes_uploaded` is `int(sum of sizeBytes over file_uploaded rows, nulls as 0)`. The sum goes through a pandas float accumulation and is then truncated toward zero. For byte counts above 2^53 this loses precision; the target computes it as an exact integer sum and the difference is declared, not hidden. | `:232-233`, derived |
| C-2.11 | `active_documents` is the distinct non-null `documentId` over `document_created` ∪ `document_edited` rows. `active_files` is the distinct non-null `fileId` over `file_uploaded` ∪ `file_shared` ∪ `file_deleted` rows. Both are guarded on the column existing at all. | `:208-245`, `source` |
| C-2.11a | Every one of those comparisons is an exact match against a **snake_case** literal (F-0.9). An event carrying the dotted `analytics-service` spelling raises `total_events` and its hourly bucket, and its user is attributed and counted in `active_users` and `top_users`, but it is invisible to `documents_created`, `documents_edited`, `comments_added`, every file metric, `bytes_uploaded`, `active_documents` and `active_files`. The target reproduces the snake_case match exactly — it does **not** normalise the two vocabularies together, because that would change the numbers. | `:203-245`, `source`; confirmed by the wave-0 baseline: 28 `document_created` + 1 `document.created` on the input, `total_events` 249 and `documents_created` 28 on the output |
| C-2.12 | `top_users` is the first 100 rows of the user list sorted by total action count **descending, stable**: ties keep first-appearance order in the event frame, which is SQS-then-DynamoDB read order. The target reproduces this with an explicit `first_seen_ordinal` tiebreak; without it, tie order is not deterministic in SQL. | `:194-200`, derived |
| C-2.13 | `peak_hour` is the hour with the largest total event count; on a tie, the **numerically smallest hour** wins, because the dict is sorted by hour before `max` takes the first maximum. | `:259, :410`, `source` |

### 2.3 Output

| Clause | Contract | Evidence |
|---|---|---|
| C-2.14 | Four S3 objects per run: `summary.json.gz`, `hourly_breakdown.json.gz`, `top_users.jsonl.gz` under `analytics/daily/year=/month=/day=`, and `reports/analytics/daily/<ds>/report.json` uncompressed. All three gzip members are written with `mtime=0`, so they are byte-reproducible for identical input. | `:304-337, :426-437`, `source` |
| C-2.15 | One Postgres row per `report_date`, upserted on conflict. | `:355-392`, `source` |
| C-2.16 | **A Postgres failure is swallowed.** The job logs it, rolls back, and carries on to write the S3 report. The run exits 0. Downstream `user_activity_daily` then reads a Postgres table that is missing a day while the S3 side has it. | `:395-399`, `source` |
| C-2.17 | The target **fails loudly** instead. This is a named behaviour change: a day the legacy would have half-completed now fails the task and is retried by the job's retry policy. It changes output only on a run where the legacy would have produced an inconsistent pair of outputs. | derived, **behaviour change P3-D02** |

## 3. `user_activity_daily.py`

| Clause | Contract | Evidence |
|---|---|---|
| C-3.1 | The Postgres window is `report_date BETWEEN ds - 30 days AND ds` — **31 days inclusive**. The S3 window is `range(30)` day offsets, i.e. `ds-29 .. ds` — **30 days**. The two halves of the same report cover different windows. This is reproduced exactly. | `:79, :139-140`, `source` |
| C-3.2 | A missing, unreadable, non-gzip or non-JSON daily `top_users.jsonl.gz` is silently skipped by a bare `except`. A corrupt file and an absent file are indistinguishable, and a partially-consumed file contributes the lines read before the error. | `:173-176`, `source` |
| C-3.3 | `active_days` counts days on which the user appeared in `top_users` — i.e. days on which they were in the **top 100**, not days on which they were active. | `:166-167`, derived |
| C-3.4 | `peak_active_users` is `max(active_users)` over the daily rows, not a distinct count and not a total, despite the variable being named `total_users`. | `:185`, `source` |
| C-3.5 | `avg_daily_events = round(total_events / len(daily_summaries), 2)`, Python banker's rounding, 0 when there are no rows. The target rounds half-to-even to match. | `:186, :196`, `source` |
| C-3.6 | User ordering is by `total_actions` descending, stable, so ties keep first-appearance order, which is **today backwards** (offset 0 first). `user_summaries` is the first 500, `top_users` the first 20. | `:178, :200-201`, `source` |
| C-3.7 | A Postgres failure here **exits 1** — the opposite of C-2.16. The contract keeps the loud behaviour. | `:113-117`, `source` |
| C-3.8 | Three S3 objects: the dated report, a `latest/activity_report.json` overwrite, and `user_summaries.jsonl` (written only when there is at least one user). | `:215-239`, `source` |
| C-3.9 | The dependency on `analytics_daily` is a real data dependency (Postgres row + S3 objects), expressed in the legacy only as a 3-hour cron gap. The target wires it as a task edge. | `estate` (`etl/crontab`) |

## 4. `storage_cleanup_daily.py` — destructive

| Clause | Contract | Evidence |
|---|---|---|
| C-4.1 | An object under `files/` in the file-storage bucket is **orphaned** iff its exact key is absent from the set of non-empty `s3_key` values in `otterworks-file-metadata`. Exact string match; no normalisation, no prefix logic. | `:105-113`, `source` |
| C-4.2 | The scan of the metadata table and the listing of the bucket are not consistent with each other. A file written between the two reads is listed but not yet referenced, and is deleted. This race is **not** reproduced: the target computes the delete set from a point-in-time snapshot of both sides. | derived, **behaviour change P3-D03** |
| C-4.3 | Each orphan is copied to `quarantined/<ds>/<source-key>` in the quarantine bucket and then deleted from the source bucket. A copy failure is logged, counted as `objects_failed`, and the source object is left alone. The run still exits 0. | `:134-151`, `source` |
| C-4.4 | The target **never deletes by default.** It computes and persists the delete set, and deletion is a separate task behind an explicit job parameter that is `false` in the bundle. Turning it on is a human action after the delete sets have been compared. | guardrail, parent instruction |
| C-4.5 | Merge evidence for this unit is **set equality of the delete set**: the exact set of keys the legacy would remove versus the exact set the target computes, compared as sets, plus the per-key byte size. Not a count. | guardrail |
| C-4.6 | Zero orphans still produces a report. `orphan_percentage` is 0 when the bucket is empty rather than a division error. | `:122-124, :177-179`, `source` |
| C-4.7 | `estimated_monthly_savings_usd` is `round(orphaned_bytes / 1024^3 * 0.023, 4)` — a hard-coded 2019 S3 Standard rate. It is reproduced verbatim as a number, and flagged as stale rather than corrected. | `:161-162`, `source` |

## 5. `audit_archive_weekly.py` — destructive

| Clause | Contract | Evidence |
|---|---|---|
| C-5.1 | The cutoff is `midnight UTC of ds minus 90 days`, rendered `%Y-%m-%dT%H:%M:%SZ`-shaped via `isoformat() + "Z"`, and compared **as a string** against the item's lowercase `timestamp` attribute. Because both sides are zero-padded and left-aligned on the same fields, the string compare is chronologically correct for that format; the strict `<` means an event exactly on the cutoff is **not** archived. Items lacking a lowercase `timestamp` are not "older than the cutoff" and not "newer" — they are excluded from the filter entirely (F-0.4), which is why the estate's own records never match. | `:52-74`, `source` |
| C-5.2 | The archive is one gzip JSONL member per run, `mtime=0`, one line per item, `Decimal` rendered as `int` when integral and `float` otherwise, key order as DynamoDB returned it. Written to `audit-archive/year=<yyyy>/week=<ds>/audit_events.jsonl.gz` with storage class `GLACIER`. Note `week=` holds a full date, not a week number. | `:96-125`, `source` |
| C-5.3 | The delete step never succeeds (F-0.4a) and is swallowed. Where the archive path runs at all, it is therefore append-only over an unshrinking source, and every weekly run re-archives every event past the cutoff under a new `week=<ds>` key. | `:139-165`, `estate` |
| C-5.4 | The target **never deletes from the source.** The legacy system is read-only in every phase. Pruning the source is a customer action after cutover, not a migration action, and is listed at STOP E. | guardrail |
| C-5.5 | The compliance report's `gdpr_compliant` / `soc2_compliant` / `data_encrypted_*` flags are hard-coded `true`. They are reproduced as-is, and the fact that they are constants rather than checks is recorded at STOP E. | `:188-193`, `source` |
| C-5.6 | Zero events past the cutoff → `sys.exit(0)` before writing anything, including the compliance report. A quiet week produces no evidence of having run. | `:91-93`, `source` |

## 6. `search_reindex_weekly.py` — scope decision

| Clause | Contract | Evidence |
|---|---|---|
| C-6.1 | The job deletes both MeiliSearch indices, recreates them, applies settings, then pages the document-service and file-service APIs and bulk-indexes the results. Between the delete and the last bulk-index, **search is degraded or empty**. | `:42-275`, `source` |
| C-6.2 | Its only data store is a MeiliSearch index. It reads two live HTTP microservices. It touches no warehouse, no S3, no database. | `source` |
| C-6.3 | Proposed: this unit is **removed from Databricks scope** and stays a service-side job. The reasoning and the alternative are in the plan; a Databricks job that calls two in-cluster HTTP services on a schedule and writes a search engine would be a worse operational fit than what exists, not a better one. | plan, **P3-D05** |
| C-6.4 | If the decision goes the other way, the unit still cannot be reconciled with the harness: there is no Delta target to compare against. The gate would be an index document count and a settings diff, which is a different and weaker gate, stated up front. | derived |

## 7. Scala `UsageRollupJob` / `UsageRollupAggregator`

| Clause | Contract | Evidence |
|---|---|---|
| C-7.1 | The aggregator is pure and deterministic: group events by UTC calendar date of `timestamp`, emit one row per day sorted ascending by date. Same input, same output, always. | `UsageRollupAggregator.scala`, `source` |
| C-7.2 | Per day: `totalEvents` = row count; `activeUsers` = distinct `userId`; six per-event-type counts; `storageAllocatedBytes` / `storageReleasedBytes` = sum of `metadata["bytes"]` parsed as `Long` over the matching event type, where a missing or unparseable value contributes **0, silently**; `netStorageBytes` = allocated − released and may be negative. | `UsageRollupAggregator.scala:26-47`, `source` |
| C-7.3 | Byte sums are `Long` addition. Nothing in the target may route them through a `DOUBLE`. | derived |
| C-7.4 | The report wrapper carries `windowStart` / `windowEnd` as the first and last rollup dates — which are the min and max **observed** dates, not a requested window; a gap day simply does not appear as a row. `dayCount` is the number of rows, not the span. | `UsageRollupJob.scala:51-61`, `source` |
| C-7.5 | `generatedAt` is `Instant.now()` and is excluded from recon. | `:53`, `source` |
| C-7.6 | This is set-based aggregation with no JVM-specific behaviour, so it converts to SQL on Delta. No JAR task, no cluster. | derived, **P3-D06** |
| C-7.7 | Today's output is discarded (F-0.6). The target writes a Delta table, which is a **new durable output**, not a like-for-like port of a consumer. Recon compares the target table against the report the real Scala job produces over the same pinned input. | derived |

## 8. What no recon in this pipeline covers

Named here, repeated in every unit PR and in the STOP E packet:

- **The SQS leg.** It is destructive on read (F-0.1) and the queue does not exist in the
  estate (F-0.2). Recon covers the DynamoDB leg and a landed, replayable copy of an SQS-shaped
  payload; it cannot prove behaviour against the live queue.
- **The partial-read path.** C-2.4's three-consecutive-failures exit cannot be provoked
  against a pinned fixture, so it is untested by construction.
- **Production resource names.** F-0.2, F-0.3 and F-0.4 are read off this estate. If the
  production estate has different buckets, a different table key schema or a live queue, the
  delete sets and archive volumes computed here do not transfer.
- **Scale.** Fixtures are hundreds of rows. Nothing here exercises the 10 000-message SQS cap,
  a paginated DynamoDB scan, or a bucket large enough to matter to C-4.1.
- **Structure.** Grants, table properties, column comments and volume ACLs are outside
  row-level parity, exactly as in pipelines 1 and 2.
- **Search.** Removed from scope under P3-D05; there is nothing to reconcile.
- **Timing.** Job graphs are verified structurally. No recon proves the converted schedule
  produces output at the same wall-clock time as cron did.
