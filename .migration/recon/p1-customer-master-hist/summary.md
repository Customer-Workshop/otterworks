# p1-customer-master-hist — recon verdict: PASS, grade DEGRADED, **NOT DATA-PROVEN**

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`, `official_verdict=false`).
The Oracle side is read over JDBC with the repo-local adapter, which is outside the harness's
tested matrix. See `DEGRADED.md`; the harness's own summary is `recon.summary.md`.

## NOT DATA-PROVEN

`OW_BILLING.CUSTOMER_MASTER_HIST` holds **zero rows** today, in the fixture and in the live
source. So this PASS proves two things only:

1. Schema parity across all 158 columns through the mapping.
2. An empty-set assertion: source count 0 equals target count 0.

It proves **nothing about row content, money precision, date parsing or anomaly handling**,
because there were no rows to compare. Nobody may cite this run as data evidence. The unit
needs a fresh recon once the trigger path starts writing history rows.

## What ran

- Fixture first (`--mode fixture`, PASS, never merge evidence), then exactly one live
  merge-evidence run (`--mode live --depth full --seed 0`). One live Oracle read for the
  extract, one for recon; never concurrent.
- Tiers 1-3 PASS. Tiers 5-7 (constraint, index, identity parity) are **unverified** on the
  JDBC route — structural to this route, not a property of this unit. The result therefore
  carries that unverified warning and `merge_eligible=false`, which is how the harness
  treats any run with an unverified warning.
- Idempotency: the silver load was rerun and `target_state.digest.json` (row count plus an
  order-independent content hash) was identical across runs, modulo run id and timestamp.
- Recon values are recomputed from Databricks and Oracle directly, never from this unit's
  own load output.

## The 15 parsed date companions

The `DD-MON-YY` strings are carried byte-exact and each gets the parsed companion its
consumers read. Recon could not exercise them here (no rows), so the parser was checked
separately against the shapes wave 0 measured on the live source
(`databricks/migration/lakebase/w0a_date_parity.py`): unpadded days, four-digit years,
lower case, alternate separators and surrounding spaces all parse; an impossible day, an
unknown month or an ISO string give NULL, which is what `f_str2dt` returns and what the
declared anomaly set expects. All 18 vectors match on the warehouse.

## Trigger and sequence conversion

Oracle keeps this table filled by `trg_customer_master_hist` (`AFTER UPDATE OR DELETE ... FOR
EACH ROW`): it copies the whole `:OLD` row, stamps `hist_op` `UPD`/`DEL`, writes `hist_dt` as
the `DD-MON-YY HH24:MI:SS` **string** `TO_CHAR(SYSDATE, ...)` produces, and takes `hist_id`
from `seq_customer_master_hist`. Parent inserts write no history row.

Delta has no row triggers, so the behaviour moves into
`databricks/migration/transport/silver_hist_trigger.py`, which generates the equivalent
append from the parent's old image: same two operation codes, same full-row copy, `hist_dt`
kept as the same formatted string (not a timestamp, converted to UTC explicitly so it does
not follow the writer's session timezone), and `hist_id` allocated as
`max(hist_id) + row_number()` in place of the sequence. Gap-free numbering is not preserved —
an Oracle sequence is not either (it caches and loses numbers on restart); what is preserved
is that ids are increasing and unique within the history table.
