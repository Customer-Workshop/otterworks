# 01 — Conventions

## Designated write target

| Field | Value | Status |
|---|---|---|
| Atlas project | `otterworks-demos` (`MONGODB_ATLAS_PROJECT_ID`) | FACT |
| Atlas cluster | `otterworks-demo`, MongoDB 8.0.29, unpaused; no cluster creation | VERIFIED |
| Migration database | `ow_tp_mongodb_032752` | PROPOSED |
| Quarantine database | `ow_tp_mongodb_032752_quarantine` | PROPOSED |
| Namespace field | `ns: "mongo_032752"` on every migrated document | PROPOSED |
| Scale | Existing M0 (512 MB) capacity; SCALE=demo data fits; no tier change | FACT |

Only the two databases above may be written. No grants, users, cluster changes, or writes
to any other database are allowed. Every collection must be registered in `04_progress.md`
before its first load. Loads are idempotent (drop-and-reload or upsert-by-key within this
run's own databases only).

## Secret names (referenced by name only, never by value)

| Tier | Purpose | Secret name |
|---|---|---|
| Assessment | Oracle source connection | fixture-local dev credential, DSN `localhost:52521/FREEPDB1`, user `ow_billing` |
| Migration | Atlas data plane | `MONGODB_ATLAS_URI` |
| Migration | Atlas control plane | `MONGODB_ATLAS_PUBLIC_KEY`, `MONGODB_ATLAS_PRIVATE_KEY`, `MONGODB_ATLAS_PROJECT_ID` |
| Cutover | Production repoint | Customer-held; never available to Devin |

## MongoDB and application conventions

- Collections and fields use lower snake_case; collection names are plural.
- Preserve stable natural business keys as `_id` where they are externally referenced;
  otherwise ObjectId per the approved mapping.
- Oracle `NUMBER` values follow the approved BSON int/long/Decimal128 mapping (02).
- Prefer driver-idiomatic bulk writes and aggregation pipelines over ported SQL shapes;
  app-side logic only where the approved mapping says a pipeline cannot preserve behavior.
- Quarantine records retain the source key, unit, reason class, and source watermark.

## Branch and PR conventions

- Run branch: `tp-run/mongodb-20260901T032752Z`, cut from `tech-partnerships`.
- `tech-partnerships` and `main` are never PR targets for this migration.
- Unit branches: `migrate/ow_billing/<wave>-<unit>`.
- ONE PR per unit — never a stack. Every unit PR targets the run branch and must pass
  `make tp-smoke`. Review budget: 2 rounds per PR.
- A unit is complete only when MERGED into the run branch with a green recon verdict.

## PR evidence contract

Every unit PR body is ~2,000 characters max, ordered:

1. Unverified paths / declared-unexercised (on top)
2. Decisions
3. Code
4. Evidence: rendered `recon.summary.md` (~30 lines); `result.json` and `report.md`
   linked as artifacts, never pasted. Cite recon mode, mapping version, tolerance version.
