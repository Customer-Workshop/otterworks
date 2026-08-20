# Legacy Portal — modular monolith (rehost / decomposition "before" state)

`legacy-portal` is a **legacy modular monolith**: a single deployable Spring Boot application
(Java 11, Spring Boot 2.7.x, built with Maven) that bundles **three bounded contexts** into one
process. It exists as a realistic **"before" state** for two migration demos:

- **Rehost (lift-and-shift → EC2)** — it **runs on a VM / on-prem host today** (plain Docker
  Compose, a fat JAR under systemd), deliberately *not* on the repo's Helm/EKS path. That makes it
  the natural starting point for a lift-and-shift-to-EC2 demo.
- **Monolith decomposition (→ microservices / Lambda)** — its three contexts are cleanly separated
  by package **and by database schema**, so the seams for splitting it into services are obvious.

> This component is part of the OtterWorks **golden app** as a durable before-state. The
> after-state (EC2/ASG IaC, decomposed services) is intentionally **not** included here.

## Bounded contexts

Each context lives in its own package with its own routes and its own database schema. There are
**no cross-context foreign keys or shared tables** — the only thing they share is the JVM process
and the datasource. That is exactly what makes this a good decomposition candidate.

| Context | Package | Schema | Routes |
|---|---|---|---|
| Announcements | `com.otterworks.legacyportal.announcements` | `announcements` | `GET/POST /api/announcements`, `GET /api/announcements/{id}`, `POST /api/announcements/{id}/publish` |
| User Preferences | `com.otterworks.legacyportal.userpreferences` | `user_preferences` | `GET /api/preferences/{userId}`, `PUT /api/preferences/{userId}` |
| Feedback | `com.otterworks.legacyportal.feedback` | `feedback` | `POST /api/feedback`, `GET /api/feedback?userId=`, `GET /api/feedback/average-rating` |

Shared, non-domain plumbing lives in `com.otterworks.legacyportal.common` (health endpoint,
exception handling, branding settings).

### Why it's an obvious decomposition candidate

- **Independent data ownership** — one schema per context; no shared tables or joins across
  contexts, so each context's tables can be lifted into a per-service database.
- **Independent routes** — each context owns a distinct `/api/*` prefix that maps 1:1 to a future
  service (e.g. an `announcements-service`, a `preferences-service`, a `feedback-service`, or a
  Lambda per context).
- **No cross-context object references** — contexts do not call each other's services directly, so
  extracting one does not drag the others along.

## Branding settings

The banner served on the unauthenticated `/health` endpoint comes from
`portal-settings.properties`, read through Commons Configuration by
`common/PortalBrandingSettings`. Two rules apply to that file:

- Only key-to-key interpolation resolves (`${portal.environment}`). Prefixed lookups
  (`${env:...}`, `${file:...}`, `${sys:...}`, ...) are not registered on the interpolator the
  banner is read through, so they are served verbatim — the file cannot be used to read the
  process environment or the filesystem through `/health`.
- The packaged classpath copy is the default source. The process working directory (the JAR's
  install directory under systemd) is never searched. To edit settings without a redeploy,
  start the service with an explicit absolute path:

  ```bash
  java -Dportal.settings.path=/etc/legacy-portal/portal-settings.properties \
       -jar /opt/legacy-portal/legacy-portal.jar
  ```

## Build & test

```bash
cd services/legacy-portal
./mvnw verify        # compile + run unit tests (uses embedded H2)
```

## Run

### Local / on a VM (embedded H2, self-contained)

```bash
./scripts/run-onprem.sh
curl http://localhost:8095/health          # {"status":"UP","service":"legacy-portal"}
curl http://localhost:8095/actuator/health
```

Or under systemd on the VM — see [`deploy/legacy-portal.service`](deploy/legacy-portal.service).

### On-prem with a real PostgreSQL (Docker Compose)

```bash
docker compose -f docker-compose.onprem.yml up --build
curl http://localhost:8095/health
docker compose -f docker-compose.onprem.yml down -v
```

This brings up PostgreSQL alongside the app; the three schemas are created by
[`scripts/initdb.sql`](scripts/initdb.sql). This stack is intentionally separate from the
Helm/EKS deploy path — it models the on-prem host the rehost demo lifts *from*.

## Legacy markers (upgrade targets)

- Java 11 → 17+/21
- Spring Boot 2.7.x → 3.2+
- `javax.*` (Java EE) → `jakarta.*`
