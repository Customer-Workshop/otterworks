# p1-pkg-dunning (U-24): the audit rows the converted routines write

Oracle's `pkg_dunning` calls `pkg_ow_util.log_msg` twice: once at the end of
`sp_schedule_dunning` (05_pkg_dunning.sql:66) and once per suspended tenant in
`sp_suspend_overdue` (:96). The converted routines call wave-0's `billing.log_msg` at the
same two points, so the run writes the same two kinds of row into
`billing.billing_audit_log`. That table is a declared runtime write for w3-d
(`.migration/waves/wave-3.json`, ledger D-009): DML only, its DDL is wave 0's and untouched.

## Installed on `mig-p1-w2`

`databricks/migration/lakebase/w3d_pkg_dunning.sql` was re-applied on the wave branch
(CREATE OR REPLACE throughout, so re-applying is a no-op). `pg_get_functiondef` shows one
`billing.log_msg` call in `sp_schedule_dunning` and one in `sp_suspend_overdue`;
`fn_overdue_accounts` has none, as in Oracle.

## The rows themselves

`databricks/migration/lakebase/w3d_audit_probe.py` calls both procedures on the wave branch,
reads the audit rows the call produced, and then rolls the transaction back:

```
as_of=2026-09-15  audit rows before=0  written by this run=2
  DUNNING | scheduled 2 attempts as of 15-SEP-26
  DUNNING | suspended tenant=00000000-0000-0000-0000-000000000005
dunning_attempts in-transaction: 3
notifications in-transaction: 2
rolled back: no row on the wave branch changed
```

The date reads `15-SEP-26` because the line goes through `billing.f_dt2str`, the wave-0
`DD-MON-YY` helper, not through `to_char`, which would take month names from `lc_time`
rather than Oracle's NLS. The op `dunning_log_line_text` diffs that whole line against
Oracle over 21 as-of dates.

The rollback is deliberate, and it is why `billing.billing_audit_log` still holds zero rows
on the branch: `billing.invoices` on `mig-p1-w2` is unit p1-invoices' data (batch w3-b, still
in flight), and `billing.dunning_attempts` and `billing.notifications` hold this unit's
reconciled rows. Committing a sweep would write rows no source run produced and break the
parity this unit just proved. So the routines are installed and shown to log, but they have
still not been run end to end against a settled invoice state; the end-to-end op diff is the
wave gate's, after w3-b merges.

One divergence carried from wave 0 (P1-D1a, not this unit's to close): Oracle's `log_msg`
runs in an autonomous transaction and keeps its row when the caller rolls back. Postgres has
no autonomous transaction and this Lakebase project blocks `dblink`, so the converted
`log_msg` rolls back with its caller. Its own failures are swallowed, as Oracle swallows
them.
