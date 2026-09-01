# U3 dim_period

## Purpose

This unit migrates period derivation from `COMMISSION_PAY.COMMISSION_LEDGER` to
the Databricks silver layer. The source is DISTINCT `period_month`, optionally
filtered by `p_period_month`. The target is `ow_tp.silver.dim_period_cdw`.

## Target and mapping

| Oracle column | Databricks column | Mapping |
|---|---|---|
| `period_key` NUMBER identity | `period_key` BIGINT | Explicit baseline values; DEC-003 |
| `period_month` VARCHAR2 | `period_month` STRING | Byte-exact `YYYY-MM` |
| `year_num` NUMBER(4,0) | `year_num` INT | First four characters |
| `month_num` NUMBER(2,0) | `month_num` INT | Final two characters |
| `quarter_num` NUMBER(1,0) | `quarter_num` INT | `CEIL(month_num / 3)` |
| load timestamp | `loaded_at` TIMESTAMP | `current_timestamp()` |

The load uses an insert-only MERGE; existing periods are never updated. New
keys use the current maximum `period_key` plus `row_number()` ordered by
`period_month`, after existing periods are excluded.

## Encoding

Inputs are UTF-8 and strings are byte-exact. No trim or case folding is done.
Baseline ingestion uses `read_files` with an explicit schema and `FAILFAST`.

## Malformed records

The baseline reader fails fast on malformed CSV. Spark derivation casts can
produce NULL; NULL derivations and values outside `YYYY-MM` make `assert_true`
fail before the MERGE. Nothing is loaded for that run, preserving the Oracle
raise-and-rollback semantic. The Oracle raise path is exercised only by this
guard; no malformed row is present in the feed snapshot.

## Empty input

Zero ledger rows fail the declared-volume guard when the manifest says more
than zero. If the manifest declares zero, the MERGE inserts nothing and the
table remains the baseline.

## Batch granularity

Each run processes a full snapshot: DROP and recreate from baseline, then
insert-only MERGE. Reruns are idempotent.

## Recon

Recon uses tolerances v1 in DEGRADED snapshot mode. `period_key` is the key,
`period_month` is the natural key, and `loaded_at` is excluded.

## Coverage gaps / unverified paths

`live-legacy-comparison` is DEGRADED mode; owner parent; it closes at the
wave-1 independent recon. Concurrent writers and malformed rows absent from
the snapshot remain unverified paths.
