# Operator notes — user-preferences

Scope: `services/portal/user-preferences-service` only. The shared pattern lives in
`docs/migration/skeleton.md`; the behaviour under test lives in
`docs/migration/contracts/user-preferences.md`.

## Run it

```
make portal-up NS=dev
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev ps
```

The `user-preferences` profile starts two containers: `user-preferences-service` (published on
`127.0.0.1:8102`) and its own `user-preferences-db` (Postgres 16, `127.0.0.1:55502`, named volume
`user-preferences-db-data`). Health: `curl http://localhost:8102/health` →
`{"status":"UP","service":"user-preferences-service"}`.

Override `USER_PREFERENCES_PORT`, `USER_PREFERENCES_DB_PORT`, `USER_PREFERENCES_DB_PASSWORD` and
`NS` in the environment; nothing is hard-coded in the image or in `application.yml`.

## Image

`services/portal/user-preferences-service/Dockerfile` builds from the `./services/portal` context
because the module needs the parent POM and `portal-common`. The parent is installed
non-recursively (`-N`) and each module is built with `-f`, so the sibling services are not
required in the context — do not switch to a `-pl`/`-am` reactor build. Runtime stage is
`eclipse-temurin:21-jre-jammy` running as non-root `appuser` (uid 1001) with `target/app.jar` and
a `curl`-based healthcheck on `/health`.

## Schema

Flyway owns the schema (`ddl-auto: none`). First boot applies
`V1__create_user_preference.sql` into the service's own database; a restart logs
`Schema "public" is up to date. No migration necessary.` and keeps existing rows. If a migration
ever needs to be re-run from scratch, drop the namespace's data with `make portal-down NS=dev`
(which removes the volumes) rather than editing the applied migration.

## Parity

```
PORTAL_CANDIDATE_URL=http://localhost:8102 make portal-parity CONTEXT=user-preferences
```

with the monolith up on 8095 (the `legacy` profile). Expected: `47/47 identical`.

## Isolation

The service resolves only `user-preferences-db`; its datasource URL, username and password come
from compose environment variables and no other database host is configured. The published port
is bound to `127.0.0.1`, so the service is reachable only from the host — it has no
authentication, exactly like the monolith.
