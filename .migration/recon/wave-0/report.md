run_id: single-session-wave-0
manifest_sha: 1a02333493fe

# Wave 0 independent reconciliation (playbook 4 Part 1)

- Engagement: offline OW_BILLING (Oracle) -> MongoDB, run branch `tp-run/mongodb-20260926T164803Z-rt-offline`
- Access axes: source_access=`ddl_only`, target_access=`local` (`.migration/08_connectivity.json`)
- Verifier: independent session (migrated nothing; read only the run branch and the `--w0-b01` branch; loader re-run and gate re-executed from the spec, PR chat not read)
- Inputs: `03_mapping_spec.json` map-draft-2 (codes-only verbatim subset, same version + canonicalization block), `02_tolerances.json` tol-1, `waves/wave-0.json`, `fixtures/ow_billing_demo.json`
- Harness: recon 0.3.x from the mongo-migration plugin 0.3.0 (`recon selftest PASS: 9 canonicalization rules exercised`), fresh venv

## Wave verdict

**fixture PASS, live recon pending customer run.** Rehearsal evidence only: `--mode fixture --target-class local`, `merge_eligible=false` in every result.json. Nothing was merged; nothing may merge on this evidence (AGENTS.md rule 11).

| Batch | Unit | Collection | Gate | Verifier verdict |
|---|---|---|---|---|
| w0-b01 | u-00-codes | ow_billing_migration.codes | Tier 1 PASS (1 check), Tier 2 PASS (0 native checks, 1 field deferred to Tier 3), Tier 3 PASS (32/32 keyed, full_diff, 0 duplicate source keys) | **PASS** (fixture, local) |

## w0-b01 / u-00-codes

### Independent re-run

1. Fixture rebuilt on the verifier machine: `make oracle-billing-up && make oracle-billing-seed NS=demo` (Oracle Free, schema OW_BILLING, seed 714559852; CODES=32 rows, matching `fixtures/ow_billing_demo.json`). Fixture never modified.
2. Local target: `docker run -d --name ow-mongo -p 27017:27017 mongo:7`; the only database written is `ow_billing_migration`, the only collection `codes` (verified by listing databases/collections afterwards).
3. Loader taken verbatim from the unit branch at `0921b6d0` (`services/legacy-billing/migration/mongo/load_codes.py`), run once: `loaded=32, quarantined=0, quarantine_reasons={}`. Matches the PR's stated counts.
4. Gate: `recon run --unit u-00-codes --family oracle --mapping <codes-only subset> --tolerances .migration/02_tolerances.json --canonicalization profiles/oracle.md --mode fixture --target-class local --source-dsn-secret OW_BILLING_FIXTURE_DSN --target-uri-secret MONGO_LOCAL_URI --target-db ow_billing_migration --allowed-targets-file .migration/allowed_targets.json --source-concurrency 1 --seed 1` -> exit 0, `verdict=PASS`, `mapping_version=map-draft-2`, `tolerance_version=tol-1`, `redacted=true`, `redaction_salted=false`, `merge_eligible=false`.
5. The verifier result agrees tier-for-tier with the evidence committed on the unit branch (`services/legacy-billing/migration/mongo/recon/u-00-codes/`, generated 17:13Z): same verdict, same tier check counts (1/0/32), same versions and seed.

### Probes past the gate

| Probe | Source (Oracle CODES) | Target (codes) | Result |
|---|---|---|---|
| Row/doc count | 32 | 32 | match |
| Empty-collection check | n/a | 32 docs, `_id_` index present | not empty |
| Null/missing rate per field | CODE_TYPE/CODE_VAL/CODE_DESC all NOT NULL, 0 nulls | codeType/codeVal/codeDesc: missing 0, null 0, empty-string 0 | match |
| Distinct CODE_TYPE | 10 | 10 | match |
| min/max CODE_VAL | 1 / 99 | 1 / 99 | match |
| sum(length(CODE_DESC)) | 230 | 230 | match |
| Duplicate natural keys in target | PK (code_type, code_val) | 0 groups with n>1 on (codeType, codeVal) | none |
| Leading/trailing whitespace rows in source | 0 | n/a (rstrip rule would be a no-op) | none |
| Full keyed compare (all 32 rows, codeType/codeVal/codeDesc/_id) | | | 0 mismatches |
| Boundary docs | first `CUST_STATUS/1 active`, max `CUST_STATUS/99 conversion-limbo` | same docs present with `_id` `CUST_STATUS:1` / `CUST_STATUS:99` | match |
| BSON types | | codeType string, codeVal **int (int32)**, codeDesc string, 32/32 | see finding F1 |

### App-level parity replay

The four `codes` lookups in `services/legacy-billing/app/facade.py` (TENANT_STATUS on tenants.status_cd, USAGE_KIND on usage_events.kind_cd, INV_STATUS on invoices.status_cd, DUN_STATUS on dunning_attempts.status_cd) were replayed: for every distinct code value actually referenced in the fixture the Oracle `LEFT JOIN codes ... code_desc` result was compared with `codes.find_one({codeType, codeVal}).codeDesc`. 9/9 lookups matched; per-type code counts match (TENANT_STATUS 2/2, USAGE_KIND 3/3, INV_STATUS 4/4, DUN_STATUS 3/3); no referenced code value is unresolved on either side, so LEFT JOIN null-preserving semantics were not exercised by the fixture data.

## Findings (none blocking the fixture verdict)

- **F1 (low, spec conformance):** the mapping spec declares key field `codeVal` as `bson_type: long`, but the loader writes Python `int` -> BSON int32 (32/32 docs `$type` = `int`). The harness did not raise `type_mismatch` because `codeVal` is a key field, not a graded `fields[]` entry, so key-field BSON types are not type-checked by Tier 3. Functionally harmless for NUMBER(4), but either the loader should emit `bson.Int64` or the spec should say `int`; whichever is chosen goes through the STOP B change process, not this report. Evidence: probe `$type` aggregation; spec `collections[codes].decision.key_fields[1].bson_type`.
- **F2 (low, operability):** the collection has only the `_id_` index (`_id` = `"<codeType>:<codeVal>"`); the app read paths look up by `(codeType, codeVal)`, which is unindexed. Irrelevant at 32 documents but a compound unique index on `{codeType:1, codeVal:1}` would also encode the source PK. Evidence: `list_indexes()` -> `['_id_']`.
- **F3 (info):** `redaction_salted=false` in both the unit's and the verifier's result.json; `RECON_REDACT_SALT` is not set in this offline engagement. Acceptable because the fixture is synthetic (fixture manifest `masked_columns: []`), but a live run should set the salt.
- **F4 (info):** the loader's quarantine paths (`empty_string_is_null:CODE_TYPE`, `null_key:CODE_VAL`, `duplicate_key`) are unreachable against this schema (all three columns NOT NULL, PK on the key) and were exercised by no row; quarantine counts of 0 are therefore expected rather than evidence of clean data.
- **F5 (info):** the unit branch touches nothing under `.migration/` (merge-base diff: README.md, load_codes.py and the three recon evidence files only), consistent with rule 6.

## Not covered / pending

- Live recon: not possible (source_access=ddl_only, no migration cluster). Live `--mode live --target-class migration_cluster` against the customer's Oracle and the Atlas migration cluster is the merge gate and remains pending a customer run.
- Tier 4 (`--ops`): no recorded representative operations exist for this unit; the manual replay above stands in for it and is not a harness verdict.
