# Reconciliation tolerance record

**Version `tol-p1-v1` (2026-09-14).** Machine form: `03_recon_tolerances.json` (same version id).
Recon mode: **LIVE** (source pinned by SCN or `SET TRANSACTION READ ONLY`, target = Lakebase batch
branch or Delta staging). DEGRADED is not in effect; if D10-2 stays open, LIVE recon runs from the
Devin VM path, not from Databricks serverless, which changes nothing in this record.

## Tolerances (per data type, per surface)

| # | Surface | Data type / check | Tolerance | Population | Mark |
|---|---|---|---|---|---|
| 1 | both | Row count | 0 unexplained differences | every mapped table, full population | PROPOSED |
| 2 | both | Primary keys | exact set equality (missing/extra = FAIL) | every mapped table | FACT |
| 3 | both | Money (`*_AMT`, `AMOUNT`, `BALANCE*`, `PRICE*`, `TAX*`) as `NUMBER(18,2)` -> `DECIMAL(18,2)`/`NUMERIC(18,2)` | exact, 0.00 | every row | FACT |
| 4 | both | Floats (`BINARY_DOUBLE`, `NUMBER` without scale used as rate) | abs 1e-6 | every row | FACT |
| 5 | both | Timestamps / dates | equal to the second (Oracle `DATE` has no sub-second) | every row | FACT |
| 6 | both | Legacy `VARCHAR2(9) 'DD-MON-YY'` date strings (`SIGNUP_DT`, `INVOICE_DT`, `HIST_DT`) | compared as the raw string; parsed value is an added column, dirty strings (`31-FEB-24`, `N/A`) are anomalies compared as sets | every row | PROPOSED |
| 7 | both | Strings (`VARCHAR2`) | exact, byte-equal after trailing-space trim (Oracle `CHAR` padding); `NULL` vs empty string is a canonicalization rule, not a difference | every row | PROPOSED |
| 8 | both | Aggregates (`SUM` of money, `COUNT`) | rel 0.0 | every mapped table | FACT |
| 9 | analytical | Planted anomalies (37 orphan `INVOICE_LINE`, dirty `SIGNUP_DT`, malformed CSV lists) | compared as sets against the seed manifest; landed in `ow_tp.ops.quarantine_<unit>`; never dropped | anomaly population per unit | FACT |
| 10 | analytical | Quarantine rate | exactly the manifest's enumerated anomaly count, 0 unexplained extra | driver table population per unit | PROPOSED |
| 11 | operational | `cdc_lag_max_s` | **60 s** (rehearsal); rows newer than the target's applied watermark are in flight, not defects | operational tables with a `watermark` | PROPOSED (STOP A row) |
| 12 | operational | `cdc_in_flight_max_rows` (counter watermarks) | 0 (no counter watermarks in this estate) | n/a | PROPOSED |
| 13 | operational | Constraint / index parity | every PK, UK, FK, NOT NULL, CHECK present on target; target-only constraints accepted (`accept_target_only_constraints: true`) | every operational table | PROPOSED |
| 14 | operational | Sequence / identity parity | target sequence `last_value` >= source `LAST_NUMBER` at the pin; `identity` named per table (`SEQ_CUSTOMER_MASTER`, `SEQ_ENTITY_ATTR_VALUE`, `SEQ_BILLING_AUDIT_LOG`, `SEQ_*_HIST`) | 5 sequence-backed tables | PROPOSED |
| 15 | operational | Trigger side effects | `_HIST` rows produced by `trg_*_hist` compared as sets; `trg_sub_no_uncancel` and `trg_usage_events_check` verified by behavioural test in the unit PR, not by recon | affected tables | PROPOSED |
| 16 | operational | Watermark | every operational mapping names a `watermark` column (`UPDATED_AT`/`CREATED_AT`/`LOGGED_AT`, or `ORA_ROWSCN` where none exists); a table with none is graded strictly | every operational table | FACT (playbook rule) |
| 17 | both | Isolation | source `SET TRANSACTION READ ONLY` / `AS OF SCN <pin>`; target: Lakebase `REPEATABLE READ` snapshot; Delta: table version pin | every run | PROPOSED |

## Recon economics

| Field | Value | Mark |
|---|---|---|
| `full_diff_row_threshold` | 1 000 000 rows (every table in this estate, max 150 000, gets a full row diff) | PROPOSED |
| `sample_size` | 10 000 (only used above the threshold) | PROPOSED |
| `pk_set_ranges` | 16 | PROPOSED |
| `source_concurrency` (legacy query cap) | 2 per unit, 4 total across concurrent children | PROPOSED |
| Fixture-first | children develop against the seeded fixture / branch copy; one live read per unit inside the cap | FACT |

## Amendment procedure
A tolerance changes only by an explicit human reply recorded in `06_decisions.md`. The change is a
new dated version (`tol-p1-v2`, ...) that keeps the old rows, re-issues both `.md` and `.json`
together, and states the re-verification scope for waves already merged under the old version.
`result.json` records the version it ran under. Grading-only fixes (canonicalization rules) are the
one exception and still get a decision row.
