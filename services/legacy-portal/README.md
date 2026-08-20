# Legacy Portal — the shell left after decomposition

`legacy-portal` used to be a modular monolith bundling **three bounded contexts** into one Spring
Boot deployable (Java 11, Spring Boot 2.7.x, Maven). Those contexts have been extracted, their
traffic switched over, and their code removed from here. What is left is a **shell**: it boots,
answers `/health` and the actuator endpoints, and owns no data.

| Context | Served by | Contract |
|---|---|---|
| Announcements | `services/portal/announcements-service` (8101) | [`docs/migration/contracts/announcements.md`](../../docs/migration/contracts/announcements.md) |
| User preferences | `services/portal/user-preferences-service` (8102) | [`docs/migration/contracts/user-preferences.md`](../../docs/migration/contracts/user-preferences.md) |
| Feedback | `services/portal/feedback-service` (8103) | [`docs/migration/contracts/feedback.md`](../../docs/migration/contracts/feedback.md) |

`/api/announcements`, `/api/preferences` and `/api/feedback` are **no longer served here** — they
return 404. No consumer points at them: the client app reaches each context through its own proxy
prefix and env var ([`docs/migration/traffic-routing.md`](../../docs/migration/traffic-routing.md)).

Switching the shell off — pre-conditions, ordered steps, the rollback point at each step and what
survives — is [`docs/migration/decommission.md`](../../docs/migration/decommission.md).

## What remains

```
src/main/java/com/otterworks/legacyportal
├── LegacyPortalApplication.java        # boot class
└── common
    ├── HealthController.java           # GET /health  → {"status","service","banner"}
    ├── GlobalExceptionHandler.java     # {"error","message"} envelope
    └── PortalBrandingSettings.java     # portal-settings.properties, read at startup
```

No datasource, no JPA, no database, no schemas: the `announcements`, `user_preferences` and
`feedback` schemas belong to the extracted services' own databases now.

## Build & test

```bash
cd services/legacy-portal
./mvnw verify
```

## Run

### Local / on a VM

```bash
./scripts/run-onprem.sh
curl http://localhost:8095/health          # {"status":"UP","service":"legacy-portal","banner":"…"}
curl http://localhost:8095/actuator/health
```

Or under systemd on the VM — see [`deploy/legacy-portal.service`](deploy/legacy-portal.service).

### Docker Compose (on-prem host model)

```bash
docker compose -f docker-compose.onprem.yml up --build
curl http://localhost:8095/health
docker compose -f docker-compose.onprem.yml down -v
```

This stack is intentionally separate from the Helm/EKS deploy path — it models the on-prem host
the portal ran on.

## Legacy markers (upgrade targets)

- Java 11 → 17+/21
- Spring Boot 2.7.x → 3.2+
- `javax.*` (Java EE) → `jakarta.*`
