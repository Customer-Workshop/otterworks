# p1-job-nightly-dunning (U-25) — recon verdict: PASS, grade DEGRADED, **NOT DATA-PROVEN AGAINST A LIVE RUN**

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`,
`official_verdict=false`). The Oracle side is read over JDBC with the repo-local adapter,
outside the harness's tested matrix. See `DEGRADED.md`; the harness's own summary is
`recon.summary.md`.

## The gap, stated plainly: there is no live run to compare against

`JOB_NIGHTLY_DUNNING` is **DISABLED** in Oracle, so no legacy run history exists and no
live run can be compared. The converted Lakeflow job `ow_tp_p1_nightly_dunning` is created
**PAUSED** (daily 02:00 UTC, `0 0 2 * * ?`); enabling it is the user's STOP E decision, not
Devin's. What stands in for a live comparison is run-history equivalence **on the fixture**:
the legacy PL/SQL block and the converted chain were each executed twice per `as_of` against
the same input state, and the rows each wrote were compared, run for run. That is fixture evidence, not a
merge verdict and not proof of production behaviour.

The data recon in `result.json` is the threshold/sampled comparison of
`billing.dunning_attempts` only. Its row contract belongs to w3-d; this unit did not write
or re-convert that table.

## Run-history equivalence (`runhistory_equivalence.json`)

Source block, run verbatim on the fixture:
`BEGIN pkg_dunning.sp_schedule_dunning(:d); pkg_dunning.sp_suspend_overdue(:d); END;`
Target: the job body, `billing.sp_schedule_dunning` then `billing.sp_suspend_overdue`, same
`as_of`, one transaction. Both sides snapshot `dunning_attempts`, `tenants`, `subscriptions`
and `notifications` before and after and **roll back**, so neither the fixture nor the
shared branch `mig-p1-w2` is mutated.

| `as_of` | weekday | run | legacy rows written | converted | equivalent |
|---|---|---|---|---|---|
| 2026-09-15 | Tue | 1 | 2 attempts (`attempt_no` 1 and 2) scheduled 2026-09-15; tenant …0005 → 20; subscription …0005 → 20, suspended 2026-09-15; 1 suspension notification | identical | yes |
| 2026-09-15 | Tue | 2 | 2 more attempts (`attempt_no` 2 and 3); nothing further from the sweep | identical | yes |
| 2026-09-12 | Sat | 1 | same as above, scheduled 2026-09-14 (weekend shift) | identical | yes |
| 2026-09-12 | Sat | 2 | same as above, scheduled 2026-09-14 | identical | yes |

No exception on either side in any run, `scheduled_cnt = 2` every time. The deterministic
MD5-derived attempt ids match byte-for-byte (`35737ff3-…`, `6118c817-…` on run 1;
`bdeccf71-…`, `70e0e4d2-…` on run 2) — the target reproduces the legacy id derivation, not
merely the row count.

The second run is the rerun proof. The chain is **not** idempotent, on either side: running
it again for the same date schedules the next attempt number. That is the legacy behaviour
and the target reproduces it; it was not cleaned up.

This is the **first** end-to-end execution of the converted chain. It ran clean; nothing was
smoothed.

### Excluded from the comparison, deliberately

`billing_audit_log` is not compared. `log_msg` is an autonomous transaction on Oracle
(its rows survive the rollback) and an ordinary call on the target (its rows do not). The
difference is the rollback harness, not the conversion, but it is unverified either way and
is listed here rather than quietly dropped.

## What ran

- Fixture recon first (`--mode fixture --depth sampled`, PASS, never merge evidence), then
  exactly one merge-evidence run (`--mode transactional --depth sampled --seed 0`) against
  live Oracle — the unit's single live read.
- Tiers 0–3, 5–6 PASS. Tier 7 schema parity is **UNVERIFIED**: the JDBC adapter reads no
  constraint metadata. Structural to the route, not to this unit.
- Two recon runs total, under the cap of three.

## Conversion notes

- The job is orchestration only. `pkg_dunning`, `invoices`, `invoice_lines`,
  `dunning_attempts` and `notifications` were read as installed on `mig-p1-w2` and not
  re-converted.
- `TRUNC(SYSDATE)` becomes the run's own UTC date at midnight, passed as the `as_of` job
  parameter (default `{{job.start_time.iso_date}}`), so a rerun is reproducible instead of
  depending on the worker clock (plan decision P1-D3: UTC assumed and declared).
- Package-global state (`g_last_run_dt`, `g_scheduled_cnt`) is explicit: the converted
  `sp_schedule_dunning` takes and returns it (plan decision P1-D4). The job passes the
  legacy initial values and records what came back.
- `WHEN OTHERS THEN NULL` around the attempt insert is reproduced, not fixed (P1-D2).
- The weekend shift (Sat +2, Sun +1) is preserved; the Saturday run above exercises it.
- No retries and no notifications were added: the legacy job told nobody when it failed.
- The schedule lands PAUSED.

## Dependencies unmerged at build time

Wave-3 units (`pkg_dunning`, invoices, dunning attempts, notifications) were **not merged
into the base branch** when this unit was built. They were read where they are installed,
Lakebase branch `mig-p1-w2`. `pkg_rating` (`sp_finalize_rating`, `fn_usage_rating`,
`fn_usage_summary`) was not delivered and does not exist in Lakebase. The converted
nightly-dunning chain does not call it — `sp_schedule_dunning` and `sp_suspend_overdue` read
invoices and write dunning/suspension rows only — so this unit is **not blocked** by it, and
nothing was stubbed. The consequence is scope: this job orchestrates the dunning chain, not
rating.

## Not verified

- Any live Oracle run of `JOB_NIGHTLY_DUNNING` (disabled at source; no run history exists).
- Any run of the converted job on its schedule (created PAUSED, never triggered).
- Source-side constraint/index/identity parity (tier 7, JDBC route).
- `billing_audit_log` write parity (see exclusion above).

## Evidence

| File | What it is |
|---|---|
| `result.json` | the harness result, with the degraded block |
| `runhistory_equivalence.json` | legacy block vs converted chain, per `as_of`, rolled back |
| `recon.summary.md`, `report.md` | the harness's own summary and report |
| `DEGRADED.md` | why this is not an official verdict |
