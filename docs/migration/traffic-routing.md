# Portal traffic routing — the switch and the rollback

Wave 1 extracted the three portal bounded contexts and proved them at parity with the monolith.
This document is the **routing seam**: how a caller picks the backend for a context, what the
values are in each environment, how to roll a single context back, and how to check which
backend is actually serving.

The rule the seam obeys: **one config value per context, no code change, no image rebuild.**

## The config values

| Context | Config value | Old value (monolith) | New value (extracted, current default) |
|---|---|---|---|
| Announcements | `ANNOUNCEMENTS_API_URL` | `http://legacy-portal:8095` (dev: `http://localhost:8095`) | `http://announcements-service:8101` (dev: `http://localhost:8101`) |
| User preferences | `USER_PREFERENCES_API_URL` | `http://legacy-portal:8095` (dev: `http://localhost:8095`) | `http://user-preferences-service:8102` (dev: `http://localhost:8102`) |
| Feedback | `FEEDBACK_API_URL` | `http://legacy-portal:8095` (dev: `http://localhost:8095`) | `http://feedback-service:8103` (dev: `http://localhost:8103`) |

Each value is a **base URL only**. The route prefixes are unchanged on both sides
(`/api/announcements`, `/api/preferences`, `/api/feedback`), so swapping the base URL is the
entire switch — that is what makes rollback a config change instead of a deployment.

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

One command, one value, one context. Nothing else moves; the monolith's routes are still live.

```bash
# dev
ANNOUNCEMENTS_API_URL=http://localhost:8095 npm run dev            # in frontend/client-app

# docker compose (golden app stack)
ANNOUNCEMENTS_API_URL=http://legacy-portal:8095 docker compose up -d --no-deps --force-recreate web-app

# kubernetes
helm upgrade web-app infrastructure/helm/web-app --reuse-values \
  --set-string env.ANNOUNCEMENTS_API_URL=http://legacy-portal:8095
```

Roll forward again by putting the value back (`http://announcements-service:8101`, dev
`http://localhost:8101`) and repeating the same command. Substitute
`USER_PREFERENCES_API_URL` / `http://localhost:8102` or `FEEDBACK_API_URL` /
`http://localhost:8103` for the other two contexts.

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
# monolith:  {"status":"UP","service":"legacy-portal","banner":"…"}

curl -s http://localhost:3000/user-preferences-api/health   # user-preferences-service | legacy-portal
curl -s http://localhost:3000/feedback-api/health           # feedback-service        | legacy-portal
```

A second, independent signal: responses from the monolith carry the deprecation headers, and the
extracted services do not.

```bash
curl -si http://localhost:3000/announcements-api/api/announcements | grep -i '^deprecation\|^sunset'
# Deprecation: true
# Sunset: Wed, 31 Mar 2027 00:00:00 GMT
```

The monolith also logs every deprecated-route hit
(`Deprecated monolith route served: GET /api/announcements …`), so
`docker compose -f docker-compose.portal.yml -p otterworks-portal-dev logs legacy-portal` shows
whether any traffic is still landing on it.

## What is deprecated, and what is not

`/api/announcements`, `/api/preferences` and `/api/feedback` on the monolith are **deprecated but
fully working**, and stay that way until the monolith is retired:

- `Deprecation: true` and `Sunset: Wed, 31 Mar 2027 00:00:00 GMT` response headers, added by
  `com.otterworks.legacyportal.common.DeprecatedContextRoutesFilter`.
- A `WARN` log line per request naming the service that owns the context now.
- A class comment on each of the three controllers.

Status codes and response bodies are untouched, so the parity suites still replay against the
monolith unchanged:

```bash
make portal-up NS=dev
PORTAL_CANDIDATE_URL=http://localhost:8101 make portal-parity CONTEXT=announcements
PORTAL_CANDIDATE_URL=http://localhost:8102 make portal-parity CONTEXT=user-preferences
PORTAL_CANDIDATE_URL=http://localhost:8103 make portal-parity CONTEXT=feedback
```
