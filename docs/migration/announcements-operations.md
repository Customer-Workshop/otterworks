# Announcements — operator notes

Scope: `services/portal/announcements-service` only. Nothing here changes the contract, the
shared skeleton, or the compose profile.

## Running the container

```bash
make portal-up NS=dev                           # portal shell + every extracted context
make portal-up NS=dev PROFILE=announcements     # announcements-service + announcements-db only
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev ps
curl -s http://localhost:8101/health            # {"status":"UP","service":"announcements-service"}
make portal-down NS=dev                         # stops the stack and drops its volumes
```

The image is a two-stage Temurin 21 build from the `./services/portal` context, runs as the
non-root `appuser` (uid 1001), and its healthcheck curls `/health` on 8101 — the same surface
compose polls. The published port is bound to `127.0.0.1`: the service carries no
authentication and is internal-only.

Schema and data:

- Flyway applies `V1__create_announcement.sql` into `announcements-db` on first boot
  (`Migrating schema "public" to version "1 - create announcement"`).
- A restart re-validates and does nothing (`Schema "public" is up to date. No migration
  necessary.`); `ddl-auto` stays `none`, so the container never mutates the schema.
- The datasource comes only from `SPRING_DATASOURCE_URL/USERNAME/PASSWORD` in the environment.
  The image carries no credentials and no baked datasource.
- The only database the service talks to is `announcements-db`: with the whole stack up, its
  open connections all target the `announcements-db` container on 5432, and the
  `announcements` role has no access to the other contexts' databases.

## Isolation checks worth repeating

```bash
# every published port is loopback-only
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev ps

# runtime identity and the only datasource the container knows about
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev \
  exec announcements-service sh -c 'id; printenv | grep SPRING_DATASOURCE'

# outbound connections: all to the announcements-db container address on 5432
docker compose -f docker-compose.portal.yml -p otterworks-portal-dev \
  exec announcements-service sh -c 'cat /proc/net/tcp6'
```

Compose puts every portal container on one default network, so sibling database hostnames
still resolve; separation is per-database and per-credential, not network-level. The
`announcements` role is rejected by `user-preferences-db` and `feedback-db`.

## Building the image

The image comes from the shared skeleton pattern: the parent POM is installed
non-recursively (`mvn -B -N install`) and `portal-common` and this module are then built with
`-f`, so the context never needs the other services' sources. Do not switch this module to a
`-pl … -am` reactor build.

Maven resolution goes to Maven Central. Hosts that Central rate-limits (HTTP 429) cannot
build these images without a mirror; configure one at the Docker/host level rather than in
this module's Dockerfile, which is generated from the shared skeleton.
