# OTD-6 — Storage quota warning banner: Requirement Understanding

**Jira:** [OTD-6](https://cognition-partner-workshops.atlassian.net/browse/OTD-6) · Project OTD (OtterWorks-Team-Demos) · Label `otterworks-demo`

> This is an autonomous demo run. The plan below was self-generated and self-approved
> per the run instructions (no human approval gate), after grounding every referenced
> table/column/route against the live local stack.

## Story (verbatim)

> As a user, I want a banner when I exceed 90% of my storage quota, so that I can free
> space before hitting the limit.

**Acceptance Criteria (verbatim):**
1. Given my usage is at or above 90% of quota, When I load the app, Then a warning banner is displayed.
2. Given the banner is shown, When I dismiss it, Then it stays hidden for the remainder of the session.
3. Given my usage drops below 90%, When I load the app, Then the banner is not shown.
4. Given the banner is shown, When I click its action, Then I am taken to storage management.
5. Given different subscription tiers, When the threshold is evaluated, Then it respects the tier's quota_bytes.

## Actors & scope

- **Actor:** an authenticated OtterWorks web-app (client-app) user.
- **Scope:** user-facing warning banner in the React client-app, backed by the user's real
  storage quota served from the owning microservice and PostgreSQL. No change to admin flows.

## Grounding against the live stack (verified)

Verified against the running golden stack (`make infra-up` + `make up seed=1`) and live Postgres.

### Data — `storage_quotas` (owner: admin-service, Rails)
`\d storage_quotas` on the live `otterworks` DB:

| column | type | notes |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` |
| `user_id` | uuid | **UNIQUE** (`index_storage_quotas_on_user_id`) |
| `quota_bytes` | bigint | per-row/per-tier limit, default 5 GiB |
| `used_bytes` | bigint | canonical usage (maintained by the usage-rollup batch) |
| `tier` | varchar | `free` \| `basic` \| `pro` \| `enterprise` (indexed) |
| `created_at` / `updated_at` | timestamp | |

`StorageQuota` model already exposes `usage_percentage`, `over_quota?`, `remaining_bytes`
and `TIER_LIMITS` (free 5 GB, basic 50 GB, pro 200 GB, enterprise 1 TB). The 90% threshold
is therefore evaluated as `used_bytes / quota_bytes` — **quota_bytes is per-tier**, so the
threshold intrinsically respects each tier (AC-5).

### Routing / auth (verified)
- API Gateway (Go/Chi) proxies `/api/v1/*` prefixes to owning services and injects
  `X-User-ID` (from the JWT `sub`) on every proxied request; every mounted prefix is
  JWT-protected. **There is currently no user-facing quota route** — only admin-only
  `GET/PUT /api/v1/admin/quotas/:user_id`.
- admin-service `JwtAuthenticator` decodes the same shared `JWT_SECRET` (HS256/HS384) and
  sets `request.env['jwt.user_id']`, so a user-facing endpoint can resolve "me" from the token.

### Frontend (verified)
- Client-app is React + Vite + react-router (pages in `src/pages`, layout `components/layout/app-shell.tsx`).
- `storageApi.getUsage()` in `src/lib/api.ts` currently **hardcodes `total: 10 GB`** and
  computes `used` by paginating files — a mock-ish default to be replaced with the real quota.
- `apiClient` auto-transforms snake_case → camelCase, so the backend may return snake_case.

### Discrepancy found & resolved (infra gap, not OTD-6)
On a clean `make up`, **auth-service crash-loops**: it and analytics-service share the DB
and the default `flyway_schema_history` table, both shipping a version-1 migration → checksum
mismatch, so the `users` table is never created and login is broken. This is a genuine wiring
gap (not the planted admin-service `production.rb` bug) and is not exercised by CI. Fixed
minimally by giving auth-service its own history table (`spring.flyway.table:
flyway_schema_history_auth`) so both services migrate cleanly. Required to bring up the real
stack for browser verification.

## AC Traceability Matrix (with derived ACs for full category coverage)

| AC-ID | Category | Requirement | Source |
|---|---|---|---|
| **AC-01** | FUNC | Usage ≥ 90% of quota ⇒ warning banner shown on app load | Story AC-1 |
| **AC-02** | UI | Dismissing the banner hides it for the remainder of the session | Story AC-2 |
| **AC-03** | FUNC | Usage < 90% ⇒ banner not shown on app load | Story AC-3 |
| **AC-04** | NAV | Banner action navigates to storage management (`/files`) | Story AC-4 |
| **AC-05** | FUNC | Threshold evaluated against the tier's `quota_bytes` (per-tier) | Story AC-5 |
| **AC-06** | UI | Banner communicates usage (percentage + used-of-quota) and offers dismiss + action controls | Derived (UI completeness) |
| **AC-07** | ERR | Missing quota row / fetch failure degrades gracefully (no crash, banner hidden) | Derived (error handling) |
| **AC-08** | RBAC | Quota endpoint requires auth and returns the **current** user's quota (from JWT `sub`), never another user's | Derived (multi-tenant safety) |
| **AC-09** | PERF | Quota lookup is a single indexed `user_id` read; endpoint responds well under interactive latency | Derived (performance) |

Coverage: 9/9 AC-IDs mapped, all six categories (FUNC, UI, NAV, ERR, RBAC, PERF) represented.
Zero unmapped ACs.
