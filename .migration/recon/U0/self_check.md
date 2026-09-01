# U0 pre-PR self-check evidence

Evidence produced for U0 under the approved 2026-09-01 amendments (single whole-table
`codes` gate on the composed key; `fixture_meta` count-only with `INITIALIZED_AT`
declared-unexercised). The authoritative artifact is `.migration/recon/U0/gate/result.json`
(verdict PASS, tiers 4/12/105); it was not modified.

- [x] **NULL and missing attribution cannot fail open.** `scripts/tp_mongo/load_u0.py` applies explicit `vc`/`ch` null handling; tier 2 defers the six `empty_string_is_null`/`rstrip_spaces` fields to tier 3, which diffed every key post-canonicalization (`gate/result.json`).
- [x] **Every reference is scoped to the unit namespace.** The loader accepts only `ow_tp_mongodb_032752` and only the four U0 collections registered in `.migration/04_progress.md`; `load_report.json` records the target db and `ns` counts (32/69/3/1 = 105).
- [x] **No DDL drops, replaces, or alters a shared table.** Oracle access is SELECT-only; drops are limited to the four owned MongoDB collections.
- [x] **Idempotency proven by rerun, not inferred.** A second full load + gate run: `load_report.rerun.json` (`dropped`/`recreated` true, identical 32/69/3/1, no doubling) and `gate_rerun/result.json` (second PASS, identical 4/12/105).
- [x] **Recon values recomputed from the target platform.** Both gate runs read Atlas live through the harness adapters; no values copied from a previous report.
- [x] **Parity-versus-tolerance decision comes from the contract.** Tolerances 1.0 and canonicalization 1.0 are passed unmodified; `.migration/05_decisions.md` records STOP B and the two amendments.
- [x] **No secrets or requester identity in source, evidence, or history.** Secrets are referenced by env-var name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`); branch diff scanned for URI/DSN/credential values, names and email addresses — none found.
- [x] **Unverified paths declared.** `docs/tech-partnerships/recon/U0.recon.json` (`make tp-validate-recon`: PASS) lists the declared-unexercised `INITIALIZED_AT`, the fixture-only run mode, the unexercised reader path and the unused quarantine DB.
- [x] **`make tp-smoke` is green.**

## Recon key rendering (declared)

The harness keys source rows by the cursor-description name of each key expression, so:

- `codes`: the approved `CODE_TYPE || '#' || CODE_VAL` is emitted whitespace-free
  (`CODE_TYPE||'#'||CODE_VAL`) — Oracle strips whitespace from description names. Same
  expression, same composed value.
- `fixture_meta`: canonicalization v1.0 `datetime_utc_truncate_ms` is applied source-side
  in the key expression, because the harness compares keys pre-canonicalization and
  `TIMESTAMP(6)` cannot round-trip through a millisecond BSON date.

Both renderings are asserted against the approved entry by `scripts/tp_mongo/unit_mapping.py`
and recorded in `.migration/recon/U0/mapping/u0.json` under `_recon_key_rendering`. Fields,
root tables and root scopes are copied verbatim; no contract file was changed.

## Environment note

`/home/ubuntu/.venvs/recon` was absent and was rebuilt locally from the plugin-provided
harness (`recon selftest`: PASS, 9 rules). The runner prefers the blueprint path and falls
back to `recon` on PATH.
