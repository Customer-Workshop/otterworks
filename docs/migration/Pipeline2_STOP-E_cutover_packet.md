# Pipeline 2 — STOP E: cutover decision packet

**Pipeline:** OtterWorks finance close, the CUSTBILL batch chain (`sftp_ingest_poll.ksh` →
`parse_custbill_fixedwidth.sh` → `finance_excel_report.pl`, glued by `run_all.sh` and cron)
→ a Lakeflow Spark Declarative Pipeline plus two Lakeflow Jobs on `ow_tp`.
**Date:** 2026-09-15 · **Status:** awaiting customer decision · **Prepared by:** the
pipeline-2 migration session.

**Nothing here authorizes a cutover.** No consumer has been repointed, `CB77340` still drops
to the SFTP server, the legacy scripts and crontabs are untouched, and both target schedules
are PAUSED. Cutover needs the customer-held cutover principal and an explicit reply.

---

## 1. What is being asked

Four decisions. All four now carry a **parent-default answer, pending customer confirmation**:
the engagement parent chose them so the build could be finished and parked, and they are
recorded as defaults, not as customer decisions. **The customer holds the cutover principal**,
so none of them takes effect until the customer confirms them and authorizes cutover
separately. Only the first two need answering before anything can be scheduled.

| # | Decision | Parent default (pending customer confirmation) |
|---|---|---|
| **D3-01** | Does `MVSPROD` job `CB77340` keep dropping `CUSTBILL*.dat` on the SFTP server, or is it repointed at the governed volume `/Volumes/ow_tp/bronze/landing/custbill/`? | **Keep the SFTP drop for now.** The target lands from it, so the upstream mainframe job is not changed on cutover day. A repoint stays available later as a separate, reversible change. |
| **D4-01** | The close was mailed through a sendmail pipe that has been dead for years. Confirm the replacement: the governed gold table plus the byte-compatible file export, and the job's own failure notification instead of mail. | **Confirmed as built.** If a human consumer surfaces later they get the gold table or the volume export — not a revived mail pipe. The `on_failure` destination still needs a real value at cutover; it is empty today on purpose. |
| **P2-D05** | The Sunday 06:00 `run_all.sh` re-run has no replacement. Drop it, or recreate it? | **Dropped.** It re-emitted the same totals under a new filename; the every-15-minutes ingest and the 02:10 close already cover the work. Nothing recreates it today. |
| **P2-D04** | Timezone for both schedules. It also sets the date stamp in the export filename. | **UTC.** If finance reads the close by local business date, this is the one to revisit, because the timezone and the export filename convention are the same decision. |

---

## 2. Delivery state

5 waves, 4 units, all closed. One PR per unit into `tp-run/databricks-20260915T045714Z`.

| Wave | Unit | Replaces | Recon | PR |
|---|---|---|---|---|
| 0 | `p2-foundations` | — (contract, schedule model, plan, captured legacy baseline) | no data movement | #1599 |
| 1 | `p2-sftp-ingest` | `jobs/sftp_ingest_poll.ksh` | official **PASS**, live, full depth | #1603 |
| 2 | `p2-custbill-parse` | `jobs/parse_custbill_fixedwidth.sh` | official **PASS**, live, full depth | #1606, #1607 |
| 3 | `p2-finance-close` | `jobs/finance_excel_report.pl` | official **PASS**, live, full depth | #1608, #1609 |
| 4 | `p2-orchestration` | `run_all.sh` + the CUSTBILL cron entries | structural **PASS** (24 checks) | #1610, #1613 |

Unlike pipeline 1, these are **official harness verdicts** with `merge_eligible=true`: the
source here is files on disk, so the harness's Oracle-adapter limitation does not apply.
Money is exact, row counts exact, dates ISO-canonicalized, anomalies compared as sets, and
every result was recomputed from the target rather than from the artifact that produced it.
Idempotency was proven by an actual rerun in every wave.

One fix after wave 4 closed (#1613): both jobs used to start the shared pipeline directly,
and a pipeline allows one active update, so an ingest still running at 02:10 failed the close
with "Pipeline update already in progress" — reproduced in the workspace. The close now runs
the ingest job instead, so a late ingest delays the close rather than failing it; also proven
by running both at once.

What the target looks like today:

```
/Volumes/ow_tp/bronze/landing/custbill/   landed CUSTBILL*.dat, atomic, nothing deleted
ow_tp.bronze.custbill_raw                 one row per record, bytes preserved + file ledger
ow_tp.silver.custbill                     the fixed-width parse, byte-exact to the legacy .psv
ow_tp.silver.custbill_quarantine          additive observability, never a filter
ow_tp.silver.custbill_trailer_audit       declared vs parsed record counts
ow_tp.gold.custbill_finance_close         the close, as a governed table
/Volumes/ow_tp/gold/exports/custbill/     finance_billing_<stamp>.csv + the .xls byte copy
ow_tp_p2_custbill_ingest                  quartz 0 0/15 * * * ?   PAUSED
ow_tp_p2_finance_close                    quartz 0 10 2 * * ?     PAUSED
```

---

## 3. Dirty output is preserved, on purpose

The user pinned the legacy behaviour as the contract at STOP C, so the target reproduces the
defects rather than repairing them. The exported CSV and `.xls` are byte-identical to the
files the Perl itself produced over the pinned fixtures (md5 `de118d0223bb3a77fd83973a625fed8d`).
Preserved deliberately:

- a `|` inside a customer name shifts every later field, so the close still reports the
  nonsense groups `0US,UNKNOWN(D0)` and `000000020000,UNKNOWN(USD)`;
- amounts are coerced by leading numeric prefix, so junk contributes `0.00` and still counts
  a row; a negative on a field declared unsigned is read as written;
- `usd` and `USD` are separate groups, because the Perl's hash key is case-sensitive;
- dates are never validated;
- the `.xls` is a CSV with a lying extension.

**Quarantine never gates the output.** 116 silver rows reach the aggregation whether they are
quarantined or not; gold counts the same 114 records the legacy report counted, and the 2-row
gap is exactly the empty-customer rows the Perl also skips. No expectation drops a record.

One legacy defect is now **visible** rather than silent: `CUSTBILL_PROBE_001.dat` declares a
trailer of 15 and parses 14, because a customer id beginning `HDR` is deleted as a header
line. The target loses the same record — identical output — and reports the discrepancy in
`custbill_trailer_audit`. Whether to fix that is a customer call, not a migration call — it is
tracked as **P2-BEH-02** in §4.

---

## 4. Behaviour changes — what the target does *not* do the same way

| id | Change | Status |
|---|---|---|
| **P2-D01** | **The landing race is gone.** The legacy ingest checked file stability with a 1-second double-stat and the parse ran on a timer 5 minutes later, so it could read a half-written `.dat` and produce a close from it. The target lands atomically and makes the parse a dependency edge, so it cannot. | **Customer owns this.** Accepted at STOP C as the one real behaviour change. **Not testable** — it needs a producer raced mid-write, which pinned fixtures cannot do. If any downstream number ever depended on a partial read, it will now differ, and only the customer can say whether one did. |
| **P2-BEH-02** | **The `HDR`-prefix record loss in `CUSTBILL_PROBE_001`.** The legacy `sed` deletes every line starting `HDR`, so a customer id beginning `HDR` is deleted as if it were a header: the file declares a trailer of 15 and 14 records are parsed. The target loses the same record — the output is identical — and reports the gap in `ow_tp.bronze.custbill_trailer_audit`. | **Customer owns this.** Migration preserves the defect on purpose; whether to fix it, and what the corrected close would be worth, is a business call, not a migration call. Nothing changes until the customer asks. |
| **P2-OPS-01** | No source file is deleted, no `/tmp` lock files are written, and a failed stage fails the run instead of being swallowed by `|| true`. | Accepted at STOP C. |
| **D4-01** | sendmail is dropped; the job's `on_failure` notification replaces it. | Parent default, pending customer confirmation (§1). |

---

## 5. What the reconciliation does not cover

Stated plainly, because "all units passed" would be misleading:

- **Rows, not structure.** The harness compares row data. It does not compare Delta table
  properties, comments, or **grants** — including the grants on the export volume path.
- **Retries and the failure notification are configured, not exercised.** Nothing was failed
  on purpose, and the destination is empty by design, so `on_failure` delivers nothing today.
- **The schedules never fired.** They are PAUSED, so the quartz expressions are verified as
  configuration only.
- **The export file *name*** is not reconciled. The legacy took the date from the ETL box's
  local clock; the job passes an explicit stamp (see P2-D04).
- **The SFTP hop itself** is out of scope: recon starts at the landed bytes.
- **Only the pinned fixture set** is exercised — other currencies, record types and delimiter
  placements are not.
- **`source_principal_read_only`** is still unverified: the factory doctor has no privilege
  query for a Databricks-family source. 16 of 17 rows green.
- Wall-clock columns (`parsed_at`, `quarantined_at`, `closed_at`) are excluded from the
  diffs and fingerprints as target-side values with no legacy counterpart.
- **The close's 3600-second timeout is not sized against real ingest volumes.** The close now
  waits for the ingest job (see §2), and that wait counts against its own timeout, so a long
  ingest or a queue of them can in principle exhaust it and produce no export for the day.
  Against the pinned fixtures an ingest run takes minutes, so it never came close; the real
  drop is bigger. Measure a production-sized ingest at cutover and set the close timeout
  above the worst-case wait plus one full ingest and export.

---

## 6. What has not been touched

- No production cutover. `CB77340` still drops to SFTP; the legacy scripts, both crontabs and
  the legacy box are unchanged. The migration reads the fixtures, it does not disable anything.
- No new clusters: everything runs serverless, alongside the existing warehouse
  `565cd2fd713738c4`.
- No live schedule: both jobs are PAUSED, and the bundle target pins
  `presets.trigger_pause_status: PAUSED` so nothing it deploys can run on a timer.
- No live pager: the `on_failure` destination is an empty bundle variable.
- Nothing under `billing.` or belonging to pipeline 1.

---

## 7. Cutover sequence, once authorized

1. Confirm **all four** decisions in §1, not just the two blocking ones: D3-01 and D4-01 gate
   the shape, and P2-D04 (timezone, which also sets the export date stamp) and P2-D05 (the
   dropped Sunday re-run) take effect the moment the schedules are deployed and unpaused, so
   a parent default must not become live without the customer saying so. Then set
   `failure_webhooks` to a real notification destination, and size `timeout_seconds` on the
   close against the real ingest duration (see §5).
2. Deploy the bundle to a production target — that drops the development-mode `[dev ...]`
   name prefix, leaving `ow_tp_p2_custbill_ingest` and `ow_tp_p2_finance_close`.
3. Run both jobs once by hand against the day's real drop and compare the export against the
   legacy run for the same day. Both chains can run in parallel: the target deletes nothing
   and writes only under `ow_tp`.
4. Unpause the ingest schedule first, leave the close paused for one cycle, confirm silver
   keeps up, then unpause the close.
5. Disable the CUSTBILL cron entries on the legacy box — the one change to the legacy estate,
   and the customer's to make. Keep the scripts in place as the rollback.
6. Rollback at any point: pause both jobs, re-enable the cron entries. The target has removed
   nothing the legacy chain needs.

**This packet does not authorize step 2 onward.** Pipeline 2 stops here.
