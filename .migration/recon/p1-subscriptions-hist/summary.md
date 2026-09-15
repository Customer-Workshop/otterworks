# p1-subscriptions-hist — recon verdict: PASS, grade DEGRADED, **NOT DATA-PROVEN**

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`, `official_verdict=false`).
The Oracle side is read over JDBC with the repo-local adapter, which is outside the harness's
tested matrix. See `DEGRADED.md`; the harness's own summary is `recon.summary.md`.

## NOT DATA-PROVEN

`OW_BILLING.SUBSCRIPTIONS_HIST` holds **zero rows** today, in the fixture and in the live
source. So this PASS proves two things only:

1. Schema parity across all 10 columns through the mapping.
2. An empty-set assertion: source count 0 equals target count 0.

It proves **nothing about row content, date parsing or status-code handling**, because there
were no rows to compare. Nobody may cite this run as data evidence. The unit needs a fresh
recon once the trigger path starts writing history rows.

## What ran

- Fixture first (`--mode fixture`, PASS, never merge evidence), then exactly one live
  merge-evidence run (`--mode live --depth full --seed 0`). One live Oracle read for the
  extract, one for recon; never concurrent.
- Tiers 1-3 PASS. Tiers 5-7 (constraint, index, identity parity) are **unverified** on the
  JDBC route — structural to this route, not a property of this unit.
- Idempotency: the silver load was rerun and `target_state.digest.json` (row count plus an
  order-independent content hash) was identical across runs, modulo run id and timestamp.
- Recon values are recomputed from Databricks and Oracle directly, never from this unit's
  own load output.

## Trigger and sequence conversion

Oracle keeps this table filled by `trg_subscriptions_hist` (`AFTER UPDATE OR DELETE ... FOR
EACH ROW`): it copies the whole `:OLD` row, stamps `hist_op` `UPD`/`DEL`, writes `hist_dt` as
the `DD-MON-YY HH24:MI:SS` **string** `TO_CHAR(SYSDATE, ...)` produces, and takes `hist_id`
from `seq_subscriptions_hist`. Parent inserts write no history row.

Delta has no row triggers, so the behaviour moves into
`databricks/migration/transport/silver_hist_trigger.py`, which generates the equivalent
append from the parent's old image: same two operation codes, same full-row copy, `hist_dt`
kept as the same formatted string (not a timestamp), and `hist_id` allocated as
`max(hist_id) + row_number()` in place of the sequence. Gap-free numbering is not preserved —
an Oracle sequence is not either (it caches and loses numbers on restart); what is preserved
is that ids are increasing and unique within the history table.

## One mapping note

`mapping_spec.json` declares `starts_on`, `ends_on` and `suspended_on` as target `TIMESTAMP`.
Their Oracle type is `DATE`, which is zoneless, so the loader writes `TIMESTAMP_NTZ` — the
wave-1 dialect rule. The mapping file is parent-owned and was not edited.
