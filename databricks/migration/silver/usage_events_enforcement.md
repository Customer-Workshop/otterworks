# U-18 USAGE_EVENTS: where `TRG_USAGE_EVENTS_CHECK` now lives

The Oracle trigger (`services/legacy-billing/db/oracle/schema/01_tables.sql`) fires
`BEFORE INSERT ... FOR EACH ROW` on `OW_BILLING.USAGE_EVENTS` and raises on two conditions:

| Oracle rule | Error | Where it lives on Delta |
|---|---|---|
| `NVL(:NEW.units, 0) <= 0` | `ORA-20001 units must be > 0` | Delta CHECK constraint `usage_events_units_positive` (`units > 0`) on `ow_tp.silver.usage_events`, plus `units` declared `NOT NULL`. Every writer of the table is held to it, not only the migration loader. |
| `kind_cd` absent from `CODES` where `code_type = 'USAGE_KIND'` | `ORA-20002 unknown usage kind <n>` | Load-time expectation in `usage_events_load.py` (`check_trigger_rule`), evaluated against the `USAGE_KIND` code set read from the source in the same read-only transaction as the rows. |

Why the second rule is an expectation and not a CHECK constraint: a Delta CHECK cannot look
a value up in another table, and writing today's code values into a literal `IN (...)` list
would enforce a different, frozen rule — the trigger validates against whatever `CODES`
holds at insert time. `CODES` is not a declared write target of this unit, so there is no
Delta copy of it in `ow_tp.silver` to constrain against either.

Behaviour on a violation: the load aborts and reports the offending ids and the matching
Oracle error. Rows are never dropped, cleaned or quarantined — the trigger rejects the
write, and reproducing that rejection is the parity behaviour (D8-01).

Not covered: the trigger's `BEFORE INSERT` timing is not reproducible on a bulk MERGE, so
the rules are checked over the snapshot before the write rather than per row during it. The
outcome is the same for a load that passes; for a load that fails, Oracle would have
rejected one row and this loader rejects the whole batch.
