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

Four decisions. Only the first two need answering before anything can be scheduled.

| # | Decision | Recommendation |
|---|---|---|
| **D3-01** | Does `MVSPROD` job `CB77340` keep dropping `CUSTBILL*.dat` on the SFTP server, or is it repointed at the governed volume `/Volumes/ow_tp/bronze/landing/custbill/`? | Keep the SFTP drop at first and land from it, so the upstream mainframe job is not changed on cutover day. Repoint later as a separate, reversible change. |
| **D4-01** | The close was mailed through a sendmail pipe that has been dead for years. Confirm the replacement: the governed gold table plus the byte-compatible file export, and the job's own failure notification instead of mail. | Confirm as built. If a human consumer surfaces later they get the gold table or the volume export — not a revived mail pipe. Give the `on_failure` destination a real value at cutover; it is empty today on purpose. |
| **P2-D05** | The Sunday 06:00 `run_all.sh` re-run has no replacement. Drop it, or recreate it? | Drop it. It re-emitted the same totals under a new filename; the every-15-minutes ingest and the 02:10 close already cover the work. |
| **P2-D04** | Timezone for both schedules. UTC is proposed. It also sets the date stamp in the export filename. | Confirm UTC, unless finance reads the close by local business date — in which case name the timezone and the filename convention together, because they are the same decision. |

---

## 2. Delivery state

5 waves, 4 units, all closed. One PR per unit into `tp-run/databricks-20260915T045714Z`.

| Wave | Unit | Replaces | Recon | PR |
|---|---|---|---|---|
| 0 | `p2-foundations` | — (contract, schedule model, plan, captured legacy baseline) | no data movement | #1599 |
| 1 | `p2-sftp-ingest` | `jobs/sftp_ingest_poll.ksh` | official **PASS**, live, full depth | #1603 |
| 2 | `p2-custbill-parse` | `jobs/parse_custbill_fixedwidth.sh` | official **PASS**, live, full depth | #1606, #1607 |
| 3 | `p2-finance-close` | `jobs/finance_excel_report.pl` | official **PASS**, live, full depth | #1608, #1609 |
| 4 | `p2-orchestration` | `run_all.sh` + the CUSTBILL cron entries | structural **PASS** (20 checks) | #1610 |

Unlike pipeline 1, these are **official harness verdicts** with `merge_eligible=true`: the
source here is files on disk, so the harness's Oracle-adapter limitation does not apply.
Money is exact, row counts exact, dates ISO-canonicalized, anomalies compared as sets, and
every result was recomputed from the target rather than from the artifact that produced it.
Idempotency was proven by an actual rerun in every wave.

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
`custbill_trailer_audit`. Whether to fix that is a customer call, not a migration call.

---

## 4. Behaviour changes — what the target does *not* do the same way

| id | Change | Status |
|---|---|---|
| **P2-D01** | **The landing race is gone.** The legacy ingest checked file stability with a 1-second double-stat and the parse ran on a timer 5 minutes later, so it could read a half-written `.dat` and produce a close from it. The target lands atomically and makes the parse a dependency edge, so it cannot. | Accepted at STOP C. **Not testable** — it needs a producer raced mid-write, which pinned fixtures cannot do. If any downstream number ever depended on a partial read, it will now differ. |
| **P2-OPS-01** | No source file is deleted, no `/tmp` lock files are written, and a failed stage fails the run instead of being swallowed by `|| true`. | Accepted at STOP C. |
| **D4-01** | sendmail is dropped; the job's `on_failure` notification replaces it. | Confirm at STOP E (§1). |

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

1. Answer D3-01 and D4-01 (§1). Set `failure_webhooks` to a real notification destination.
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
