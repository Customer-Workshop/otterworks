# 02 Tolerances (correctness contract), version 1 (approved at STOP A, D-010)

"Same data" means the value below after the named canonicalization rule, on both sides.

| Source type | Target type | Match rule | Canonicalization |
|---|---|---|---|
| NUMBER(p,0), p <= 18 (ids, counts, codes) | int32 if every value fits, else int64 | exact | none |
| NUMBER(p,s) s > 0, and money | Decimal128 | exact at source scale (`numeric_abs_tol` 0) | `decimal_round` half_even at source scale |
| NUMBER without precision | Decimal128 until the STOP B min/max/scale probe proves int-safe | exact | `decimal_round` |
| VARCHAR2 / NVARCHAR2 | string | exact, byte for byte | none |
| CHAR | string | exact after trailing-space strip | `rstrip_spaces` |
| NULL / Oracle empty string | field omitted on target | NULL, '' and missing are equal | `empty_string_is_null` (target policy `missing`), `null_missing_equiv` |
| DATE / TIMESTAMP | BSON date, UTC-naive both sides | exact to the millisecond | `datetime_utc_truncate_ms` |
| VARCHAR2 text dates (`*_DT`, DD-MON-YY) | BSON date plus the raw string kept for display | exact; unparseable values (expected 50) quarantined by id, compared as a set | `date_string_to_date` `%d-%b-%y`, pivot confirmed at STOP B |
| `*_YN` CHAR(1) | bool | exact | `yn_to_bool` |
| `*_CSV` / `*_IDS` lists | array of string | exact, order kept | `csv_to_array` drop_empty; malformed (expected 31) quarantined, compared as a set |
| ENTITY_ATTR_VALUE rows | `customers.attributes[]`, one entry per row, duplicates kept | multiset equal per customer (count and name/value pairs) | none |
| INVOICE_LINE rows | embedded `invoices.lines[]`, ordered by line number | per invoice: line count, per-line values, sums exact | none |
| Orphaned INVOICE_LINE rows | `quarantine_invoice_line` | exactly 37, same keys as a set | none |
| String comparisons | binary (no casefold) unless the census finds NLS case-insensitive logic | exact | `collation_casefold` off |
| Report aggregates (totals, balances, counts) | computed from target | exact to the cent (`aggregate_rel_tol` 0) | amounts rendered as 2-decimal strings |

Other contract items:
- Connectivity policy: `online`. Resolved axes: source_access `live`, target_access `migration_cluster`.
- Row-diff threshold: 200,000 (above the 100,000 default so every table, including the 150,000 invoice lines, is fully row-diffed; no sampling).
- Sample size (only used above the threshold): 1,000.
- Source query cap: 1 concurrent recon query against Oracle.
- Re-run cap: 3 full pipeline re-runs per child, then escalate.
- NULL vs missing: `null_missing_equiv`.
- Idempotency: every loader re-run yields identical counts and checksums.
- Amendments: only by explicit approval, as a new dated row (old kept), a new `version` in both
  files, and the list of merged units to re-verify. Grading-only fixes (canonicalization or
  harness bug, no data or tolerance value change) are pre-approved: apply, log, mention at wave close.
