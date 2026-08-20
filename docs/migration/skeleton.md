# Shared service skeleton

**Status: frozen.** Every extracted portal service is built from exactly this pattern. A Wave 1
child fills in the blanks; it does not invent a second pattern, and it does not change anything
described here. If a child believes the skeleton is wrong it **stops and reports to the parent
session** rather than working around it.

The pattern exists so the three services are interchangeable to an operator: same build, same
error envelopes, same health surface, same configuration keys, same container shape. Divergence
is the failure mode this document prevents.

## 1. Layout

```
services/portal/
├── pom.xml                       # parent: Boot 3.3.5, Java 21, plugin + dependency management
├── mvnw, mvnw.cmd, .mvn/         # Maven 3.9.9 wrapper, same pin as the monolith
├── portal-common/                # shared error envelope + /health, auto-configured
├── skeleton/                     # templates to copy; NOT a Maven module
│   ├── pom.xml
│   ├── application.yml
│   └── Dockerfile
└── <context>-service/            # one per Wave 1 child
    ├── pom.xml
    ├── Dockerfile
    └── src/main/java/com/otterworks/portal/<context>/…
        src/main/resources/application.yml
        src/main/resources/db/migration/V1__….sql
        src/test/java/…
```

Allocation (fixed by the contracts):

| Context | Module | Port | Compose profile | Database |
|---|---|---|---|---|
| Announcements | `announcements-service` | 8101 | `announcements` | `announcements-db` |
| User preferences | `user-preferences-service` | 8102 | `user-preferences` | `user-preferences-db` |
| Feedback | `feedback-service` | 8103 | `feedback` | `feedback-db` |

## 2. Creating a service

1. Copy `skeleton/pom.xml` → `<context>-service/pom.xml`, replace `<context>`, and add
   `<module><context>-service</module>` to the parent `<modules>`. That one line is the only
   edit a child makes to a shared file in Wave 1.
2. Copy `skeleton/application.yml` → `<context>-service/src/main/resources/application.yml` and
   replace `<context>` and `<port>`.
3. Copy `skeleton/Dockerfile` → `<context>-service/Dockerfile` and replace `<context>` and
   `<port>`.
4. Write the entrypoint as `com.otterworks.portal.<context>.<Context>Application` with a plain
   `@SpringBootApplication`. Component scanning stays inside your own package —
   `portal-common` arrives through auto-configuration, not scanning.
5. Write `db/migration/V1__create_<table>.sql` from the DDL in your contract, verbatim.

## 3. What `portal-common` gives you (and what you must not re-implement)

- `PortalExceptionHandler` — the monolith's `GlobalExceptionHandler`, port-for-port:
  `NoSuchElementException` → 404 and `IllegalArgumentException` → 400, both as the **legacy
  envelope** `{"error","message"}`. It deliberately does *not* extend
  `ResponseEntityExceptionHandler`, so bean-validation failures, unreadable bodies, 404, 405
  and 500 keep Spring's **default envelope** `{"timestamp","status","error","path"}`. Both
  envelopes are on the legacy wire and both are contractual.
  - Consequence worth knowing before you debug it: parameter and path-variable conversion
    failures reach this advice by Spring's cause unwrapping, so `GET /api/announcements/abc`
    returns the *legacy* envelope with the raw `For input string: "abc"` message.
- `PortalHealthController` — `GET /health` → `{"status":"UP","service":"<spring.application.name>"}`.
  The monolith's `banner` field is intentionally dropped; it is sourced from a
  `portal-settings.properties` file resolved against the working directory, which is the
  highest-rated finding in the assessment. This is the one deliberate response difference in
  the whole migration, and the parity scenarios exclude `/health` because of it.

Do not add a second `@ControllerAdvice`, do not re-declare these beans, and do not add
`server.error.include-*` overrides — the defaults in `skeleton/application.yml` are what make
the default envelope match.

## 4. Non-negotiables

- **Java 21 / Boot 3.3.5**, inherited. No module sets its own versions.
- **Flyway owns the schema.** `spring.jpa.hibernate.ddl-auto: none`, permanently. The monolith
  runs `ddl-auto: update`; reproducing that in an extracted service is a contract violation.
- **One database per service**, reached only by its owner. No cross-context table access, no
  cross-context HTTP call, no shared library beyond `portal-common`.
- **No credentials in source.** The datasource comes from `SPRING_DATASOURCE_*` in the
  environment; compose supplies local development values.
- **Route prefixes are unchanged** (`/api/announcements`, `/api/preferences`, `/api/feedback`)
  so the Wave 2 routing switch is a configuration change, not a client change.
- **The dependency gate already covers you.** `security/deps/modules.yaml` registers the
  `services/portal` reactor as one module, so a new service is measured the moment it is added
  to `<modules>`. Do not add a per-service entry and do not exempt anything.
- **No authentication.** The monolith has none, `userId` is caller-supplied, and adding auth
  would break parity. Extracted services are internal-only, bound to `127.0.0.1` in compose,
  and reachable only through the gateway. Closing this gap is a coordinated contract revision
  across all three services, not a per-child decision.

## 5. Tests every service ships

1. **Unit/slice tests** for the service and controller, including the behaviours the contract
   calls out as traps (fabricated preference defaults that are not persisted; primitive-boolean
   binding; idempotent publish; empty-table average of `0.0`).
2. **Integration test** on the real engine via Testcontainers PostgreSQL, running the Flyway
   migrations — not H2, because the monolith's H2 behaviour is exactly what we are leaving.
3. **Parity suite** using the shared harness (§6). Nothing else counts as parity: a child that
   writes its own comparison logic has forked the pattern.

## 6. Parity harness

`tests/parity/portal/replay.py` replays `tests/parity/portal/scenarios/<context>.json` against
both the monolith and the extracted service and diffs status + body after the normalisations
in `docs/migration/contracts/README.md` (instants compared by shape, identifiers by allocation
order).

```bash
make portal-up NS=dev
PORTAL_CANDIDATE_URL=http://localhost:8101 make portal-parity CONTEXT=announcements
```

Both sides must start empty. A child **adds cases** to its own scenario file; it must not edit
`replay.py`, the normalisation rules, or another context's scenarios. Green means every case in
the file is byte-identical after normalisation.

`docs/migration/contracts/record-baseline.sh` and the checked-in
`docs/migration/contracts/baseline-transcript.json` are the recorded monolith responses that
the contracts were written from — evidence, not a test. Re-record only against a freshly
started monolith.

## 7. Compose

`docker-compose.portal.yml` already contains the service and database entry for all three
contexts, each behind its own profile plus a `legacy` profile for the monolith. A child fills
in nothing there: it only has to make its `Dockerfile` build. Ports, names, healthchecks, and
the `127.0.0.1` bindings are fixed.

```bash
make portal-up NS=dev PROFILE=announcements   # one context plus its database
make portal-up NS=dev                          # everything that exists
make portal-down NS=dev
```
