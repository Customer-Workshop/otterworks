# BDD Requirements — OTD-6 Storage quota warning banner

Traces every AC-ID from
[`user-story-requirement-understanding.md`](../otd-6-storage-quota-banner/user-story-requirement-understanding.md).
Jira: [OTD-6](https://cognition-partner-workshops.atlassian.net/browse/OTD-6).

Threshold under test: **90%** of the user's `quota_bytes` (per-tier).

---

## BDD-01: Banner appears when usage is at/above 90%
**Traces to:** AC-01 · **Category:** FUNC
**Given** the signed-in user's `storage_quotas` row has `used_bytes / quota_bytes >= 0.90`
**When** the user loads the app (any authenticated page)
**Then** a warning banner is displayed at the top of the content area.
### Testing Flow
1. Sign in as a user whose quota row is ≥ 90% used (e.g. free tier, 4.8 GB of 5 GB).
2. Load `/dashboard`.
3. Verify a warning banner reading "You're running low on storage" (or equivalent) is visible.

## BDD-02: Banner shows exactly at the 90% boundary
**Traces to:** AC-01, AC-05 · **Category:** FUNC
**Given** `used_bytes / quota_bytes == 0.90` exactly
**When** the app loads
**Then** the banner is displayed (threshold is inclusive: `>= 90`).
### Testing Flow
1. Set the quota row to used = 90% of quota. 2. Load the app. 3. Verify the banner shows.

## BDD-03: Dismissing hides the banner for the rest of the session
**Traces to:** AC-02 · **Category:** UI
**Given** the banner is shown
**When** the user clicks the dismiss (×) control
**Then** the banner disappears and stays hidden on subsequent navigations/reloads within the same browser session.
### Testing Flow
1. With the banner shown, click the dismiss control. 2. Verify it disappears.
3. Navigate to `/files`, then back to `/dashboard`; verify it stays hidden.
4. (Session scope) confirm dismissal is stored in `sessionStorage`, not `localStorage`.

## BDD-04: Banner is not shown below 90%
**Traces to:** AC-03 · **Category:** FUNC
**Given** the user's `used_bytes / quota_bytes < 0.90`
**When** the app loads
**Then** no warning banner is displayed.
### Testing Flow
1. Set the quota row below 90% (e.g. 1 GB of 5 GB). 2. Load the app. 3. Verify no banner.

## BDD-05: Banner action navigates to storage management
**Traces to:** AC-04 · **Category:** NAV
**Given** the banner is shown
**When** the user clicks its action button ("Manage storage")
**Then** the app navigates to the Files page (`/files`) where space can be freed.
### Testing Flow
1. With the banner shown, click "Manage storage". 2. Verify the URL is `/files`.

## BDD-06: Threshold respects each tier's quota_bytes
**Traces to:** AC-05 · **Category:** FUNC
**Given** two users on different tiers (free 5 GB, pro 200 GB)
**When** the 90% threshold is evaluated
**Then** it uses each row's `quota_bytes` — a pro user at 190 GB/200 GB (95%) sees the banner,
while a pro user at 150 GB/200 GB (75%) does not, even though 150 GB alone exceeds a free quota.
### Testing Flow
1. Pro user, used = 190 GB of 200 GB → banner shows.
2. Pro user, used = 150 GB of 200 GB → no banner (75%).

## BDD-07: Banner communicates usage and controls
**Traces to:** AC-06 · **Category:** UI
**Given** the banner is shown
**Then** it displays the usage percentage and used-of-quota, a dismiss control, and an action button.
### Testing Flow
1. Show the banner. 2. Verify it contains the percentage / "X of Y" text, a × control, and "Manage storage".

## BDD-08: Missing quota row / fetch error degrades gracefully
**Traces to:** AC-07 · **Category:** ERR
**Given** the user has no `storage_quotas` row (or the request fails)
**When** the app loads
**Then** the endpoint returns a free-tier default (0% used) / the UI simply shows no banner and does not crash.
### Testing Flow
1. Sign in as a brand-new user (no quota row). 2. Load the app. 3. Verify no banner and no error boundary.

## BDD-09: Endpoint requires auth and is scoped to the caller
**Traces to:** AC-08 · **Category:** RBAC
**Given** the quota endpoint `GET /api/v1/storage/quota`
**When** it is called without a valid token / with user A's token
**Then** unauthenticated calls are rejected (401) and authenticated calls return **only** the
caller's quota (resolved from the JWT `sub`), never another user's.
### Testing Flow
1. `curl` the endpoint without a token → 401.
2. `curl` with user A's token → row for user A only.

## BDD-10: Quota lookup is fast (single indexed read)
**Traces to:** AC-09 · **Category:** PERF
**Given** the endpoint
**When** called
**Then** it performs a single `user_id`-indexed lookup and returns promptly (no N+1 / no full scan).
### Testing Flow
1. Call the endpoint; confirm sub-interactive latency and that it is a unique-index lookup on `user_id`.

---

## AC → BDD Traceability Matrix

| AC-ID | Category | BDD scenarios | Executable coverage |
|---|---|---|---|
| AC-01 | FUNC | BDD-01, BDD-02 | Vitest `shouldShowStorageBanner`; Cucumber/Playwright banner-visible |
| AC-02 | UI | BDD-03 | Vitest (dismissed state); Cucumber/Playwright dismiss-persists |
| AC-03 | FUNC | BDD-04 | Vitest (<90%); Cucumber/Playwright hidden |
| AC-04 | NAV | BDD-05 | Playwright/Cucumber navigate-to-/files |
| AC-05 | FUNC | BDD-02, BDD-06 | Vitest (tier-independent %); RSpec (per-row quota_bytes) |
| AC-06 | UI | BDD-07 | Playwright/Cucumber banner content |
| AC-07 | ERR | BDD-08 | RSpec free-tier default; Playwright new-user no-banner |
| AC-08 | RBAC | BDD-09 | RSpec scoped-to-caller; gateway JWT-protected prefix |
| AC-09 | PERF | BDD-10 | RSpec single-lookup; unique index on `user_id` |

Coverage summary: **9/9 AC-IDs mapped**, zero unmapped. Categories FUNC, UI, NAV, ERR, RBAC, PERF all covered.

## Data Dependencies

- **Table:** `storage_quotas` (`user_id` UNIQUE, `quota_bytes`, `used_bytes`, `tier`).
- **Endpoint:** `GET /api/v1/storage/quota` (gateway → admin-service), JWT-protected, resolves caller via `X-User-ID` / JWT `sub`.
- **Component → service → endpoint:** `StorageQuotaBanner` → `storageApi.getQuota()` (`src/lib/api.ts`) → `apiClient GET /storage/quota` → gateway `/api/v1/storage` → admin-service `Api::V1::StorageController#quota` → Postgres `storage_quotas`.
- **Navigation target:** `/files` (Files page).
