# Playbook: Generate Synthetic Test Data from a GitHub Issue

> **Facilitator / author:** this file is the source for a **Devin Playbook**.
> Copy its contents into your Devin organization (Settings → Playbooks → *Create
> a new Playbook*) so sessions can invoke it as `!generate-testdata`. See
> [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks).

## Overview

Use this playbook when a GitHub Issue describes a **user story with acceptance
criteria** that requires synthetic test data in a lower environment (dev, QA,
staging, load-test). Devin reads the issue, introspects the target database
schema, generates Python data-generation scripts, loads the data, and **proves**
correctness through a programmatic validation harness — not by eyeballing.

The guiding principle: **every generated dataset must pass the same validation
harness that would catch a production data-quality bug.** If the harness goes
green, the data is trustworthy for testing; if it goes red, the generator is
wrong and must be fixed before the PR ships.

## Required from user

- **The GitHub Issue** — number or URL. Must contain a user story and acceptance
  criteria (row counts, entity relationships, activity patterns, distribution
  requirements).
- **The namespace** — the isolated schema suffix for this run (e.g., `dev`,
  `qa1`, `loadtest`). Defaults to `dev` if not specified.
- **The target repo** — the application repo with the database schema and the
  validation harness (e.g., `otterworks`).

## Procedure

1. **Read the GitHub Issue.** Extract:
   - The user story (who needs the data, what for)
   - Every acceptance criterion (row counts, column distributions, relationship
     cardinality, temporal patterns, activity volumes)
   - Any explicit constraints (e.g., "emails must be unique", "20% of users
     should be suspended")

2. **Introspect the database schema.** Use the repo's migration files, schema
   definitions, and existing seed scripts to understand:
   - Table structures, column types, constraints
   - Foreign-key relationships and referential integrity rules
   - Enum/check constraints and valid value sets
   - Business rules (e.g., `used_bytes <= quota_bytes`)

3. **Generate the criteria file.** Write a `criteria.json` that encodes the
   acceptance criteria as machine-checkable constraints:
   ```json
   {
     "users": {"min_rows": 500, "required_columns": ["email", "display_name"]},
     "audit_logs": {"min_rows": 2000, "enum_constraints": {"action": ["create", "update", "delete"]}}
   }
   ```

4. **Generate the data-generation script.** Write a Python script at
   `testdata/generated/<ns>/generate.py` that:
   - Creates the namespaced schema (`make testdata-setup-schema NS=<ns>`)
   - Generates synthetic data respecting ALL schema constraints
   - Respects temporal causality (resources exist before events reference them)
   - Satisfies the acceptance criteria (counts, distributions, relationships)
   - Uses deterministic seeds for reproducibility
   - Is idempotent (safe to re-run)

5. **Optionally generate a simulation script.** If the issue requests "activity
   simulation" (realistic usage patterns over time), write
   `testdata/generated/<ns>/simulate.py` that:
   - Creates time-series activity (logins, file operations, document edits)
   - Respects business-hours distributions if specified
   - Generates audit trails with causal ordering

6. **Run the generator.** Execute the script to load data into the namespace.

7. **Run the validation harness.** Execute `make testdata-validate NS=<ns>` with
   the criteria file. The harness checks:
   - Schema conformance (FK, NOT NULL, types, uniqueness)
   - Temporal consistency (no impossible causal orderings)
   - Acceptance-criteria coverage (row counts, distributions, enums)
   - Business rules (quota limits, valid state transitions)

8. **Fix failures and re-run.** If the harness reports FAIL:
   - Read the failure detail (which check, what was expected vs actual)
   - Fix the generator (adjust data logic, ordering, distributions)
   - Drop and recreate the namespace (`make testdata-clean NS=<ns>`)
   - Re-run steps 6–7 until all checks PASS

9. **Open a PR** with:
   - The generation script(s)
   - The criteria file
   - The green validation report (in the PR description)
   - A reference to the source GitHub Issue

## Specifications (postconditions)

A run is complete when:

- [ ] All acceptance criteria from the GitHub Issue are encoded in `criteria.json`
- [ ] The generation script produces data that passes `make testdata-validate`
- [ ] No FK violations, temporal inconsistencies, or enum violations exist
- [ ] Row counts match the issue's requirements (within ±5% tolerance if ranges)
- [ ] The data is isolated in its own namespace (no writes to `public` or other schemas)
- [ ] The generation script is deterministic (same seed → same output)
- [ ] A PR is opened with the scripts, criteria, and validation report

## Worked example: the temporal-consistency bug

When generating test data for a "file-sharing activity audit" user story, a
natural approach generates audit-log entries and admin users independently, then
assigns `actor_id` values randomly from the user pool. This produces entries
where `audit_logs.created_at` is **earlier** than the referenced
`admin_users.created_at` — the audit log claims a user performed an action
before their account existed.

```
make testdata-validate NS=dev
#   temporal_consistency:audit_logs.created_at<admin_users.created_at | FAIL |
#     12 entries reference resources created after the event timestamp
```

The fix: generate users first with a `created_at` window, then generate audit
logs only within each user's lifetime (`user.created_at <= log.created_at <=
now()`). Re-run:

```
make testdata-validate NS=dev
#   temporal_consistency:audit_logs.created_at<admin_users.created_at | PASS |
#     all events respect causal ordering
```

The point: "looks reasonable" review would ship temporally impossible data that
breaks realistic test scenarios (e.g., "show me audit logs from a user's first
week" returns nothing because the user didn't exist yet). The harness caught it.

## Advice

- Start generation with parent tables (users, admin_users) before child tables
  (roles, quotas, audit_logs) to naturally satisfy FK constraints.
- Use `faker` for realistic names/emails but ensure uniqueness with a counter
  suffix if needed.
- For temporal data, establish a time window (`created_at` range) per entity and
  derive all downstream timestamps from within that window.
- Prefer batch inserts (`execute_values`) over row-by-row for performance with
  large datasets.
- Include a `--dry-run` flag in generators for debugging without DB writes.
- Always use `ON CONFLICT DO NOTHING` or `INSERT ... ON CONFLICT UPDATE` for
  idempotency.

## Forbidden actions

- Do **not** write to the `public` schema or any schema not prefixed with
  `otterworks_<ns>`.
- Do **not** hardcode credentials in scripts — read from environment variables.
- Do **not** generate real PII (use synthetic/fake data generators only).
- Do **not** skip the validation step — a PR without a green validation report
  is not ready.
- Do **not** mark the issue as done until the harness passes.
