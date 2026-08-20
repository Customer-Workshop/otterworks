# Wave 3 — local validation report

Verdict: **GREEN**. The decomposed portal stack comes up clean on localhost, all three parity
suites replay identically against the pinned pre-retirement monolith, every affected test suite
passes, and the announcements slice works end to end in a browser with its data landing in the
extracted service's database. The dependency gate is red, as it already was before this
migration; the migration did not change that picture except to add one more measured and clean
reactor (`portal`).

Everything below was run on `demo/legacy-portal-migration` at commit `37fdf9a9`.

## Environment

| Component | Version |
|---|---|
| OS | Ubuntu 22.04 (x86_64) |
| Docker / Compose | 27.4.1 / v2.32.1 |
| Ambient JDK | OpenJDK 21.0.11 (JDK 8/11/17/21 all installed) |
| Maven | 3.9.9 (via each module's `./mvnw`) |
| Node / npm | v22.23.2 / 10.9.8 |
| Postgres (all three databases) | `postgres:16` |
| Parity reference image | `otterworks/legacy-portal:pre-retirement-c07b93bc`, built locally from commit `c07b93bc` |

## 1. Stack bring-up

```bash
make portal-up NS=dev
```

All containers reported healthy by Compose's `--wait`:

| Container | Image | State |
|---|---|---|
| `otterworks-portal-dev-legacy-portal-1` | built from `services/legacy-portal` | Up (healthy) |
| `otterworks-portal-dev-announcements-service-1` | built from `services/portal` | Up (healthy) |
| `otterworks-portal-dev-announcements-db-1` | `postgres:16` | Up (healthy) |
| `otterworks-portal-dev-user-preferences-service-1` | built from `services/portal` | Up (healthy) |
| `otterworks-portal-dev-user-preferences-db-1` | `postgres:16` | Up (healthy) |
| `otterworks-portal-dev-feedback-service-1` | built from `services/portal` | Up (healthy) |
| `otterworks-portal-dev-feedback-db-1` | `postgres:16` | Up (healthy) |

Health identity, confirming which process serves each context:

```
8095 {"status":"UP","service":"legacy-portal","banner":"OtterWorks Portal (on-prem) - contact portal-support@otterworks.example"}
8101 {"status":"UP","service":"announcements-service"}
8102 {"status":"UP","service":"user-preferences-service"}
8103 {"status":"UP","service":"feedback-service"}
```

The shell serves nothing else — `GET /api/announcements`, `/api/preferences` and `/api/feedback`
on `:8095` all return `404`, while `/actuator/health` returns `200`.

Frontend: `frontend/client-app` on the Vite dev server (`npm run dev`, port 3000), proxying
`/announcements-api` → `http://localhost:8101` per `docs/migration/traffic-routing.md`.

Routing config audit (decommission pre-condition 4): `ANNOUNCEMENTS_API_URL`,
`USER_PREFERENCES_API_URL` and `FEEDBACK_API_URL` resolve to `:8101/:8102/:8103` in
`docker-compose.yml`, `infrastructure/helm/web-app/values.yaml` and
`frontend/client-app/Dockerfile`. No config value points at `:8095` (the one remaining `8095`
occurrence is a stale comment — see "Still outstanding").

## 2. Parity

Reference is the pinned pre-retirement monolith, per `docs/migration/decommission.md`:

```bash
git worktree add /tmp/lp-pre-retirement c07b93bc
docker build -t otterworks/legacy-portal:pre-retirement-c07b93bc \
  /tmp/lp-pre-retirement/services/legacy-portal

# repeated in full before EACH context, because the scenarios mutate state
make portal-down NS=dev && make portal-up NS=dev
docker rm -f lp-pre-retirement
docker run -d --name lp-pre-retirement -p 8096:8095 \
  otterworks/legacy-portal:pre-retirement-c07b93bc

export PORTAL_LEGACY_URL=http://localhost:8096
PORTAL_CANDIDATE_URL=http://localhost:8101 make portal-parity CONTEXT=announcements
PORTAL_CANDIDATE_URL=http://localhost:8102 make portal-parity CONTEXT=user-preferences
PORTAL_CANDIDATE_URL=http://localhost:8103 make portal-parity CONTEXT=feedback
```

| Context | Result | Exit |
|---|---|---|
| announcements | `60/60 identical` | 0 |
| user-preferences | `47/47 identical` | 0 |
| feedback | `61/61 identical` | 0 |

Each suite ran from a freshly recreated stack **and** a freshly created reference container, so
no run inherited another's writes. The counts match the pinned transcripts in
`docs/migration/parity-evidence/`.

## 3. Test suites

| Suite | Command | Result |
|---|---|---|
| Extracted services | `cd services/portal && ./mvnw -B verify` | BUILD SUCCESS — `portal-common` 4, `announcements-service` 44, `user-preferences-service` 28, `feedback-service` 36 tests, 0 failures/errors/skips (Testcontainers-backed integration tests included) |
| Monolith shell | `cd services/legacy-portal && ./mvnw -B verify` | BUILD SUCCESS — 8 tests, 0 failures/errors, **1 skipped** (`DependencyTranscriptEmitterTest`, which needs JDK 11 for the Nashorn cases) |
| Client app lint | `cd frontend/client-app && npm run lint` | 0 errors, 1 pre-existing warning (`src/pages/file-detail.tsx:84`, `react-hooks/exhaustive-deps`, unrelated to the portal slice) |
| Client app unit tests | `npm test` (vitest) | 4 files, 17 tests passed |
| Client app build | `npm run build` (`tsc --noEmit && vite build`) | success; only the pre-existing >500 kB chunk-size advisory |

## 4. Dependency gate

```bash
make deps-gate        # exit 2
make deps-transcript  # exit 2
```

**Gate (`security/deps/reports/gate.json`), CVE-2022-42889 / `org.apache.commons:commons-text` vulnerable in [1.5, 1.10.0):**

| Module | Build | Status | Version | Path |
|---|---|---|---|---|
| report-service | maven | VULNERABLE | 1.9 | direct (`services/report-service/pom.xml:43,120,121`) |
| legacy-portal | maven | VULNERABLE | 1.9 | transitive via `org.apache.commons:commons-configuration2:2.8.0` |
| notification-service | gradle | unmeasured | — | no runnable build tool (`gradle` is not on PATH here) |
| auth-service | gradle | clean | — | — |
| portal | maven | clean | — | — |

`GATE INCONCLUSIVE: 1 module(s) unmeasured: notification-service`.

**Transcript (`--stage remediated`):** `report-service` **fail** (11 cases; the three attack
cases `attack-script-lookup`, `attack-dns-lookup`, `attack-url-lookup` still resolve the
`script:`, `dns:` and `url:` lookups), `legacy-portal` **pass** (7 cases), `notification-service`
**unmeasured**.

**Before/after framing.** The gate was already red before this migration: `report-service`
carries `commons-text` 1.9 directly, `legacy-portal` carried it transitively, and
`notification-service` was unmeasured without Gradle. What the migration changed:

- **New and clean:** the extracted `portal` reactor is *measured* (`./mvnw`, one build covering
  all four child modules; `services/portal` itself is a registered exemption as the reactor's
  path, and `services/portal/skeleton` is a template, not a module) and reports **clean** — the
  three extracted services introduce no new exposure to the advisory.
- **Monolith unchanged:** reducing `legacy-portal` to its shell did **not** clear it. It still
  depends on `commons-configuration2` 2.8.0 for `PortalBrandingSettings` (the branding/settings
  file with interpolation), which still pulls `commons-text` 1.9 transitively. Its transcript
  still passes — the shell's own interpolation behaviour is unchanged, and the script/url
  lookups stay unresolved there — but its gate status is exactly what it was.
- **Unchanged otherwise:** `report-service` is still directly vulnerable and its three attack
  cases still fail; `notification-service` is still unmeasured.

No CVE was remediated and no gate configuration was touched: this is a validation run only.

## 5. Announcements UI (browser)

Recorded Chrome session against the running stack, Vite dev server on `:3000`, at
`/announcements`. Recording:
[`announcements-ui-edited.mp4`](https://partner-workshops.devinenterprise.com/attachments/65b7b625-8dd2-4cee-81c6-830a109bb941/announcements-ui-edited.mp4).

| Scenario | Result |
|---|---|
| Initial list (empty database) | Empty state — "No announcements / Nothing has been published yet." |
| Create unpublished | Success toast, form cleared, row correctly hidden under the default published-only filter |
| Create with "Publish immediately" | Row appears immediately with a green **Published** badge (the contract's `published: true` pass-through) |
| Publish an existing draft | Row's **Publish** button flips to the **Published** badge without a reload |
| Filter "Show unpublished" on / off | 2 rows with the draft's Publish button / exactly 1 published row |
| Error path — service stopped | `docker stop` the announcements service → red alert "Announcements service returned 502" with Dismiss + Retry; after `docker start`, **Retry** clears the alert and reloads the list |
| Error path — client validation | Empty submit shows inline "Title is required" / "Body is required"; nothing is created |

| Published only | Show unpublished |
|---|---|
| ![published only](https://partner-workshops.devinenterprise.com/attachments/1953f5fd-4bbf-4da4-9308-88f3a98111af/ss_7ac5cef8.png) | ![with draft](https://partner-workshops.devinenterprise.com/attachments/c5bf221a-d860-4c3f-b9f1-556293110a46/ss_c3601718.png) |

| After publishing the draft | Service down → error + Retry | Recovered after Retry |
|---|---|---|
| ![published](https://partner-workshops.devinenterprise.com/attachments/56544490-d776-4152-a946-47e87f52dd22/ss_a19ced87.png) | ![error](https://partner-workshops.devinenterprise.com/attachments/ed4910ca-c946-4ca4-91c7-9933a2831390/ss_dc664715.png) | ![recovered](https://partner-workshops.devinenterprise.com/attachments/62443f73-82f1-48f5-bfc4-a17f77da8821/ss_7918c6f1.png) |

[Client-side validation errors](https://partner-workshops.devinenterprise.com/attachments/0a8557c0-6d89-46be-bbd9-d2d16a003541/ss_e2fb3b8d.png).

**Data placement.** The rows written through the browser are in the extracted service's
database:

```bash
docker exec otterworks-portal-dev-announcements-db-1 \
  psql -U announcements -d announcements_dev \
  -c 'select id,title,published,created_at from announcement order by id'
```

```
 id |              title               | published |         created_at
----+----------------------------------+-----------+----------------------------
  1 | Draft: maintenance window        | t         | 2026-08-20 23:14:19.170243
  2 | Otterworks portal is now modular | t         | 2026-08-20 23:14:28.592406
(2 rows)
```

and not in the monolith: `GET http://localhost:8095/api/announcements` → `404`, the
`legacy-portal` container has no `SPRING_DATASOURCE_*`/JDBC environment at all, and the Compose
project has no monolith database container (only `announcements-db`, `user-preferences-db`,
`feedback-db`).

Note the table is `announcement` (singular), per
`announcements-service/src/main/resources/db/migration/V1__create_announcement.sql`.

## Still outstanding, unmeasured or untested

Nothing here blocked the validation; all of it is knowingly open.

1. **`report-service` is still vulnerable to CVE-2022-42889** (`commons-text` 1.9, direct) and
   its three attack transcript cases still fail. Pre-existing; out of scope here.
2. **`legacy-portal` is still transitively vulnerable** through `commons-configuration2` 2.8.0,
   which the shell retains for `PortalBrandingSettings`. Removing the bounded contexts did not
   remove this edge; it disappears only when the module is deleted at decommission step 6.
3. **`notification-service` is unmeasured by the gate.** No `gradle` on PATH in this
   environment, so its `commons-text` status is unknown — it is neither clean nor vulnerable in
   the report. Unchanged by this migration.
4. **`DependencyTranscriptEmitterTest` is skipped** in `services/legacy-portal`'s `verify` on the
   ambient JDK 21; the Nashorn-dependent cases only run under JDK 11 (which the deps harness
   selects separately, and where the module's transcript does pass).
5. **Only announcements was exercised in a browser.** User-preferences and feedback were proven
   by parity, unit/integration tests and health checks, not through a UI.
6. **Only the Compose path was validated.** Kubernetes/Helm values were read and audited but not
   deployed; the nginx container image proxy path was not exercised (the Vite dev proxy was).
7. **The pinned reference image exists only on this machine.** It was rebuilt locally from
   `c07b93bc`; decommission pre-condition 6 ("the rollback image exists in the registry the
   environment pulls from") is still unmet.
8. **Stale comment in `frontend/client-app/Dockerfile` (line 28)** still says a context can be
   rolled back to the monolith with one env var (`http://legacy-portal:8095`). That is no longer
   true — the shell returns `404` for those routes and rollback is a redeploy of the pinned
   image. Left in place deliberately: this run is a gate, not a fix.
9. **`publishedOnly=true` list order is not id-ascending** (id 2 sorted before id 1 after the
   draft was published). Parity covers the list responses and is identical to the monolith, so
   this is monolith-faithful behaviour, not a regression — recorded only because it surprises.
10. **Not run:** the Playwright e2e and Cucumber BDD suites in `frontend/client-app`, the rest
    of the golden-app stack (`make up` / `make test`), and any load, soak or failover testing.
    Decommission pre-condition 2 (zero hits on the removed routes over a full business cycle)
    cannot be evidenced from a local run.
