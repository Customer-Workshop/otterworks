# CUSTBILL (P-B, J6–J9) — production cutover plan

Status: **PLAN ONLY — nothing here has been executed.** STOP E is held
(`.migration/05_progress.md`). Every step marked **[customer]** is executed by the customer
under the customer-held cutover principal; Devin never holds or requests that principal and
never performs a repoint, unpause, or crontab edit. Steps marked **[parent]** are evidence
or documentation steps the migration parent performs on request.

Scope: the four P-B crontab lines in `etl/legacy-extra/crontab` (`*/15` sftp_ingest_poll.ksh,
`5-59/15` parse_custbill_fixedwidth.sh, `10 2 * * *` finance_excel_report.pl, `0 6 * * 0`
run_all.sh) → Databricks job `ow_tp_custbill` (ingest → parse → finance, serverless,
`max_concurrent_runs=1`, 2 retries / 5-min backoff, failure e-mail to finance). `etl/crontab`
(P-A..P-E) is out of scope and untouched.

## 0. Preconditions (all must be closed before step 2)

| # | Item | Owner | Where answered | Default if unanswered |
|---|---|---|---|---|
| R1 | Production feed encoding / record terminator (D3-3) | mainframe owner | register `04_dependency_register.md` | fixed-width ASCII, `\n`; a differing feed quarantines whole files (U6-c) — **do not** cut over on the default |
| R2 | Finance recipient list; `.xlsx` replaces `.xls`? (D4-1) | finance | Terraform var `finance_recipients` | `finance-reports@otterworks.dev`, xlsx + byte-identical CSV |
| R3 | Shared-drive pickup exists? where? (D4-4) | finance / ops | this plan §4 | none — reports read from `/Volumes/ow_tp/bronze/landing/reports/<ns>/` |
| R4 | Production landing mechanism into `/Volumes/ow_tp/bronze/landing/<ns>/incoming/` (D7-1, D10-6) | mainframe / infra | this plan §2 | none — **blocking**; the run pushed files itself |
| D8-4 | PII regime for `cust_name`/`cust_id` on `ow_tp.silver.custbill_records` (masking / row filters) | customer data governance | UC grants, applied by customer | none — **blocking** before any non-migration principal is granted `SELECT` |
| D8-2 / R-7 | Production run identity: a service principal owning the job and the `ow_tp` scope (no shared PAT) | customer platform team | Databricks account console | none — **blocking** |
| — | STOP E authorization in `#ow-migrations` naming the cutover window | customer | Slack thread → `05_progress.md` STOP E row | — |
| P-1 | Parent "production readiness" PR (plan-only until STOP E): (a) job parameter `ns` default `demo` → `prod` in `infrastructure/terraform-databricks/main.tf` and `databricks/custbill_workflow/job.json`; (b) `lifecycle { ignore_changes = [string_value] }` on the three `databricks_secret` resources; (c) `recon_custbill.py` accepts `--run-mode live --ns prod` and an `--expect-pause-status UNPAUSED` flag for U9-a during the parallel window (today it hard-gates live to `ns=demo` and expects `PAUSED`). Tolerances untouched. | parent | run branch PR, reviewed + merged before §3 | none — **blocking**; without (a) an unpaused schedule keeps writing `demo` and never reads `prod/incoming/` |

## 1. Freeze and baseline **[parent, on request]**

1. Merge the last open close PR into the run branch; tag the run branch commit
   (`tp-run/databricks-20260901T205308Z`) as the cutover candidate. No `main` merge.
2. Re-run `make tp-preflight PLATFORM=databricks` and `verify_job.py` against Jobs API `get`
   (retries required); attach both outputs to the STOP E thread.
3. Snapshot legacy outputs for the parallel-run window: `archive/`, `parsed/*.psv`,
   `reports/finance_billing_*.csv` from the production ETL box for the same dates the job will
   process. These are the recon baselines; the harness reads them via `--legacy-root`.

## 2. Production landing (R4) **[customer]**

Pick one; the job reads the volume regardless of who writes it.

- **A. Mainframe SFTP → customer file gateway → UC volume**: gateway writes to
  `/Volumes/ow_tp/bronze/landing/prod/incoming/`; ingest verifies-then-deletes exactly as today.
- **B. S3 external location**: mainframe SFTP lands in an S3 prefix registered as a UC external
  location; `landing` volume re-declared as an external volume over it (Terraform change, parent
  PR, plan-only until approved). No AWS Transfer Family is provisioned by the migration
  (hourly-billed endpoint; see `CUSTBILL_plan.md` D7-1).

**Dual delivery for the parallel window (§4).** Both chains must see the same bytes, so for the
whole window the feed is delivered to *both* the legacy SFTP drop and `prod/incoming/`. Preferred:
the mainframe transmission job gets a second target (same file, same name, same day). Fallback:
a customer-owned copy job on the ETL box watches the legacy `incoming/` directory and pushes each
file to the volume *before* the legacy `*/15` poll deletes it — i.e. it runs at `2-59/15` off the
same crontab, copies with a temp name, renames on completion, and compares sha256 against the
source; a mismatch or missing copy is logged and the file is re-pushed on the next tick. Daily
completeness check **[parent]**: `bronze.custbill_raw` distinct `source_file` for `ns=prod` equals
the legacy `archive/` listing for that day (this is U6-a/U6-b in the recon). Any gap halts the
window clock — that day does not count toward the exit criteria.

Whichever is chosen, the production namespace is `ns=prod` (matches `^[a-z0-9-]{1,32}$`).
`prod` is registered as a write target in `05_progress.md` before the first file lands.

## 3. Production credentials **[customer]**

1. Create the service principal from D8-2; grant it `CAN MANAGE RUN` on job `ow_tp_custbill`,
   `READ VOLUME`/`WRITE VOLUME` on `ow_tp.bronze.landing`, `MODIFY` on the four `ow_tp` tables,
   and `READ` on secret scope `ow_tp`.
2. Only after P-1(b) (`ignore_changes` on the three `databricks_secret` resources) is merged **and
   applied**, put the production SFTP credential into scope `ow_tp` keys
   `sftp_host`/`sftp_user`/`sftp_password` **from the customer principal**, replacing the fixture
   values. Order matters: with the guard in place first, no later `terraform apply` can put the
   fixture values back. Confirm with `terraform plan` = no changes on the secrets before §4.
3. Transfer job ownership (`run_as`) to the service principal; the shared PAT used during the
   migration run is rotated/revoked afterwards.

## 4. Parallel run (minimum one weekly cycle, recommended two) **[customer runs, parent recons]**

1. **[customer]** Confirm via Jobs API `get` that job parameter `ns` defaults to `prod` (P-1(a))
   and `verify_job.py --expect-ns prod` passes; then unpause (`pause_status: UNPAUSED` on the
   `0 */15 * * * ?` schedule; or enable file-arrival on `prod/incoming/` if the workspace supports
   it — then delete the cron schedule so there is one trigger; both trigger kinds inherit the job
   parameter default). Legacy crontab lines **stay on** and dual delivery (§2) is live. Both chains
   now process the same feed: legacy on the ETL box, Databricks on `ns=prod`. Manual `Run now`
   with `ns=demo` remains possible for the migration team and never touches `prod` rows.
2. After each daily 02:10 legacy finance run and again after the Sunday 06:00 `run_all.sh`:
   **[parent]** `recon_custbill.py --unit custbill_workflow --ns prod --legacy-root <snapshot of that day> --run-mode live --expect-pause-status UNPAUSED --evidence-json <partial/overlap evidence>`
   (P-1(c)); `--previous` for idempotency on the next no-input run. U9-c evidence is collected
   once at the start of the window from a customer-approved dry failure (malformed file into
   `prod/incoming/`, removed afterwards) plus the natural overlap between the 15-min schedule
   and a manual `Run now`. Tolerances T1–T12 unchanged
   (`03_recon_tolerances.md`); quarantined rows are reported as a named delta (R-2), never
   tolerated silently. Reports committed under `docs/tech-partnerships/recon/parallel/<date>/`.
3. Exit criteria: every daily report GREEN; the Sunday full-chain report GREEN; at least one
   real upstream failure or retry observed and handled (finance skipped, gold unchanged) or a
   deliberate dry failure agreed with finance; finance confirms the `.xlsx`/CSV from the volume
   match the legacy `.xls` they receive today.
4. Circuit breaker: three same-class recon failures → re-pause the job **[customer]**, halt, escalate
   in `#ow-migrations`. Legacy remains system of record throughout, so no data rollback is needed.

## 5. Cutover **[customer]**

Executed in the approved window, in this order, each step confirmed in the STOP E thread:

1. Finance switches consumers to the volume export (or the R3 shared-drive copy job the customer
   owns) for the next report date.
2. Remove the four P-B lines from `/etc/cron.d` / `etl/legacy-extra/crontab` on the ETL box
   (`etl/crontab` untouched). Leave `run_all.sh` and the three job scripts on disk, read-only.
3. Stale lock files in `/var/lock/etl/` from the retired chain are removed by ops.
4. Point the mainframe feed at the production landing path only (step 2 mechanism); the legacy
   SFTP drop stops receiving.
5. **[parent]** Final recon on `ns=prod` for the first post-cutover report date against the last
   legacy output → committed as `recon/cutover/custbill_workflow.live.recon.json`.
6. Ledger: STOP E → APPROVED/EXECUTED with permalink; rows 6–9 → CUTOVER; D2-2 → DECIDED.

## 6. Rollback (any time during §4–§5, customer-executed)

- Re-pause `ow_tp_custbill`. Re-add the four crontab lines (identical text, kept in this repo).
- Repoint the mainframe feed back to the legacy SFTP drop.
- No table/volume cleanup required: legacy never depended on `ow_tp`; `ns=prod` rows can be
  wiped with `custbill.py --ns prod wipe` once the customer confirms.
- Recovery objective: one 15-minute cycle (the first missed legacy `*/15` poll picks up any
  file that arrived meanwhile, since ingest never deletes what it did not hash-verify).

## 7. Decommission (≥ 30 days after cutover, customer)

Archive `/opt/etl/legacy-extra/` and `/var/log/etl/{sftp_ingest,parse,finance,run_all}.log`;
retire the ETL box's SFTP account for the mainframe; delete the legacy SFTP container spec only
after the archive is verified. `tech-partnerships` branch stays immutable as the historical
record.

## Open questions for the customer (reply in the STOP E thread)

1. R4 landing mechanism — A (file gateway) or B (S3 external location)?
2. R1 — confirm production feed is fixed-width ASCII with `\n` terminators and no header/trailer
   variants beyond `HDR`/`TRL`.
3. R2/R3 — recipient list; keep CSV + xlsx; does a shared-drive pickup exist?
4. D8-4 — who owns the PII regime decision and by when?
5. Parallel-run length: one or two weekly cycles?
6. Cutover window (a weekday after the 02:10 legacy finance run, before the next 15-min poll).
