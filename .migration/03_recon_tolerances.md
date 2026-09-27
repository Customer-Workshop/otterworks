# 03 — Reconciliation tolerances (tol-20260927c-v1)

Frozen at STOP A. Changing any row needs a new STOP A row in `06_decisions.md`; the old row stays.
Machine copy: `03_recon_tolerances.json` (read by `dbx-recon`). Only a `dbx-recon` verdict counts as parity.

| Field | Value | Population | Why |
|---|---|---|---|
| Money (`NUMBER(12,2)`: subtotal, tax, total, amount, monthly_fee, overage_amount, total_amt) | exact, `numeric_abs_tol = 0.0` | every mapped money column | finance close and invoice rows must match to the cent |
| Row counts | exact | every mapped table within its `root_where` | one missing row is a defect |
| Aggregates (SUM/COUNT/MIN/MAX per table) | `aggregate_rel_tol = 1e-9` | Tier 1 | floating carry only |
| Other numerics (units, quotas, rates) | exact | rating and usage columns | integers or fixed-scale decimals in the source |
| Dates / timestamps | `datetime_utc_truncate_ms`; Oracle `DATE` keeps time-of-day; Oracle `TIMESTAMP(6)` -> Lakebase `timestamp(6)` (no zone, prior run D-010) | all date columns | plain Oracle `TIMESTAMP` carries no zone |
| Strings | `rstrip_spaces`, `empty_string_is_null` (Oracle `''` is `NULL`) | all VARCHAR2/CHAR | Oracle semantics |
| UUID keys (`VARCHAR2(36)`) | `uuid_normalize` (case-fold) | ids | generated on both sides by the same MD5 rule (`pkg_ow_util.f_md5_uuid`) |
| Tier 3 depth | `full_diff_row_threshold = 5,000,000`, `sample_size = 100,000` | every in-scope table is far below the threshold, so Tier 3 is the keyed full diff on every table | the estate is small; no sampling needed |
| Legacy query cap | `source_concurrency = 4`; one live read per child; independent verifier one more | Oracle `OW_BILLING_RO` | Oracle FREE on a t3.large |
| Nondeterminism | `billing_audit_log.logged_at`, `rating_results.created_at`, `invoices.issued_at` set by `SYSTIMESTAMP` in the source are compared as presence + ordering, not value (declared per mapping spec) | audit / issued timestamps | wall clock differs by construction |
| CUSTBILL file | byte-identical: SHA-256 of the legacy `CUSTBILL_<NS>_ORACLE.dat` equals the SHA-256 of the Databricks-produced file; recorded as a custom gate with both digests as evidence | one file per run | the D7 hand-off is a fixed-width format contract |
| Finance close total | exact per (ccy, record_type) count and sum, legacy finance CSV vs gold table | one close per run | the three numbers |
| Mode | LIVE recon from the session bridge (`dbx-recon --family oracle`, Oracle 23ai/26ai FREE thin mode). No Lakehouse Federation, no port 1521 to serverless, no CDC. Fixture-mode runs are development evidence only | all units | user constraint |
| ML parity | N/A (no scoring surface in scope) | — | — |

Amendment procedure: propose in `06_decisions.md` with old and new value, blast radius (which units re-run), and the re-verification scope; re-run `dbx-recon` for every affected unit before the wave closes.
