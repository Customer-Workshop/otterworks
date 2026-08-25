# MongoDB migrations

Workloads that move OtterWorks production data off the legacy stores and into
MongoDB Atlas. Each workload owns its own target databases (`ow_tp_mongodb_*`)
and nothing else.

## mongo_files — file metadata

The file-service keeps its metadata in the shared DynamoDB table
`otterworks-file-metadata`, one item per stored file, namespaced by an `ns`
attribute. `mongo_files` moves one namespace at a time into
`ow_tp_mongodb_<ns>.files`, with unreadable or incomplete items routed to
`ow_tp_mongodb_<ns>_quarantine.files_quarantine` under a reason code.

Contract: `docs/tech-partnerships/contracts/mongo_files.json`.
Recon evidence: `docs/tech-partnerships/recon/mongo_files.recon.json`.

### Running it

```bash
# target: the local document-store fixture by default
docker run -d --name ow-tp-mongo-fixture -p 27018:27017 mongo:7

scripts/tp-run-deterministic.sh \
  uv run migrations/mongodb/mongo_files/migrate.py --ns demo

TP_RECON_GENERATED_AT='2026-01-15T00:00:00Z' scripts/tp-run-deterministic.sh \
  uv run migrations/mongodb/mongo_files/recon.py --ns demo \
  --out docs/tech-partnerships/recon/mongo_files.recon.json
```

`migrate.py --self-test` exercises the mapping, encoding and quarantine rules
on their own, without touching any store.

Target selection is explicit and defaults to the fixture:

| variable | meaning |
| --- | --- |
| `MONGO_FILES_TARGET` | `fixture` (default) or `live` |
| `MONGO_FILES_FIXTURE_URI` | fixture connection string (default `mongodb://localhost:27018`) |
| `MONGODB_ATLAS_URI` | used only when `MONGO_FILES_TARGET=live` |

### What the migration guarantees

- One document per source item, `_id` = `uuid5` of the DynamoDB partition key,
  so a rerun converges instead of duplicating (writes are per-batch upserts).
- The `ns` attribute becomes the indexed `tenant` field; no document is written
  without it.
- Numbers stay integral (`long`), booleans stay booleans, binary attributes
  become BSON binary, and an absent attribute is omitted rather than written as
  `null`. Storage keys and filenames are carried through byte-for-byte.
- A missing tenant, storage key or timestamp is never defaulted: the item is
  quarantined with a reason code (`missing_tenant`, `missing_storage_key`,
  `missing_timestamp`, `invalid_timestamp`, `invalid_encoding`). Unknown
  attributes are preserved under `extras` and attributed in the recon report.
- Items whose storage key names no owning object are migrated and flagged with
  `orphaned_metadata: true` — never deleted, never re-parented.
- An empty namespace-filtered scan is a no-op: existing documents are left
  alone and the run exits zero.
- `files` carries a `$jsonSchema` validator (`validationAction: error`)
  requiring `tenant`, a string `storage_key` and a date `modified_at`, so a
  legacy string date is rejected with server error 121.

### What recon proves

`recon.py` recomputes every number from the stores themselves — document
counts, the checksum folded over `legacy_id|size_bytes|storage_key`, the
orphaned-metadata set, the per-page source counts, and the collection's
validator and indexes — then reruns the migration and recomputes them again to
observe idempotency. Planted-anomaly detection is compared as a set, so both a
missed and an unexpected anomaly fail the report. Anything the fixture cannot
demonstrate is listed in `unverified_paths` rather than being claimed.
