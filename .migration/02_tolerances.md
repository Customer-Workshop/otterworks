# 02_tolerances — version 1.0.0 (PROPOSED at intake, resolved at STOP A)

Intake said "tolerances exact"; every row below is exact match after the Oracle profile's canonicalization. The `.json` beside this file is what `recon run --tolerances` loads.

| Oracle type | Target BSON | Canonicalization before compare | Tolerance |
|---|---|---|---|
| `NUMBER(p,0)`, p <= 18 | `long`/`int` | none | exact |
| `NUMBER(p,s)`, s > 0 or p > 18, `NUMBER` (no p/s) | `decimal128` | compare as decimal, no float | exact (numeric_abs_tol 0) |
| `BINARY_FLOAT` / `BINARY_DOUBLE` | `double` | IEEE compare | exact |
| `VARCHAR2` / `NVARCHAR2` / `CLOB` | `string` | none (no trim, no case fold) | exact |
| `CHAR(n)` | `string` | strip trailing spaces (profile rule) | exact after strip |
| Empty string `''` (Oracle stores NULL) | `null` or missing field | `null_missing_equiv` | exact |
| `DATE` | `date` | treat as UTC, ms precision | exact |
| `TIMESTAMP` / `TIMESTAMP WITH [LOCAL] TIME ZONE` | `date` | normalize to UTC, truncate to ms | exact |
| `RAW` / `BLOB` | `binData` | byte compare | exact |
| `NUMBER(1)` flags `0/1`, `CHAR(1)` `'Y'/'N'` | `bool` | map per mapping-spec rule | exact |
| Row counts per collection | n/a | n/a | exact |
| Aggregates (SUM/COUNT/MIN/MAX per unit) | n/a | decimal compare | exact (aggregate_rel_tol 0) |

## Other parameters
| Parameter | Value | Source |
|---|---|---|
| Connectivity policy | `online` — probe source and target; any failure blocks; no fallback | FACT (intake) |
| `source_access` / `target_access` | resolved by the probe at STOP A; see `08_connectivity.json` | DISCOVERED |
| Row-diff threshold (`full_diff_row_threshold`) | 100000 (above: keyed sampling `sample_size` 1000 + full aggregates) | FACT |
| Source query cap (`source_concurrency`) | 1 | FACT |
| Child re-run cap | 3 full recon re-runs, then escalate (rule 7) | plugin rule |
| NULL vs missing | `null_missing_equiv` | PROPOSED default |

## Amendment rule
A tolerance changes only by explicit approval recorded as a new dated row in `05_decisions.md`; the old row stays, `version` bumps in both files, and the row names every merged unit that must be re-verified. Grading-only fixes (a canonicalization rule or harness bug, no data or tolerance value change) are pre-approved: apply, log, mention at wave close.
