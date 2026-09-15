# 03_recon_tolerances — the parity contract

**Version: v1 (2026-09-15).** Machine form: `03_recon_tolerances.json`. Every recon result
records the version it ran under; a run against a stale version is visible in its evidence.

**Recon mode: LIVE**, via Lakehouse Federation to Oracle read-only. If federation is refused
(D10-01), the mode drops to **DEGRADED** (snapshot extracts with per-unit manifests), every
report headers the mode, and an in-perimeter run becomes an entry criterion for STOP E.
Changing the mode is an amendment, not a runtime choice.

## Tolerances

| Row | Value | Population | Status |
|---|---|---|---|
| Row counts | exact, zero tolerance | every table, both tiers | FACT (user) |
| Money (`NUMBER(12,2)` → `DECIMAL(12,2)`) | exact, zero tolerance | every monetary column: invoice totals, line amounts, credit notes, rated amounts | FACT (user) |
| Non-money floats | 1e-9 relative | every other numeric column and every aggregate | FACT (user) |
| Dates | canonicalized to ISO-8601 before comparison | every date column, including `VARCHAR2(9)` `DD-MON-YY` strings | FACT (user) |
| Unparseable dates | compared as a declared anomaly set, membership exact | the rows whose date string fails canonicalization | FACT (user) |
| Known anomalies | compared as sets, membership exact | orphan invoice lines, malformed CSV lists | FACT (user) |
| Strings | exact after trim of trailing spaces; collation-insensitive comparison | every `VARCHAR2` column | PROPOSED |
| NULL vs empty string | Oracle's empty-string-is-NULL is preserved; a target empty string where Oracle holds NULL is a diff | every nullable string column | PROPOSED |
| Quarantine rate | > 1% of the driver population is a unit failure | driver population only, per pipeline | PROPOSED |
| Unordered results | ties broken by primary key before comparison | every query without a total order | PROPOSED |

## Economics

| Row | Value | Rationale |
|---|---|---|
| `full_diff_row_threshold` | 5,000,000 | the whole estate is far below this, so every table gets a keyed full diff, not a sample |
| `sample_size` | 100,000 | only reached if a table exceeds the threshold |
| `source_concurrency` | 4 | the source is a single t3.large running Oracle Free; more concurrent recon queries would distort the live system |
| Live windows | one per unit; the independent verifier gets its own with a different `--seed` | |

## Amendment procedure

A tolerance changes only by explicit approval from the engagement owner, recorded as a new
dated version of this file with the old row preserved, a new `03_recon_tolerances.json`
issued together with it, and a stated re-verification scope for every wave already merged
under the old value. No tolerance is relaxed to make a red unit green.
