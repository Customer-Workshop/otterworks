# Golden Reference Synthetic Dataset

This directory generates the **golden reference dataset** for OtterWorks — a
large, realistic, internally-consistent snapshot of a busy company. It is loaded
**once** into the permanent shared reference database and used as the starting
state for demos.

Unlike the per-session namespaces used for ephemeral test-data runs, this dataset
is intended to be durable and reproducible. The generator is fully deterministic
(fixed random seed), so re-running it produces the same structural dataset every
time.

## What it produces

| Table | Approx. rows | Notes |
|-------|-------------:|-------|
| `users` | 500 | unique emails, realistic name/timestamp distribution over ~18 months |
| `user_settings` | 500 | 1:1 with `users` |
| `user_roles` | ~500–1000 | every user has `USER`; some also have one of `EDITOR`/`ADMIN`/`OWNER` (1–2 roles each) |
| `refresh_tokens` | ~350 | `expires_at` strictly after `created_at` (active / expired / revoked mix) |
| `admin_users` | 25 | unique emails; roles `viewer`/`editor`/`admin`/`super_admin`; statuses `active`/`suspended`/`deactivated` |
| `storage_quotas` | 25 | one per admin user; tier `free`/`basic`/`pro`/`enterprise`; `used_bytes <= quota_bytes` |
| `audit_logs` | 5000 | `created_at` always at/after the referenced admin user's `created_at` (~8% are actor-less system events) |
| `feature_flags` | 30 | unique names |
| `announcements` | 20 | valid severity/status |
| `incidents` | 50 | valid severity/status; ~30% linked to a Devin session |
| `system_configs` | 40 | unique keys |

All enum values, foreign keys, uniqueness, temporal ordering and business rules
enforced by `testdata/harness/validate.py` are respected.

## Regenerate & validate (local Postgres only)

> Do **not** load this into any remote/live database. Loading into the permanent
> shared DB is handled separately. Use a local Postgres only for validation.

```bash
# 1. Bring up local Postgres (repo infra, or any postgres:16 container)
make infra-up
export DB_HOST=localhost DB_PORT=5432 DB_NAME=otterworks \
       DB_USER=otterworks DB_PASSWORD=otterworks_dev

# 2. Create the namespaced schema
make testdata-setup-schema NS=golden

# 3. Generate the data (deterministic)
python testdata/generated/golden/generate.py --ns golden

# 4. Validate — standard suite + golden acceptance criteria
make testdata-validate NS=golden CRITERIA=testdata/generated/golden/criteria.json

# 5. (optional) Tear down
make testdata-clean NS=golden
```

## Reproducibility

- IDs are generated with `uuid5` from a fixed namespace, so cross-table foreign
  keys always resolve and are stable across runs.
- All random choices flow from a single `random.Random(seed)` seeded with a fixed
  default (`--seed`, default `20240117`).
- Timestamps are expressed relative to the run time (`now()`), so the dataset
  always spans the most recent ~18 months while keeping every temporal invariant.

## Loading into the permanent shared database

The generator writes into schema `otterworks_<ns>`. To load into the permanent
shared reference database, point the `DB_*` environment variables at that
database and run steps 2–4 above with the desired namespace. This step is
performed out-of-band by an operator, not by the validation flow here.
