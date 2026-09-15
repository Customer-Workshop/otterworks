# Pipeline 1 — Oracle dialect and platform rules harvested from wave 1

Rules the wave-1 pilot proved on the live estate. They extend `oracle-plsql` and
`databricks-lakebase` for the rest of pipeline 1; every later wave is expected to follow
them without rediscovering them.

## Types

- `NUMBER(10)` overflows `int4`: map it to `bigint`, never `integer`. `NUMBER(4)` →
  `smallint`. `NUMBER(p,s)` → `numeric(p,s)` / `DECIMAL(p,s)`, never float.
- Oracle `DATE` carries a time part. The parsed companion of a `DD-MON-YY` string column is
  `timestamp` (Lakebase) / `TIMESTAMP_NTZ` (Delta), not `date` — a `date` target mismatched
  every keyed comparison on `INVOICE_HEADER`.
- Oracle `TIMESTAMP` (zoneless source) → `TIMESTAMP_NTZ`, not `TIMESTAMP`: the zoned type
  renders as an instant and fails tier 3 on every row (P1-D3).
- `python-oracledb` returns `NUMBER` as a float unless `oracledb.defaults.fetch_decimals`
  is `True`. Without it, money lands as `DOUBLE` and exact-equality recon still passes.

## Constraints and triggers

- Do not add foreign keys Oracle does not enforce: they reject the orphan rows D8-01
  requires reproducing.
- A trigger that validates against another table (the `CODES` lookup) cannot become a Delta
  `CHECK`: it splits into a `CHECK` for the static predicate plus a documented load-time
  expectation for the lookup.
- A unique-value swap between two surviving keys cannot converge through row-wise upserts.
  Declare non-key `UNIQUE` constraints `DEFERRABLE` in the unit's own DDL; retrofitting
  `DEFERRABLE` onto a table another unit owns is DDL on a shared object and is not allowed.
- Upsert loaders must delete source-dropped keys before inserting, or a `UNIQUE` value that
  moved to a retired key collides with its old owner.

## Platform

- The Lakebase pooled endpoint host rejects the generated OAuth credential (SASL
  authentication failed); use the direct endpoint host.
- A Lakebase branch that has a TTL cannot have child branches. The wave branch a later wave
  will be cut from must be switched to `no_expiry` first (`update-branch` with update mask
  `spec.no_expiry`), which means it has to be dropped by hand at pipeline close.
- `create-branch` takes its source and expiry under `spec` (`spec.source_branch`,
  `spec.ttl` or `spec.no_expiry`), not under `status`.
- The guard blocks any single program that both reads Oracle and writes a target, and
  blocks shell command substitution and shell function definitions inside Databricks or
  legacy commands. Unit code is therefore two scripts (extract, load), with logic in Python
  files rather than shell.
- `allowed_targets.json` names catalogs but not schemas, so a loader pins its own writable
  schema; resolve the committed allowlist from the script's own location and reject a
  caller-supplied substitute.

## Recon on the degraded JDBC route

- `dbx-recon run --family oracle` refuses at the CLI. The gate drives the harness engine
  with the repo-local Oracle adapter (`run_degraded_recon.py`); every verdict is
  `DEGRADED`, `official_verdict=false`, `reason=d10_01_denied`, and is never described as an
  official harness verdict.
- The adapter reads no constraint metadata, so tiers 5–7 are UNVERIFIED and
  `merge_eligible` is always false. That is structural, not a data failure.
- `factory-doctor` has no Oracle privilege query, so `source_principal_read_only` stays
  unverified; the read-only grants are confirmed by hand and recorded.
- The harness writes `result.json`, not the `*.recon.json` / `"kind": "recon-report"`
  artifact `tp-pre-pr-self-check` asks for. The checklist and the harness disagree; units
  emit the report artifact alongside rather than weakening the gate.
- Source-side op SQL runs on Oracle, so it is Oracle dialect with quoted lowercase result
  aliases so both sides match by name.
