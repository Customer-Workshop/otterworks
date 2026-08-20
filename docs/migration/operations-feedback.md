# Operator notes — feedback

Feedback-specific notes for running `services/portal/feedback-service` as a container. The
shared pattern is [`skeleton.md`](skeleton.md); the wire contract is
[`contracts/feedback.md`](contracts/feedback.md). Nothing here overrides either.

## Run it

```bash
make portal-up NS=dev                      # legacy + every context that exists
make portal-up NS=dev PROFILE=feedback     # feedback-service + feedback-db only
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev ps
make portal-down NS=dev                    # stops the stack and drops the volumes
```

The image builds from context `./services/portal` with `feedback-service/Dockerfile`: the parent
POM is installed non-recursively, then `portal-common`, then this module with `-f`. The other
service modules are never copied into the image, so their absence is not a build error.

Port 8103 is published on `127.0.0.1` only, and `feedback-db` on `127.0.0.1:55503`. The service
runs as non-root `appuser` (uid 1001) and its `/health` is the container healthcheck.

## Configuration

Datasource credentials come from the environment only (`SPRING_DATASOURCE_URL`,
`SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD`); compose supplies development values
and `FEEDBACK_DB_PASSWORD` overrides the password. Nothing is baked into the image or the
sources. The database name is namespaced: `feedback_${NS}`.

## Schema

Flyway owns the schema (`ddl-auto: none`). First boot against an empty `feedback-db` applies
`V1__create_feedback.sql`; a restart validates the one migration and applies nothing:

```
o.f.core.internal.command.DbValidate  : Successfully validated 1 migration
o.f.core.internal.command.DbMigrate   : Current version of schema "public": 1
o.f.core.internal.command.DbMigrate   : Schema "public" is up to date. No migration necessary.
```

The `feedback` table carries no CHECK constraint on `rating` — the monolith has none, and the
1–5 bound is enforced in the application layer where parity requires it. Do not add one in a
later migration.

## Verifying against the container

```bash
PORTAL_CANDIDATE_URL=http://localhost:8103 make portal-parity CONTEXT=feedback
```

Both sides must start empty, so run it on a freshly created stack (after `make portal-down NS=dev`
or before any manual writes).

## Isolation

`feedback-service` connects to `feedback-db` and nothing else; no cross-context table access and
no cross-context HTTP call. To check while the stack is up, the only client of each database
should be its own service:

```bash
docker exec otterworks-portal-dev-feedback-db-1 \
  psql -U feedback -d feedback_dev -tAc \
  "select distinct client_addr, usename from pg_stat_activity where client_addr is not null"
```
