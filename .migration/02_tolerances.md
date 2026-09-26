# 02_tolerances: correctness contract (version `tol-1`)

Status: PROPOSED at setup; resolved at STOP A (see `05_decisions.md` D-001). Intake said "tolerances: exact", so every row is exact match; defaults come from the Oracle profile's canonicalization rules.

| Oracle type | Mongo type | Comparison | Tolerance |
|---|---|---|---|
| `NUMBER(p,0)`, p<=18 | int64 / int32 | exact | 0 |
| `NUMBER(p,s)` s>0 or p>18, `NUMBER` unbounded | Decimal128 | exact after canonical decimal normalisation (trailing zeros) | `numeric_abs_tol = 0` |
| `DATE`, `TIMESTAMP` | BSON date (UTC) | exact instant | 0 |
| `VARCHAR2`, `NVARCHAR2`, `CLOB` | string | exact; Oracle empty string == NULL == missing field | exact |
| `CHAR(n)` | string | exact after trailing-space trim (profile rule) | exact |
| Flag columns (`Y`/`N`, `1`/`0`, `T`/`F`) | bool | exact after profile flag canonicalisation | exact |
| CSV-in-a-column | array of strings | exact after split/trim (profile rule) | exact |
| Dates stored as text | BSON date or string, per mapping decision | exact after profile date-text canonicalisation | exact |
| Aggregates (SUM/COUNT per collection) | | exact | `aggregate_rel_tol = 0` |

## Parameters (`02_tolerances.json`)
- `full_diff_row_threshold`: 100000. Above it, keyed sampling (`sample_size` 1000) plus full aggregates; below it, full row diff.
- `source_concurrency`: 1. At most one recon query hits the source (or the fixture) at a time.
- Re-run cap: a child may re-run the full pipeline 3 times, then must escalate (rule 7).
- NULL vs missing field: `null_missing_equiv`.

## Connectivity policy
- Policy: `offline` (intake). Nothing is probed. Resolved axes (`08_connectivity.json`):
  `source_access = ddl_only`, `target_access = local` (`mongo:7` via `docker-compose.local.yml`, `MONGO_LOCAL_URI`).
- Consequence: merge evidence needs `live`/`snapshot` AND `migration_cluster`. This engagement has neither, so every recon run is rehearsal evidence; the customer must run `live`/`snapshot` recon against a migration cluster inside their network before STOP C can be authorized.

## Amendment rule
A tolerance changes only by explicit human approval: new dated row in `05_decisions.md`, old row kept, new `version` in both files, plus the list of verified units that must be re-verified. Grading-only fixes (canonicalisation rule or harness bug, no data or tolerance value change) are pre-approved: apply, log, mention at wave close.

## tol-2 (approved at wave-1 close, D-011, provenance user:)
Quarantine-aware grading: a source value that the loader quarantines (reason code recorded) compares equal to a missing target field. Implemented for text dates via the engagement profile overlay `.migration/profiles/oracle.md` (`date_string_to_date.params.unparseable=null`, combined with `null_missing_equiv`). Not implementable for malformed CSV lists: recon 0.3.2 `csv_to_array` has no `unparseable` param, so those 13 planted values in CUSTOMER_MASTER still grade as Tier 3 diffs until the plugin adds one. All other tolerances unchanged from tol-1 (exact, sample 1000, threshold 100000, concurrency 1).
tol-2 annotation (moved here because recon 0.3.2 rejects non-harness keys in the JSON): canonicalization profile = `.migration/profiles/oracle.md`; the overlay declares the spec's date aliases `date_string_to_date:dby-b3d57e` and `date_string_to_date:dbyHMS-30dd8b` explicitly because `merge_canon_rules` overrides by exact name only.
