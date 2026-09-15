# Wave 1 close

Landed: 3 of 3 batches passed their own recon, all DEGRADED (official_verdict=false, d10_01_denied) - not an official Oracle harness verdict.
Independent verify: PASS, 0 PRs merged (verifier migrated 0 units, wrote nothing, edited no ledger file).
Failed: none.
Blocked on missing inputs: none.
Held back by circuit breaker: none (0 failures, threshold 3 same-class).
Launch mechanism: child sessions, not run_workflow - the workflow runner's process has no credentials (the process it starts inherits no environment, so DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET and the AWS pair are absent and the pre-flight factory-doctor fails databricks_identity), and writing them to disk was refused.
Awaiting manual merge: https://github.com/Cognition-Partner-Workshops/otterworks/pull/1569, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1570, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1571, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1572, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1573, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1574
Cost: estimated source_statements=60, target_statements=48, source_rows_fetched=169668, target_rows_fetched=169668; actual source_statements=162, target_statements=150, source_rows_fetched=338826, target_rows_fetched=338727, harness time 727s. Verifier depth sampled.

Verifier findings:
- All six units AGREE: row counts, money sums, keyed digests and anomaly sets recomputed from Oracle read-only and from the target platform directly (never from CDC output).
- Every verdict is DEGRADED with official_verdict=false, reason d10_01_denied; none of this is an official Oracle harness verdict.
- The tier-5 block in the three Lakebase result.json files reports mismatched_ranges equal to the range count while passed=true: no range digest was available, so every range fell back to streaming keys and missing/extra on target are 0. A metric artifact, not a data problem.
- Idempotency is proven by real reruns for the three Delta units (repeat MERGEs, 0 inserted, 0 deleted, counts unchanged). For the three Lakebase units it rests on the loader's own log; Lakebase exposes no history the verifier can read.
- Parsed date columns on both invoice tables are TIMESTAMP_NTZ while the parent-owned mapping specs declared DATE. The parent has since changed gen_mapping_specs.py to emit timestamp / TIMESTAMP_NTZ, so spec and target now agree.
- Write scope clean: Delta history shows the wave wrote only silver.usage_events, silver.invoice_header and silver.invoice_line; the ow_tp.bronze.* tables the loaders read predate the wave and were not touched. No guard block.
- Unverified by design on the JDBC route: tiers 5-7 (source-side constraint, index and identity parity) and factory-doctor's source_principal_read_only, which has no Oracle privilege query behind it.

Skill feedback to fold in before the next wave:
- A complete-snapshot MERGE loader (WHEN NOT MATCHED BY SOURCE THEN DELETE) has no ordering between snapshots: fine for a one-shot backfill, but backfill-planner should require a snapshot fence checked and merged in one atomic protocol before such a loader recurs.
- A trigger that validates against another table (the CODES lookup) cannot become a Delta CHECK constraint: it splits into a CHECK for the static predicate plus a documented load-time expectation for the lookup.
- A unique-value swap between two surviving keys cannot converge through row-wise upserts. Later units must declare non-key UNIQUE constraints DEFERRABLE in their own DDL; wave 1 accepted a loud whole-transaction failure instead, because retrofitting DEFERRABLE onto a shared wave-branch table would be DDL on a shared object.
- A write-scope check is only as good as the allowlist it reads: resolve the committed .migration/allowed_targets.json from the script's own location and reject a caller-supplied substitute.
- Do not add foreign keys Oracle does not enforce: they reject the orphan rows D8-01 requires reproducing.
- Idempotency evidence is still caller-asserted free text; a structured two-execution artifact comparing target-state digests needs the loader to emit it, which is shared tooling beyond a unit's scope.
- NUMBER(4) -> smallint; NUMBER(12,2) / NUMBER(12,6) -> numeric(12,2) / numeric(12,6).
- Oracle NUMBER(10) overflows int4: map it to bigint, not integer.
- Oracle TIMESTAMP maps to Databricks TIMESTAMP_NTZ, not TIMESTAMP: the zoned type renders as an instant and fails tier 3 on every timestamp row against a zoneless Oracle source (P1-D3). oracle-plsql should say so.
- Parsed companions for Oracle DATE must be TIMESTAMP_NTZ, not DATE: Oracle DATE keeps its time part, so a DATE target mismatched every keyed comparison. The mapping specs are parent-owned; the child raised it on PR #1573 instead of editing them.
- Set oracledb.defaults.fetch_decimals = True or the driver returns floats and exact-equality money recon fails.
- The Lakebase pooled endpoint host rejects the generated OAuth credential (SASL authentication failed); use the direct endpoint host.
- The degraded JDBC route always yields merge_eligible=false because the adapter reads no constraint metadata (tiers 5-7 UNVERIFIED); that is structural, not a data failure.
- The guard blocks any single program that both reads the legacy source and writes the target, so a unit's code is two scripts (extract, load).
- The guard blocks shell command substitution and shell function definitions inside Databricks/legacy commands; move that logic into a Python file.
- The harness emits result.json, not the *.recon.json / "kind": "recon-report" artifact tp-pre-pr-self-check asks for; the checklist and the harness disagree.
- The recon report emitter should carry anomaly-set and idempotency outcomes into the emitted verdict and exit status; a schema-valid report does not by itself prove either.
- Upsert loaders must delete source-dropped keys before inserting; a UNIQUE value that moved to a retired key otherwise collides with its old owner.
- allowed_targets.json names catalogs but not schemas, so a loader must pin its writable schema itself; an arbitrary --target-schema otherwise escapes the write allowlist.
- factory-doctor has no privilege query for the Oracle family, so source_principal_read_only stays unverified; the grants have to be confirmed by hand (session_privs / user_tab_privs / user_role_privs) and recorded.

Per batch:
- w1-a: PASS. tenants 69, plans 3, codes 32 into Lakebase billing on branch mig-p1-w1; transactional recon PASS per unit, DEGRADED / official_verdict=false https://github.com/Cognition-Partner-Workshops/otterworks/pull/1569, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1570, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1571
- w1-b: PASS. usage_events 814 into ow_tp.silver.usage_events; live recon PASS, DEGRADED / official_verdict=false https://github.com/Cognition-Partner-Workshops/otterworks/pull/1572
- w1-c: PASS. invoice_header 18,750 and invoice_line 150,000 (37 orphan lines reproduced) into ow_tp.silver; live recon PASS per unit, DEGRADED / official_verdict=false https://github.com/Cognition-Partner-Workshops/otterworks/pull/1573, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1574
