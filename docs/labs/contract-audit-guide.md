# Contract Audit Lab Guide

This guide walks you through auditing the API and event contracts across OtterWorks services. The goal is to find places where a service's actual behavior drifts from its published specification, then decide whether to fix the spec or the code.

## Where to Find Specifications

### OpenAPI Specs

API specifications live in `shared/openapi/`. Each service that exposes an HTTP API should have a corresponding OpenAPI document here. Use these as the source of truth for request/response shapes, status codes, and field naming conventions.

### Event Schemas

Event schemas live in `shared/events/schemas/`. These are JSON Schema files describing the events each service publishes to the message bus:

| Schema File                  | Service(s)              | Event Types                                                    |
|------------------------------|-------------------------|----------------------------------------------------------------|
| `document-events.json`       | document-service        | `document_created`, `document_edited`, `comment_added`         |
| `file-events.json`           | file-service            | `file_uploaded`, `file_shared`, `file_deleted`                 |
| `notification-events.json`   | notification-service    | `notification_sent`, `notification_read`, `notification_failed`|
| `audit-events.json`          | audit-service           | `entity_created`, `entity_updated`, `entity_deleted`, `access_granted`, `access_revoked` |
| `collaboration-events.json`  | collab-service          | `user_joined`, `user_left`, `cursor_moved`, `selection_changed`|

## How to Check for Contract Drift

1. **Pick a schema** from `shared/events/schemas/`.
2. **Read the schema** and note the field names, required fields, and types.
3. **Find the service code** that publishes events of that type. Look for event construction or emission logic in the service source.
4. **Compare** the field names and structure in the code against the schema. Pay attention to:
   - Field naming conventions (camelCase vs. snake_case)
   - Required fields that might be conditionally omitted
   - Enum values that differ between spec and implementation
   - Fields present in code but missing from the schema (or vice versa)

## Known Drift to Investigate

These are areas where the schemas and service implementations are known to be out of sync. Try to locate the exact source of each discrepancy and propose a fix.

### 1. Notification Service -- Field Naming Mismatch

The `notification-events.json` schema defines fields using camelCase (e.g., `notificationId`, `userId`, `resourceId`). However, the notification-service actually publishes events using snake_case field names (e.g., `notification_id`, `user_id`, `resource_id`).

**What to try:**
- Open `shared/events/schemas/notification-events.json` and note the camelCase field names.
- Search the notification-service source code for event publishing logic.
- Compare the field names used in the code against the schema.
- Decide: should the schema be updated to snake_case, or should the service code be updated to camelCase? Consider what convention the other schemas use and aim for consistency.

### 2. Audit Service -- Missing Required Field

The `audit-events.json` schema marks `timestamp` as a required field on all event types. However, when the audit-service processes batch operations, it sometimes omits the `timestamp` field from individual events within the batch, relying on a single batch-level timestamp instead.

**What to try:**
- Open `shared/events/schemas/audit-events.json` and confirm `timestamp` is in the `required` array for each event type.
- Search the audit-service source for batch event processing logic.
- Identify where `timestamp` gets omitted on individual events.
- Decide: should the schema relax `timestamp` to optional, or should the code always include it? Consider downstream consumers that may depend on per-event timestamps.

## Running the Audit

Use the following approach for a systematic audit:

```bash
# List all event schemas
ls shared/events/schemas/

# Search a service for event publishing code
grep -r "eventType" services/<service-name>/

# Search for field name patterns
grep -rn "notification_id\|notificationId" services/notification-service/

# Run tests with coverage to see which code paths are exercised
make test-coverage
```

## What "Done" Looks Like

The audit is complete when:

- Every event schema in `shared/events/schemas/` has been compared against the service that publishes those events
- All field name mismatches have been identified and resolved (either the schema or the code was updated for consistency)
- All required-field discrepancies have been identified and a decision has been documented (fix the schema or fix the code)
- The resolution is consistent with the conventions used by the rest of the platform (check existing schemas for the naming pattern)
- Tests pass after any changes: run `make test` or the per-service test command

## Tips

- The existing `document-events.json` and `file-events.json` schemas use camelCase consistently. Use this as a reference for the expected convention.
- Event schemas follow JSON Schema draft-07. Each event type is defined under `definitions` with explicit `required` arrays and `properties`.
- When in doubt about whether to change the spec or the code, prefer changing whichever has fewer downstream dependencies.
- Run `make test-coverage` to see which services have tests covering their event publishing logic.
