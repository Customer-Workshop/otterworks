# 03 — Reconciliation tolerance record

**Version 1 — 2026-09-01 — status: APPROVED at STOP A (2026-09-01).** Every recon report cites `tolerances v1` and the recon mode in its header. A report without both is invalid.

**Recon mode: DEGRADED** (snapshot). Lakehouse Federation to the source is not reachable (D10-1). Every comparison names its snapshot manifest (source object, extraction time, row count, sha256, `FIXTURE_SOURCE`); every verdict is a statement about the snapshot, not production. An in-perimeter recon run by the customer with the delivered harness is an entry criterion for STOP E.

## Tolerances by data type (SQL + PIPELINE surfaces)
| Data type / check | Rule | Population | Status |
|---|---|---|---|
| Row count | exact (0 tolerance) per object | every in-scope object, per period and total | PROPOSED |
| Money (`commission_amt`, `premium_amt`, any `*_amt`) | exact, compared in **cents as integers** (`CAST(ROUND(x*100) AS BIGINT)`); `NUMBER(p,s)` → `DECIMAL(p,s)` with source precision | every `FACT_COMMISSION` row; every MV row; SUM per agent×period | PROPOSED |
| Rates / percentages (`commission_rate`, `*_pct`) | exact at source scale (`DECIMAL(p,s)`), no rounding on either side | every row | PROPOSED |
| Integers / keys | exact; surrogate keys preserved value-for-value | every row | PROPOSED |
| `DATE` | day precision, no tz; compared as `YYYY-MM-DD` strings | every row | PROPOSED |
| Server-side timestamps (`loaded_at`) | **excluded** from baseline, row diff, idempotency (normalized to NULL in snapshots) | — | PROPOSED |
| Strings (`agent_code`, `full_name`, `line_of_business`, `status`) | exact, byte-for-byte after UTF-8 normalization; **no** case folding, **no** trim (trailing-space differences are defects) | every row | PROPOSED |
| NULLs | NULL = NULL for comparison; NULL count per column must match exactly | every column | PROPOSED |
| Aggregates (SUM/COUNT/MIN/MAX per column) | exact; AVG **not** used as a gate (engine rounding differs) | every numeric column per object | PROPOSED |
| Rounding rule | Oracle `ROUND` = half away from zero; Spark `round()` on DECIMAL = HALF_UP; treated as equivalent only after the negative-amount test case in the dictionary passes | negative `commission_amt` rows (clawbacks), if present | PROPOSED |
| Unordered results | MV compared after ordering by (`agent_code`, `period_month`, `line_of_business`); tables by primary key | — | PROPOSED |
| Duplicate keys | zero duplicates on the recon key both sides | every object | PROPOSED |
| Idempotency | rerun of the converted loader for the same period → identical row set (excluding `loaded_at`), proven by an actual rerun | every silver/gold object | PROPOSED |
| Quarantine rate | 0 rows quarantined on the baseline period set (the legacy loader rejects nothing; any quarantine = a defect to explain); halt threshold: any quarantine > 0 fails the unit | driver population = bronze `COMMISSION_PAY` inputs for the loaded periods | PROPOSED |
| Coverage gap declarations | anomalies no unit ingests must be declared in the unit contract before recon | — | PROPOSED |

## Recon economics
| Item | Value | Status |
|---|---|---|
| Row-level diff threshold | 1,000,000 rows (estate is far below → full row diff everywhere) | PROPOSED |
| Legacy query concurrency cap | 2 concurrent read sessions against the source | PROPOSED |
| Warehouse windows | fixture-first; one live window per wave (parent-run); battery batched to one multi-metric statement per object | PROPOSED |

## Amendment procedure
A tolerance changes only by explicit user approval recorded in `06_decisions.md`. The change is appended here as **version N+1** with the old row preserved and struck through, plus a stated re-verification scope for every already-merged wave that ran under the old version. Children see only the current version and its date.
