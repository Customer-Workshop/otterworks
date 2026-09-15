# p1-pkg-dunning (U-24) — recon verdict: PASS, grade DEGRADED, **ROUTINES NOT EXECUTED**

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`,
`official_verdict=false`). The Oracle side is read over JDBC with the repo-local adapter,
which is outside the harness's tested matrix. See `DEGRADED.md`; the harness's own summary
is `recon.summary.md`.

## What this PASS covers, and what it does not

The harness run compares the two tables the package writes, `billing.dunning_attempts` and
`billing.notifications`, against Oracle. It does **not** run the converted routines. A sweep
writes `dunning_attempts`, `notifications`, `tenants`, `subscriptions` and the audit log on
the shared wave branch, which are the same rows recon compares against Oracle, so executing
it here would destroy the baseline every batch in this wave is measured on. The routines
install and resolve their table references at execution time; the wave gate runs the
end-to-end op diff. Nobody may cite this run as behavioural evidence for the sweep itself.

What was verified of the conversion, in the fixture run's tier-4 ops
(`databricks/migration/recon/ops/p1_pkg_dunning_ops.json`, evidence under `fixture/`):

1. `dunning_weekend_shift_calendar` — 21 consecutive days, Oracle
   `DECODE(TO_CHAR(d,'DY','NLS_DATE_LANGUAGE=ENGLISH'), 'SAT',2,'SUN',1,0)` against the
   Postgres `EXTRACT(ISODOW)` form, same shifted date on every day.
2. `dunning_attempt_id_formula` — every stored `dunning_attempts.id` equals
   `f_md5_uuid(invoice_id || attempt_no)` on both sides, so the converted id generation
   reproduces the ids Oracle actually wrote.
3. `suspension_notification_id_formula` — same for kind-3 notification ids, against
   `f_md5_uuid(tenant_id || 'suspension' || YYYY-MM-DD)`.
4. `dunning_log_line_text` — the audit line `sp_schedule_dunning` writes, over 21 days:
   Oracle's `'scheduled ' || TO_CHAR(cnt) || ' attempts as of ' || TO_CHAR(d,'DD-MON-YY',
   'NLS_DATE_LANGUAGE=ENGLISH')` against the converted form built on `billing.f_dt2str`,
   character for character.

## What ran

- Fixture first with the ops file (`--mode fixture --depth full`, PASS, `fixture/`), then
  exactly one merge-evidence run (`--mode transactional --depth full --seed 0`) with the
  brief's command, unmodified.
- Idempotency of the target state: two loads, two digests (`load_digest_run1.json`,
  `load_digest_run2.json`), identical. Behavioural idempotency of `sp_suspend_overdue` (a
  second sweep on the same day writes nothing, by the `NOT EXISTS` dedupe) is **not**
  proven here — it needs a sweep, and a sweep is the shared-branch write above.
- The audit-write path was exercised through the routines themselves on the wave branch,
  inside a transaction that was rolled back: one `CALL billing.sp_schedule_dunning` and one
  `CALL billing.sp_suspend_overdue` wrote the two `billing.billing_audit_log` rows Oracle
  writes at the same two points, and the rollback left the branch unchanged. The rows and
  the reason for the rollback are in `audit_log_writes.md`.
- Source-side constraint, index and identity parity (tiers 5–7) is **unverified** on the
  JDBC route.

## Conversion notes

- `(+)` outer join → ANSI `LEFT JOIN`; `DECODE` → `CASE`; `SYS_REFCURSOR` →
  `RETURNS TABLE`. Both `fn_overdue_accounts` and `sp_schedule_dunning` keep
  `ORDER BY issued_at, id`.
- Weekend shift uses `EXTRACT(ISODOW)`, not `to_char(d,'DY')`: Postgres `to_char` follows
  `lc_time`, so the Oracle English-NLS `DECODE` would silently stop matching under another
  locale. `EXTRACT` carries no locale at all.
- `WHEN OTHERS THEN NULL` around each scheduling insert is reproduced as a per-row
  `BEGIN … EXCEPTION WHEN OTHERS THEN NULL` block (P1-D2): a run can silently schedule
  fewer attempts than expected, and the recon baseline is the rows it actually wrote.
- Package globals `g_last_run_dt` and `g_scheduled_cnt` become `INOUT` parameters on
  `sp_schedule_dunning` (P1-D4) — not a session global, and not a state table, because a
  state table would be a write target this batch has not declared.
- **Logging is kept.** Oracle's `pkg_ow_util.log_msg` calls convert to `billing.log_msg`
  (wave-0, U-01), at the same two points: the scheduling total after the loop, and one line
  per suspended tenant. `billing.billing_audit_log` is a declared runtime write for this
  batch (wave-3 manifest, ledger D-009); this batch issues DML only and never touches its
  DDL. `log_msg` swallows its own failures as Oracle's autonomous transaction does; what it
  cannot reproduce on Postgres is committing the log row independently of a caller that
  rolls back — that is wave-0's declared divergence P1-D1a, not new here.
- Runtime DML on tables another unit owns the DDL for: `billing.tenants`,
  `billing.subscriptions` and `billing.billing_audit_log` (declared runtime writes; no DDL
  is issued against any of them).

## Evidence

| File | What it is |
|---|---|
| `result.json` | the harness result, with the degraded block |
| `p1-pkg-dunning.recon.json` | machine-readable report (`kind: recon-report`) |
| `recon.summary.md`, `report.md` | the harness's own summary and report |
| `DEGRADED.md` | why this is not an official verdict |
| `load_digest_run1.json`, `load_digest_run2.json` | the rerun that proves target-state idempotency |
| `fixture/` | the fixture run, including the four tier-4 ops; development evidence only |
| `audit_log_writes.md` | the `billing_audit_log` rows the installed routines write, read back from a rolled-back call |
