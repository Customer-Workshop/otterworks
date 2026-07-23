# OTD-6 — Storage Quota Warning Banner — Test Report

**Result: PASS.** All 5 acceptance criteria verified live in the browser at `http://localhost:3000`
with real data flowing `client-app → API Gateway (:8080) → admin-service → Postgres storage_quotas`.
No mock data. Automated tests (Vitest, RSpec, Go, Cucumber, Playwright) and CI are green.

- PR: https://github.com/Cognition-Partner-Workshops/otterworks/pull/600
- Jira: https://cognition-partner-workshops.atlassian.net/browse/OTD-6
- Recording: attached to the PR and the session (covers all AC-IDs).

Each browser check drove real quota state by updating the signed-in user's row in
`storage_quotas` and reloading, then confirming the endpoint response through the gateway.

---

## Automated tests

| Suite | Command | Result |
|-------|---------|--------|
| client-app unit | `npm test` (Vitest) | 8 passed |
| client-app lint | `npm run lint` | 0 errors (1 pre-existing warning in unrelated `file-detail.tsx`) |
| client-app build | `npm run build` | passed |
| client-app BDD | `bdd/features/storage-quota.feature` (Cucumber) | scenarios for AC-1..AC-5 |
| client-app e2e | `e2e/storage-quota.spec.ts` (Playwright) | banner show/hide/dismiss/navigate |
| admin-service | `bundle exec rspec` | 124 examples, 0 failures |
| api-gateway | `go vet ./...`, `go test ./...`, `go build ./cmd/server` | passed |
| auth-service | `gradle check --no-daemon` | BUILD SUCCESSFUL |

Real endpoint through the gateway (JWT-resolved current user):

```
GET /api/v1/storage/quota
{
  "user_id": "…", "quota_bytes": 5368709120, "used_bytes": 5153960755,
  "tier": "free", "usage_percentage": 96.0, "over_quota": false,
  "remaining_bytes": 214748365
}
```

---

## AC-1 — Usage ≥ 90% shows the warning banner on load

**Given** the user's real `storage_quotas` row is 96% full **When** the app loads
**Then** the warning banner is displayed with the percentage and used-of-quota.

![AC-1 dashboard with banner at 96%](https://partner-workshops.devinenterprise.com/attachments/676d7d14-3f4f-442e-971f-0f153c202790/ss_7207738e.png)

![AC-1 banner detail](https://partner-workshops.devinenterprise.com/attachments/0a42be3f-b18b-4571-bcf3-d29ba09d1357/ss_zoom_d686992b.png)

Banner text: *"You're running low on storage — You've used 96% of your storage (4.8 GB of 5 GB)."*
The dashboard storage card also shows the real `4.8 GB of 5 GB` (the previous hardcoded 10 GB is gone). **PASS**

---

## AC-4 — Banner action goes to storage management

**Given** the banner is shown **When** the user clicks "Manage storage" **Then** they land on `/files`
(the surface where files are deleted to free space; the app has no separate storage-management route).

![AC-4 navigated to /files, banner still visible](https://partner-workshops.devinenterprise.com/attachments/4cb21368-39af-4fc7-b103-e727753d729f/ss_eca7ca54.png)

URL is `localhost:3000/files`. **PASS**

---

## AC-5 — Threshold respects the tier's `quota_bytes`

The threshold is `used_bytes / quota_bytes`, so it is intrinsically per-tier. Verified with a
**pro** tier (200 GB quota):

**95% (190 GB of 200 GB) → banner shown:**

![AC-5 pro tier 95% shows banner](https://partner-workshops.devinenterprise.com/attachments/d6f6db26-4183-4a6d-bcf0-d644969c9ea9/ss_zoom_8a1d44ed.png)

**75% (150 GB of 200 GB) → banner hidden** — even though 150 GB dwarfs a free-tier 5 GB quota,
it is only 75% of the pro quota, so no banner:

![AC-5/AC-3 pro tier 75% no banner](https://partner-workshops.devinenterprise.com/attachments/8d4931b3-67d8-4cc2-9aa6-60e27fcf576d/ss_575249cc.png)

**PASS**

---

## AC-3 — Usage below 90% shows no banner

Covered by the pro-tier 75% screenshot above: at `usage_percentage = 75` the app loads with no
warning banner (dashboard/Files render normally). **PASS**

---

## AC-2 — Dismissal persists for the session

**Given** the banner is shown (row restored to 96%) **When** the user dismisses it and then does a
full page reload **Then** it stays hidden for the rest of the session (dismissal stored in
`sessionStorage`), even though usage is still 96%.

![AC-2 after dismiss + reload, still 96% but no banner](https://partner-workshops.devinenterprise.com/attachments/de5be37e-ce2a-4415-8a5c-12047a99c2a0/ss_zoom_02f2f3c3.png)

**PASS**

---

## Demo recording

![OTD-6 banner demo](https://partner-workshops.devinenterprise.com/attachments/9bb74a6b-5566-428c-a728-9d7812a585c6/otd6-banner-demo.webp)

---

## Review findings (Devin Review)

1. **[BUG] Dashboard counts vanish if quota lookup fails** — **Fixed** (`626d7dc4`): `getUsage`
   now fetches file/document counts on their own and wraps `getQuota()` in `try/catch`, so an
   admin-service outage degrades `used`/`total` to 0 while counts still render.
2. **[FLAG] `used` reflects the usage-rollup value, not a live file-size sum** — intended: the
   canonical source is `storage_quotas.used_bytes` (real data, per the no-mock rule).
3. **[FLAG] Flyway re-baseline risk on pre-migrated DBs** — pre-existing `baseline-on-migrate`
   config; in the actual scenario auth never successfully migrated into the shared table
   (it crash-looped on checksum mismatch) and demo tenants use fresh DBs, so there is no prior
   auth history to conflict.
4. **[FLAG] Quota fetched twice on the dashboard** — minor, non-correctness; banner and dashboard
   use distinct react-query keys.
