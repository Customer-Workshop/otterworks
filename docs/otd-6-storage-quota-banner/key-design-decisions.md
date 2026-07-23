# OTD-6 — Storage quota warning banner: Key Design Decisions

## Real-data data flow (no mocks)

```
client-app  ──GET /api/v1/storage/quota──▶  API Gateway (:8080)
                                             │  injects X-User-ID (JWT sub)
                                             ▼
                                          admin-service (Rails, owns storage_quotas)
                                             │  StorageQuota.find_by(user_id: current_user_id)
                                             ▼
                                          PostgreSQL  storage_quotas
```

The banner renders entirely from this real endpoint. No hardcoded quota totals remain.

## Decisions

1. **New user-facing endpoint in admin-service (owner of `storage_quotas`).**
   `GET /api/v1/storage/quota` → `Api::V1::StorageController#quota`. It resolves the current
   user from `request.env['jwt.user_id']` (set by the existing `JwtAuthenticator`, which the
   gateway feeds via the forwarded `Authorization`/`X-User-ID`). Returns the user's quota
   using the existing `StorageQuotaSerializer` fields (`quota_bytes`, `used_bytes`, `tier`,
   `usage_percentage`, `over_quota`, `remaining_bytes`). *Rejected alternative:* putting quota
   in file-service (Rust) — it does not own the table; cross-service DB reads break ownership.

2. **Gateway route.** Add `"/api/v1/storage": AdminServiceURL` to
   `ServiceRoutes()`. This automatically makes the prefix JWT-protected (AC-08) and
   `X-User-ID`-injected, consistent with every other route. No new env var needed.

3. **Graceful default when no quota row exists (AC-07).** Brand-new users have no
   `storage_quotas` row. The endpoint returns a **non-persisted** free-tier default
   (`quota_bytes` = `TIER_LIMITS['free']`, `used_bytes` = 0, `tier` = `free`,
   `usage_percentage` = 0). Result: no banner for such users (0% < 90%) and no error. We do
   not silently write rows on a GET.

4. **Threshold = 90%, evaluated against `quota_bytes` (AC-05).** `usage_percentage` is
   computed server-side by the model as `used_bytes / quota_bytes`. Because `quota_bytes` is
   per-tier, the same 90% rule respects each tier's limit (free 5 GB, pro 200 GB, …). The
   frontend shows the banner when `usagePercentage >= 90`. The threshold constant lives in a
   single pure helper (`shouldShowStorageBanner`) that is unit-tested.

5. **Frontend banner.** New `StorageQuotaBanner` rendered in `AppShell` (so it appears on app
   load across authenticated pages). It uses react-query to call a new
   `storageApi.getQuota()`. Shows usage % and used-of-quota (AC-06). It respects a
   per-session dismissal (AC-02) stored in `sessionStorage` (cleared when the tab session
   ends — exactly "remainder of the session"). The action button ("Manage storage")
   navigates to `/files` (AC-04) — the place a user frees space; OtterWorks has no separate
   "storage management" page, and Files is where deletion/cleanup happens.

6. **Remove the hardcoded 10 GB mock (no-mock-data rule).** `storageApi.getUsage()` now
   derives `total` and `used` from the real quota endpoint (falling back to file-derived
   counts only for `fileCount`/`documentCount`), so the dashboard and the banner share one
   real source of truth.

7. **Infra fix to bring up the stack.** auth-service gets its own Flyway history table
   (`flyway_schema_history_auth`) so it no longer collides with analytics-service's default
   history. Minimal, idiomatic Spring Boot config; required for login and thus for
   browser-verifying the feature. Kept as a separate, clearly-labeled commit.

## "Storage management" target (AC-04)

`/files` — the client-app has no dedicated storage-management route; Files is the surface
where users delete/clean up to free space. Documented here as the resolved interpretation.

## Test strategy (fail-before, pass-after)

- **admin-service RSpec** (`spec/controllers/api/v1/storage_controller_spec.rb`): current
  user's quota returned; free-tier default when no row; percentage/over-quota correctness;
  isolation to the caller's `user_id`.
- **client-app Vitest** (`src/lib/storage-quota.test.ts`): `shouldShowStorageBanner`
  threshold at/above/below 90%, dismissed state, and tier-independent behavior (AC-05).
- **Cucumber BDD** (`bdd/features/storage-quota.feature`) + **Playwright e2e**
  (`e2e/storage-quota.spec.ts`): banner visible ≥90%, dismiss persists in-session, action
  navigates to Files, hidden <90% (driven via a stubbed `/api/v1/storage/quota` route so the
  UI behavior is deterministic in CI-less headless runs; live real-data behavior is verified
  in the browser recording).

## Out of scope / untouched

- Planted bug `admin-service config/environments/production.rb` — left as-is.
- No new DB migration (table already exists); no changes to admin dashboard quota flows.
