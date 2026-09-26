# 01_conventions

## Branch topology (engagement restriction)
- Base branch: `origin/tech-partnerships` (immutable legacy before-state). Never merge into it or into `main`.
- Run branch: `tp-run/mongodb-20260926T164803Z-rt-offline`, cut with
  `git checkout -b tp-run/mongodb-$(date -u +%Y%m%dT%H%M%SZ)-rt-offline origin/tech-partnerships` and pushed.
- All `.migration/` state lives on the run branch. Every unit PR, wave-close PR, coexistence PR and cutover-document PR targets the run branch.
- **Only `tech-partnerships` and this run branch exist for this engagement.** No other branch or PR of the repo (including `tech-partnerships-solutions` and any closed PR) is read, fetched, checked out, diffed or searched. This is a user-set restriction recorded at intake; children inherit it.

## Unit PR conventions
- Branch: `tp-run/mongodb-20260926T164803Z-rt-offline--unit/<unit_id>` off the run branch; PR base = run branch.
- PR title: `[mongo][<wave>][<unit_id>] <object> → <collection>`.
- PR body must link the recon artifact, the fixture manifest, and the `05_decisions.md` rows cited by the mapping.
- Merge authority: recon harness verdict only, and only `live`/`snapshot` runs against a migration cluster are merge evidence. This engagement produces `fixture`/`local` evidence only, so `auto_merge: false` everywhere and **no unit PR is merged**. PASS PRs stay open, labelled "awaiting migration-cluster recon".
- Reviewer: none (self-verify only).

## Write targets
- Declared migration database: `ow_billing_migration` on `MONGO_LOCAL_URI` (local `mongo:7`). Listed in `allowed_targets.json`; nothing else is ever written.
- Each unit writes only to the collections named in its wave-manifest brief. Children never edit `.migration/`.
- Every offline command runs as `env -u MONGODB_ATLAS_URI ...` (offline guard requirement).

## Source
- Read-only, always. Oracle DDL and PL/SQL under `services/legacy-billing/db/oracle/` are never modified. No source connectivity in this engagement; a local Oracle Free container seeded from the repo DDL is the fixture.
- Source query concurrency cap: 1 (applies to the fixture too).

## Naming
- Collections: snake_case of the Oracle table (`CUSTOMER_MASTER` → `customer_master`) unless `03_mapping_spec.json` says otherwise.
- Fields: snake_case; Oracle `NUMBER(p,s)` with scale or p>18 → Decimal128; `DATE`/`TIMESTAMP` → BSON date; `CHAR(n)` → trimmed string (Oracle profile).
- Unit ids: `u-<NN>-<object>`; waves `wave-<N>`.

## Secrets
- By name only. No secret values in artifacts, PR bodies, logs, chat.
