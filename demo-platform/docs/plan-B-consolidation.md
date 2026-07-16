# Plan B — collapse to a single S3 bucket + single DynamoDB table (deferred)

Status: **DEFERRED.** We ship Scope **A** now (keep the existing shared set of managed
resources; enforce in-resource per-tenant namespacing). This document captures the future
consolidation so it can be executed as a separate workstream when prioritized.

## Goal
Reduce the shared data plane to exactly **one S3 bucket** and **one DynamoDB table**, with all
tenant + data-domain separation expressed as *keys inside* those single resources.

## Current (Scope A) — multiple shared resources, tenant-prefixed
- S3 buckets: `otterworks-files-dev`, `otterworks-audit-archive-dev`, `otterworks-data-lake-dev`, `otterworks-analytics-dev-*`
- DynamoDB tables: `otterworks-file-metadata-dev`, `-file-shares-dev`, `-file-versions-dev`, `-folders-dev`, `-notifications-dev`, `-audit-events-dev`
- Each is shared across tenants; isolation is by key prefix / owner partition.

## Target (Scope B)
- **1 bucket** `otterworks-shared-dev`, key layout `t/<tenant>/<domain>/<...>` (domain = files|audit|datalake|analytics).
- **1 table** `otterworks-shared-dev`, single-table design:
  - `PK = T#<tenant>#<domain>#<entity>` , `SK = <id>` (+ GSIs per access pattern currently served by the separate tables).

## Why it's a large refactor (not free)
- All 11 services hard-reference their specific bucket/table names via config/IRSA. Each must switch to the single resource + compose the tenant/domain-prefixed key, and their data models must fold into the single-table GSIs.
- IAM/IRSA policies narrow from per-table ARNs to one table ARN + `dynamodb:LeadingKeys` condition on `T#<tenant>#...` (this actually *improves* isolation).
- Data migration for the golden app's existing data; reaper key-scan logic changes from N tables to 1.

## Migration approach (when executed)
1. Introduce the single bucket/table alongside the old ones.
2. Add a config flag per service (`STORAGE_MODE=split|single`); implement the single-table key composition behind it.
3. Backfill/migrate golden data; dual-write during cutover.
4. Flip tenants to `single`, validate isolation (`LeadingKeys`), then flip golden.
5. Delete the old buckets/tables; update reaper + IaC.

## Isolation upgrade this unlocks (ties to Tier B)
With a single table + `dynamodb:LeadingKeys` and a single bucket + prefix-scoped IRSA, each
tenant's pods can be given credentials that can *only* touch their own `T#<tenant>#...` keys /
`t/<tenant>/*` objects — true per-tenant IAM isolation (Tier B) without per-tenant tables.
