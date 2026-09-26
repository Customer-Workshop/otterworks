# 01_conventions

## Repository and branches
- Repo: `Cognition-Partner-Workshops/otterworks`.
- Run branch: `tp-run/mongodb-20260926T164927Z-rt-live`, cut from `origin/tech-partnerships`. All `.migration/` state, wave 0, every unit PR, wave-close, coexistence and cutover documents target this branch.
- Never merge into `tech-partnerships` or `main`.
- **Branch isolation rule (customer instruction):** in this engagement only `tech-partnerships` and the run branch exist. Do not read, fetch, check out, diff, or search any other branch or PR of this repo (including `tech-partnerships-solutions` and any closed PR). Unit implementation is derived from the source estate on `tech-partnerships` and from this `.migration/` workspace only.
- Unit branches: `tp-run/mongodb-20260926T164927Z-rt-live/unit-<unit_id>`; unit PRs target the run branch. PR reviewer: none. Merge authority: recon-harness PASS (live, migration_cluster) plus the wave's `auto_merge` value.

## Naming
- Target database: `mmp_rt_billing` (Atlas `otterworks-demos/otterworks-demo`). The only write target; see `allowed_targets.json`.
- Collections: `snake_case` singular-domain names (`customers`, `invoices`, `plans`, ...); mapping in `03_mapping_spec.json`.
- Fields: `camelCase` for target documents; `_id` = source primary key (natural) unless the mapping spec says otherwise.
- Recon artifacts: `recon/<unit_id>/` on the unit PR; result file `recon/<unit_id>/result.json`.

## Secrets (names only, never values)
- Source (app owner, first attempt): `ORACLE_BILLING_DSN`.
- Source (read-only principal): `ORACLE_BILLING_RO_DSN`.
- Target (migration cluster, readWrite@mmp_rt_billing): `MONGODB_MMP_RT_TARGET_URI`. `MONGODB_ATLAS_URI` is forbidden for this engagement.
- Secret values never appear in artifacts, PR bodies, logs, chat, or code. Recon output is redacted (harness default).

## Source access
- Read-only always. Oracle estate is not modified after the customer pre-engagement steps (container up, seed `NS=mmprt SCALE=demo`, RO user + SELECT grants).
- Source concurrency 1; live reads only from this VM (children cannot reach `localhost:52521`).

## Tooling
- Recon harness: `~/.venvs/recon/bin/recon` (mongo-recon-harness, plugin mongo-migration 0.3.0). Profile: `profiles/oracle.md`.
- Connectivity probe: `skills/mongo-migration/connectivity_probe.py`; offline guard: `skills/mongo-migration/offline_guard.py`.
- Environment note: the org also installs `dbx-migration-factory`, whose PreToolUse guard reads `.migration/allowed_targets.json` and requires a non-empty `catalogs` list; the file therefore carries `catalogs` mirroring `databases`.

## Process
- Stops: STOP A soft (60 s default-accept), STOP B hard, STOP C hard. Routing: this web session only.
- Every stop/halt/wave-close writes one row to `05_decisions.md` with honest provenance.
- Wave manifests always set `auto_merge` explicitly.

## Profile feedback folded in after wave 0 (oracle profile addenda for this engagement)
- Mapping `root_table`/`child_table` are schema-qualified (`OW_BILLING.<TABLE>`): the read-only principal has no synonyms, so unqualified names fail Tier 1 with ORA-00942.
- `recon run` grades every collection in `--mapping`; batches use the unit-scoped views `.migration/mapping/<unit>.json` (filtered copies of `03_mapping_spec.json`, same version).
- Every shell that touches the fixture or the harness sources `~/.config/ow_billing_env.sh` (local, untracked: Oracle DSN env vars + `RECON_REDACT_SALT`).
