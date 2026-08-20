# Portal traffic routing — the switch and the rollback

Wave 1 extracted the three portal bounded contexts and proved them at parity with the monolith.
This document is the **routing seam**: how a caller picks the backend for a context, what the
values are in each environment, and how to check which backend is actually serving.

The rule the seam obeys: **one config value per context, no code change, no image rebuild.**

> **The monolith is no longer a routing target.** Its announcements, user-preferences and
> feedback code has been deleted; what is left is a shell serving `/health` and the actuator
> endpoints only, and those three route prefixes now return `404` on it. Pointing a context's
> URL at `legacy-portal:8095` no longer rolls it back — rollback is a redeploy of the pinned
> pre-retirement image, see [`decommission.md`](decommission.md).

## The config values

| Context | Config value | Value (extracted service, current default) |
|---|---|---|
| Announcements | `ANNOUNCEMENTS_API_URL` | `http://announcements-service:8101` (dev: `http://localhost:8101`) |
| User preferences | `USER_PREFERENCES_API_URL` | `http://user-preferences-service:8102` (dev: `http://localhost:8102`) |
| Feedback | `FEEDBACK_API_URL` | `http://feedback-service:8103` (dev: `http://localhost:8103`) |

Each value is a **base URL only**. The route prefixes are unchanged from the monolith
(`/api/announcements`, `/api/preferences`, `/api/feedback`), so swapping the base URL is the
entire switch — which is what makes moving a context between backends a config change rather
than a deployment. Every value in every environment now points at an extracted service.

## Where each value is read

The browser never talks to a portal backend directly. It calls its own origin under a
per-context prefix, and the app's proxy — Vite in dev/preview, nginx in the container image —
forwards to whatever the context's config value points at, stripping the prefix.

| Context | Browser calls | Proxied to |
|---|---|---|
| Announcements | `/announcements-api/api/announcements` | `$ANNOUNCEMENTS_API_URL/api/announcements` |
| User preferences | `/user-preferences-api/api/preferences/{userId}` | `$USER_PREFERENCES_API_URL/api/preferences/{userId}` |
| Feedback | `/feedback-api/api/feedback` | `$FEEDBACK_API_URL/api/feedback` |

| Environment | Where the value lives |
|---|---|
| Dev / preview (`npm run dev`) | Process env read by `frontend/client-app/vite.config.ts`; defaults to `localhost:810x` |
| Container image | `ENV` defaults in `frontend/client-app/Dockerfile`, substituted into `nginx/default.conf.template` at container start |
| Docker Compose (golden app) | `web-app.environment` in `docker-compose.yml` (overridable from the shell/`.env`) |
| Kubernetes / Helm | `env` in `infrastructure/helm/web-app/values.yaml` → container env |

`VITE_ANNOUNCEMENTS_API_URL` remains the build-time escape hatch for shells with no same-origin
proxy (native/desktop); it overrides the whole base URL and is not part of the runtime switch.

nginx resolves these targets **per request** through the container's own resolver, so a context
whose backend is not deployed in that environment returns `502` on call instead of preventing
the app from starting.

## Rolling one context back

The config value is still the switch, but the only backend that can serve a context is an
image that contains that context's code. Since the monolith was reduced to its shell, that
means one of:

1. **Redeploy the extracted service at an earlier tag** — the normal fix for a bad release of
   announcements/user-preferences/feedback. The routing value does not change.
2. **Redeploy the pre-retirement monolith image** and point the context's URL at it — the
   break-glass path for a defect in the extraction itself. The image is
   `otterworks/legacy-portal:pre-retirement-c07b93bc`, built from commit `c07b93bc` (the last
   commit on `demo/legacy-portal-migration` where the monolith still served all three
   contexts). Full procedure, including the data caveat, in
   [`decommission.md`](decommission.md#break-glass-rollback).

Option 2 is not a config change: the shell running as `legacy-portal` has to be replaced with
the pinned image first, and any writes made against the extracted service since the cutover
are not in the monolith's database.

```bash
# break glass: run the pre-retirement monolith alongside the stack, then point one context at it
docker run -d --name legacy-portal-rollback --network otterworks-portal-dev_default \
  -p 8096:8095 otterworks/legacy-portal:pre-retirement-c07b93bc
ANNOUNCEMENTS_API_URL=http://localhost:8096 npm run dev            # in frontend/client-app
```

Roll forward again by putting the value back (`http://announcements-service:8101`, dev
`http://localhost:8101`). Substitute `USER_PREFERENCES_API_URL` / `http://localhost:8102` or
`FEEDBACK_API_URL` / `http://localhost:8103` for the other two contexts.

For the Compose path, the golden-app stack and the portal stack
(`docker-compose.portal.yml`, project `otterworks-portal-<NS>`) are separate Compose projects, so
the `web-app` container must be attached to the portal network for either backend hostname to
resolve:

```bash
docker network connect otterworks-portal-dev_default otterworks-web-app
```

## Verifying which backend is live

Every portal backend answers `GET /health` with its own name, and the proxy passes it straight
through — so the app's own origin will tell you who is serving a context:

```bash
curl -s http://localhost:3000/announcements-api/health
# extracted: {"status":"UP","service":"announcements-service"}
# shell:     {"status":"UP","service":"legacy-portal","banner":"…"}

curl -s http://localhost:3000/user-preferences-api/health   # user-preferences-service
curl -s http://localhost:3000/feedback-api/health           # feedback-service
```

A `legacy-portal` answer here means the context is pointed at the shell, which no longer serves
it: the health probe passes but every `/api/*` call under it returns `404`. Treat it as a
misconfiguration, not a rollback.

## What the monolith serves now

`/health` and the actuator endpoints — nothing else. `/api/announcements`, `/api/preferences`
and `/api/feedback` return `404`; the controllers, services, repositories, entities and the
`DeprecatedContextRoutesFilter` that used to stamp `Deprecation`/`Sunset` headers on them are
deleted, along with the schemas they owned.

The parity suites therefore replay against the pinned pre-retirement image instead of the
running `legacy-portal` container. The harness is unchanged; only the `--legacy` endpoint moves:

```bash
make portal-up NS=dev
docker run -d --name lp-pre-retirement -p 8096:8095 \
  otterworks/legacy-portal:pre-retirement-c07b93bc

export PORTAL_LEGACY_URL=http://localhost:8096
PORTAL_CANDIDATE_URL=http://localhost:8101 make portal-parity CONTEXT=announcements
PORTAL_CANDIDATE_URL=http://localhost:8102 make portal-parity CONTEXT=user-preferences
PORTAL_CANDIDATE_URL=http://localhost:8103 make portal-parity CONTEXT=feedback
```

The scenarios mutate state, so both sides must be freshly started (`make portal-down NS=dev`
first, and a new reference container) for a run to be meaningful. The last recorded run of each
suite is pinned under `docs/migration/parity-evidence/`.
