# Wave 2 close

Landed: 3 of 3 batches passed their own recon; 2 merge-eligible.
Independent verify: PASS.
Failed: none.
Blocked on missing inputs: none.
Held back by circuit breaker: none.
Awaiting manual merge: https://github.com/Cognition-Partner-Workshops/otterworks/pull/1744, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1746
Passed, not merge-eligible (fixture/local evidence or recon warnings): https://github.com/Cognition-Partner-Workshops/otterworks/pull/1745

Verifier findings:
- All three wave-2 units passed their own independent live recon against the migration cluster, with no mismatches, no drift and no source double-run needed.
- U2-invoices passes but is not merge-eligible because its invoice lines embed is scoped, and a full comparison showed every invoice's lines exactly match the source, so this is a structural flag, not a data defect.
- All 18,750 invoices carry a tenant id that does not exist in the source tenants table either, and the migration preserves this exactly, so consumers must not assume invoices resolve to a tenant.
- The subscription history and billing audit log collections are empty in the source, so their pass only shows the empty state migrated.
- All seven post-wave app queries and the six live app queries return identical results from Oracle and the migrated MongoDB database.
- The U4 service tests all pass against the Mongo fixture, but three lint issues remain in its test files, none in app code and none checked by CI.
- Recon output is redacted with unsalted hashes because the engagement redaction salt is not set.
- An empty leftover connectivity-probe collection remains in the migration target database.

PROFILE FEEDBACK (fold into skills/mongo-migration/profiles/<family>.md before the next wave):
- 02_tolerances.md names the collection quarantine_invoice_lines (plural) while the spec uses quarantine_invoice_line
- Env: /home/ubuntu/.venvs/recon had no `recon` package installed; had to pip install -e the plugin harness (0.3.2) before `recon selftest`.
- Env: go and npm (nvm) not on default PATH, so `make tp-smoke` needed PATH=/usr/local/go/bin:~/.nvm/versions/node/v20.20.2/bin to pass.
- Harness live summary/report states merge-ineligible reason as 'fixture/continuous evidence never merges' for a live migration_cluster run whose only blocker is the scoped-embed warning
- Loader location services/legacy-billing/migration/<unit>/ needs parents[4] to reach .migration/tools (U1 lived under .migration/units)
- No canonicalization rules derived; every field was covered by the spec's own rules.
- Oracle usage_events.occurred_at TIMESTAMP(0) truncates fractional seconds on insert; Mongo must truncate to match
- Quarantine added_fields values (quarantine_reason, source_table) are not given in the spec; derived as quarantine.reason and root_table
- RECON_REDACT_SALT is not provisioned; live artifacts redacted unsalted
- RECON_REDACT_SALT not provisioned: live artifacts redacted with unsalted hashes.
- RECON_REDACT_SALT not set; live artifacts are unsalted-hashed
- Single-node replset fixture needs directConnection=true from the host
- Tier 4 app parity not run: brief supplies no --ops.
- customers.attributes: ENTITY_TYPE is implicit in the embed and must be dropped before build_root_docs
- make tp-smoke not runnable locally (no go toolchain); CI covered it
- recon venv at /home/ubuntu/.venvs/recon had drivers but no bound harness (maintenance step had not run); re-ran the blueprint's pip install -e of the plugin 0.3.2 harness before `recon selftest` passed
- tp-pre-pr-self-check `make tp-smoke` needs go/npm on PATH; npm only via nvm and sourcing nvm.sh is refused by the dbx-migration-factory shell guard, so smoke stops at the Collab Service step
- tp_recon_report.py implicitly requires load record source_counts.invoice_line = all INVOICE_LINE rows incl. orphans (it subtracts the quarantine T1 count) and expected_orphan_hashes = sha256(str(LINE_ID))[:16]; neither is documented in the brief or mongo_load

Per batch:
- w2-b01: PASS. U2-invoices landed: 18,750 invoices (149,963 embedded lines) + 37 quarantined orphan lines in ow_tp_mmp_live; live recon PASS (T1-T3, 168,750 keyed rows, idempotent rerun) with the expected D-012 scoped-embed warning, so merge_eligible=false; PR #1745 open, CI green. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1745
- w2-b02: PASS. U3-billing-core: 10 billing-core collections loaded into ow_tp_mmp_live; live recon PASS (T1 11/T2 28/T3 901), idempotent rerun, merge_eligible=true, CI green, PR #1744 open (not merged). https://github.com/Cognition-Partner-Workshops/otterworks/pull/1744
- w2-b03: PASS. U4-app-backend Mongo backend landed in PR #1746 with fixture and one live recon PASS (migration_cluster, merge_eligible=true); CI green, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1746
