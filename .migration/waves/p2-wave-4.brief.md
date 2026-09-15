# Pipeline 2, wave 4 close — PASS: `p2-orchestration`, cron and `run_all.sh` replaced by two PAUSED Lakeflow Jobs

Landed: 1 of 1 batch, 1 of 1 unit (`p2-orchestration`). Failed: none. Blocked: none. Circuit breaker: 0 of 3.

What the unit replaces: `etl/legacy-extra/run_all.sh` and the CUSTBILL entries in both crontabs. Two jobs, both PAUSED, no new clusters:

- `ow_tp_p2_custbill_ingest`, quartz `0 0/15 * * * ?` — `land_files` → `custbill_pipeline`;
- `ow_tp_p2_finance_close`, quartz `0 10 2 * * ?` — `await_silver` → `export_csv_xls`.

Five legacy behaviours are gone, and each one is a check in the recon report. The two `sleep 600` calls are `depends_on` edges: in the live run, `custbill_pipeline` started 0.5 seconds after `land_files` finished, and only because it finished. The parse loses its own `5-59/15` cron entry entirely — that is what removes the five-minute guess between ingest and parse. `|| true` on every stage is gone: a failed task fails the run after 2 retries with a 5-minute backoff. The three `/tmp` lock files that were created, never removed and never actually checked become `max_concurrent_runs: 1`, so the `*/15` ingest can no longer overlap its own previous run; the close job also queues, so a late ingest delays it instead of cancelling it. And the dead sendmail pipe becomes the job's `on_failure` notification — configured, with the destination deliberately **empty** in the migration target, because a migration session does not wire a live pager.

Recon: **PASS**, depth structural. This unit moves no data of its own, so there is no row parity to compute and the report does not claim one; every row these jobs cause to exist is reconciled row-for-row in waves 1–3. The evidence is the deployed job shape read back from the workspace with the SDK — not from the bundle file that produced it — by `databricks/migration/p2/recon/verify_job_structure.py`: 20 checks, all pass (`.migration/recon/p2-orchestration/job_structure.json`), plus one real end-to-end run. Report: `.migration/recon/p2-orchestration/p2-orchestration.recon.json`.

Idempotency was proven by the run itself, not inferred: the six pinned files were already landed in wave 1, so the orchestrated run re-executed the whole chain and left every fingerprint unchanged — silver 116 rows md5 `115f7e40240d7529b6bc48ec0a922ccd`, quarantine 15, trailer audit 6. The close job was rerun too; both exports are still 321 bytes, md5 `de118d0223bb3a77fd83973a625fed8d`.

**Behaviour changes.** **P2-D01 stands and is named here, not buried in a recon JSON:** the legacy parse could read a half-written `.dat`, because it ran on a five-minute timer behind a one-second double-stat. The target lands atomically and makes parse a dependency edge, so it cannot. Accepted at STOP C; repeated in the STOP E packet. **P2-OPS-01:** no source file is deleted, no lock file is written, and stages fail loudly. **D4-01:** sendmail is dropped, the job's failure notification replaces it, and the user confirms at STOP E.

One deviation from the manifest, deliberate: it sketched the close as `await_silver → gold_close → export_csv_xls` plus `trailer_audit`, but gold and the trailer audit are tables in the same Lakeflow pipeline as silver, so one pipeline update materializes all three. Splitting them into separate job tasks would mean splitting the pipeline. The ordering the sleeps used to fake is unchanged: the export still cannot run before gold exists.

**What this verification does not cover** (also in the report): retries and the failure notification are configured, not exercised — nothing was made to fail on purpose, and the destination is empty by design; the quartz expressions are verified as configuration, since a PAUSED schedule never fires; job permissions and grants are not compared; P2-D04 (timezone, UTC proposed) is undecided and also sets the date stamp in the export filename; P2-D05 (the Sunday 06:00 `run_all.sh` re-run) has no replacement on purpose; and `source_principal_read_only` is still unverified because the doctor has no privilege query for a Databricks-family source.

Base: the working branch at `5ac35cb0` (waves 0–3, PRs #1599, #1603, #1606, #1607, #1608, merged; #1609 is the wave-3 review fix). Next: pipeline 2 parks at STOP E with the decision packet — P2-D04, P2-D05, D3-01 and D4-01.
