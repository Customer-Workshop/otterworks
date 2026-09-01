# U0 pre-PR self-check evidence

This checklist records the evidence produced for U0 before the PR review.

- [x] **NULL and missing attribution cannot fail open; they are rejected or explicitly attributed according to the unit contract.** Evidence: `scripts/tp_mongo/load_u0.py` applies explicit `vc`/`ch` null handling; `.migration/recon/U0/mapping/core.json` and `.migration/recon/U0/load_report.json` cover the U0 fields, whose source rows loaded with the expected counts.
- [x] **Every catalog, schema, collection, and table reference is scoped to the unit namespace and uses the `ow_tp` / `ow-tp-` prefix.** Evidence: `scripts/tp_mongo/load_u0.py` accepts only `ow_tp_mongodb_032752` or its registered quarantine name and writes only the four U0 collections; `.migration/recon/U0/load_report.json` records `target_db: ow_tp_mongodb_032752`.
- [x] **No DDL drops, replaces, or alters a shared table.** Evidence: `scripts/tp_mongo/load_u0.py` performs only SELECTs against Oracle; its drop/recreate operations are limited to the four owned MongoDB U0 collections.
- [x] **Retention and cleanup logic is safe on a rerun and does not remove a newer run's data.** Evidence: `.migration/recon/U0/load_report.json` and `.migration/recon/U0/load_report.rerun.json` show the isolated U0 database and exactly four owned collections were reset, with no document-count doubling.
- [x] **Cleanup paths retain run evidence and recon artifacts.** Evidence: `.migration/recon/U0/load_report.rerun.json`, `.migration/recon/U0/core_rerun/result.json`, and the original U0 recon artifacts remain present after the rerun.
- [x] **No secrets, tokens, or real distribution-list/email addresses occur in source, evidence, or commit history.** Evidence: branch history and diff scans found no URI, DSN value, credential value, requester name, or email address. The broad history grep's `password` matches are source variable/argument names only; no secret values were present.
- [x] **The parity-versus-tolerance decision matches the contract; it was not invented during implementation.** Evidence: `.migration/05_decisions.md` records STOP B approval; `.migration/02_tolerances.json` and the generated recon reports cite the approved tolerance version.
- [x] **Idempotency was proven by an actual rerun, not inferred from code.** Evidence: `.migration/recon/U0/load_report.rerun.json` records `dropped: true`, `recreated: true`, and unchanged `source_rows`, `inserted`, `docs_after`, and `ns_docs_after` for all four collections; `.migration/recon/U0/core_rerun/result.json` is a second `U0-core` PASS.
- [x] **Recon values were recomputed from the target platform, not copied from migration memory or a previous report.** Evidence: `.migration/recon/U0/core_rerun/result.json` was produced by a fresh live recon invocation after the second load; its Tier 1–3 check counts are 2, 9, and 72.
- [ ] **Every unverified or untested path is listed in the recon report.** **GAP:** the installed harness result schema does not emit an explicit `unverified_paths` field. The known ungraded codes and `fixture_meta` parity paths are recorded below and in their generated reports.
- [ ] **The recon report declares `"kind": "recon-report"` and is stored as a `*.recon.json` artifact when using the machine-readable report schema.** **GAP:** the installed harness emits authoritative `result.json` files and does not emit the requested `kind`/`*.recon.json` shape. `make tp-validate-recon FILE=.migration/recon/U0/core/result.json` reported the schema mismatch; the harness output was not modified or wrapped.
- [x] **Capability preflight passed for every required path before live work.** Evidence: `.tp-preflight/atlas-capabilities.json` records 8 verified probes and 0 denied probes. The manifest contains no URI or credential values and is outside the migration evidence path, so it was not committed.
- [x] **`make tp-smoke` is green.** Evidence: the command completed with `tp-smoke: all checks passed`.

## Declared parity coverage gaps

- The ten `codes` runs are authoritative FAILs for the approved v1.0 mapping because the target adapter counts all 32 documents while each source scope contains only one `CODE_TYPE`; the proposed key-expression probe is separate, non-authoritative, and PASS.
- `fixture_meta` has an authoritative FAIL because the harness compares pre-canonicalization keys while Oracle microseconds (`454979`) exceed BSON millisecond precision (`454000`).
- The `codes` and `fixture_meta` keyed parity paths therefore remain ungraded for the approved mapping and are not described as green.

## Environment note

The org-blueprint venv `/home/ubuntu/.venvs/recon` was absent when checked. The duplicate reusable venv `/home/ubuntu/venvs/recon` was retained and used via explicit override; the recon runner now prefers the org-blueprint path and falls back to `recon` on PATH when that path is absent.
