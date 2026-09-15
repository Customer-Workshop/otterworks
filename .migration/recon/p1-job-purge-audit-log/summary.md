# p1-job-purge-audit-log (U-26) — recon verdict: PASS, grade DEGRADED, **NOT DATA-PROVEN**

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`,
`official_verdict=false`). The Oracle side is read over JDBC with the repo-local adapter,
which is outside the harness's tested matrix. See `DEGRADED.md`; the harness's own summary
is `recon.summary.md`.

## The gap, stated plainly: there is no live run to compare against

`JOB_PURGE_AUDIT_LOG` is **DISABLED** in Oracle and has never run there. The converted
Lakeflow job `ow_tp_p1_purge_audit_log` is created **PAUSED**, as every schedule in this
migration is. So nothing compares a legacy run against a converted run, and nothing in
this evidence should be read as if something did. What the recon compared is the table the
job acts on, which holds zero rows on both sides — schema parity and an empty-set
assertion, nothing about data.

What *can* be shown is that the converted job text behaves the way the legacy job text
specifies. `behaviour_check.json` records that, run against the deployed SQL on the
migration warehouse:

| Check | Result |
|---|---|
| an insert that omits `log_id` gets one allocated (sequence + trigger equivalent) | ids 5, 6 |
| `retention_days = 90` deletes a 120-day-old row, keeps a 10-day-old row | PASS |
| a second run with the same parameter deletes nothing more | PASS |
| a parameter that makes the statement fail raises nothing (`WHEN OTHERS THEN NULL`) | PASS |
| the same predicate **without** the handler does raise (control) | `ServerOperationError` |
| `retention_days = 1` deletes the row the 90-day run kept | PASS |
| the probe rows are removed; the table is empty again | PASS |

The last control matters: without it, "nothing was raised" could just mean the failing
parameter quietly did nothing. It fails without the handler, so the handler is what
swallows it.

## What ran

- Fixture first (`--mode fixture --depth sampled`, PASS, never merge evidence), then
  exactly one live merge-evidence run (`--mode live --depth sampled --seed 0`).
- Tiers 1–3 PASS. Tiers 5–7 are **unverified** on the JDBC route: structural to the route.
- Recon values are recomputed from Databricks and Oracle directly.

## Conversion notes

- The 90 days are still 90 days, but they are no longer buried in the job text: the job
  carries a `retention_days` parameter, default `90`, passed to the SQL task. The legacy
  comment called the constant "hardcoded"; it is now visible and changeable.
- `WHEN OTHERS THEN NULL` is reproduced, not fixed (plan decision P1-D2): the converted
  block wraps the DELETE in an EXIT handler for every SQLSTATE that does nothing. A failed
  purge stays silent and the next run tries again, exactly as today.
- The schedule is the same 03:30 daily (`FREQ=DAILY;BYHOUR=3;BYMINUTE=30` →
  `0 30 3 * * ?`, UTC) and lands PAUSED.
- `SYSDATE - 90` becomes the warehouse's UTC session clock minus the parameter, compared
  against the zoneless `logged_at` (plan decision P1-D3: UTC assumed and declared).
- No retries and no notifications were added. The legacy job told nobody when it failed;
  an alert here would be a behaviour change, not a conversion.
- The purge deletes by age, never by run, so a rerun cannot remove rows a later writer
  added inside the retention window.

## Evidence

| File | What it is |
|---|---|
| `result.json` | the harness result, with the degraded block |
| `p1-job-purge-audit-log.recon.json` | machine-readable report (`kind: recon-report`) |
| `behaviour_check.json` | the retention / swallowed-error / identity proof |
| `recon.summary.md`, `report.md` | the harness's own summary and report |
| `DEGRADED.md` | why this is not an official verdict |
