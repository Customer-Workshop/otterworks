# Decommissioning the legacy portal

The three bounded contexts the portal used to bundle are served by
`announcements-service` (8101), `user-preferences-service` (8102) and `feedback-service` (8103).
Their code has been deleted from `services/legacy-portal`, so what runs under that name today is
a **shell**: it boots, answers `GET /health` and the actuator endpoints, owns no data, and
returns `404` for `/api/announcements`, `/api/preferences` and `/api/feedback`.

This document is how the shell is switched off for good, and what the rollback position is at
each step.

## Pre-conditions

Do not start until all of these hold. Each is checkable; none is a judgement call.

| # | Pre-condition | How to check | Expected |
|---|---|---|---|
| 1 | No caller reaches the monolith for a bounded context | `curl -s $ORIGIN/announcements-api/health` (and the other two prefixes) | the extracted service's name, never `legacy-portal` |
| 2 | Zero hits on the removed routes | `docker compose -f docker-compose.portal.yml -p otterworks-portal-<NS> logs legacy-portal \| grep -c ' /api/'` (in Kubernetes: the same grep over the pod's access log for the retention window) | `0` over at least one full business cycle, 14 days recommended |
| 3 | Parity is green | run the three suites against the pinned reference (below) | `60/60`, `47/47`, `61/61` |
| 4 | Every config value points at an extracted service | grep `ANNOUNCEMENTS_API_URL`, `USER_PREFERENCES_API_URL`, `FEEDBACK_API_URL` across `docker-compose.yml`, `infrastructure/helm/web-app/values.yaml`, `frontend/client-app/Dockerfile`, and the deployed env | no `:8095` anywhere |
| 5 | Backups exist and restore | a verified dump of each extracted service's database, plus the last dump of the monolith's database if the deployment used one | restore tested into a scratch database |
| 6 | The rollback image exists in the registry | `docker image inspect otterworks/legacy-portal:pre-retirement-c07b93bc` | present, and pushed to the registry the environment pulls from |

### Parity against the pinned reference

The monolith was the parity reference, and it no longer serves those routes, so the reference
is the **pinned pre-retirement image** rather than the running shell. The harness in
`tests/parity/portal/` is unchanged — only the `--legacy` endpoint moves:

```bash
make portal-down NS=dev && make portal-up NS=dev        # both sides must start clean
docker rm -f lp-pre-retirement 2>/dev/null
docker run -d --name lp-pre-retirement -p 8096:8095 \
  otterworks/legacy-portal:pre-retirement-c07b93bc

export PORTAL_LEGACY_URL=http://localhost:8096
PORTAL_CANDIDATE_URL=http://localhost:8101 make portal-parity CONTEXT=announcements
PORTAL_CANDIDATE_URL=http://localhost:8102 make portal-parity CONTEXT=user-preferences
PORTAL_CANDIDATE_URL=http://localhost:8103 make portal-parity CONTEXT=feedback
```

The scenarios write, so a suite is only meaningful on freshly started backends on both sides;
re-running without recreating them compares two differently-accumulated datasets and reports
spurious diffs. The last clean run is recorded under `docs/migration/parity-evidence/` — that
transcript, not a replay against the shell, is the evidence of record from here on.

## Decommission steps

Each step is reversible until the expiry noted against it. Do them in order, and do not start a
step before the previous one's soak window has elapsed.

### 1. Drain

Remove the shell from every ingress path: delete its rule from the ingress/gateway, take it out
of any load-balancer target group, and remove its DNS record's traffic (leave the record).
Nothing routes to `:8095` any more, but the process still runs.

- **Rollback:** re-add the ingress rule. Seconds.
- **Expires:** never, while step 2 has not run.
- **Soak:** 3 days. Watch the shell's logs for connection attempts from anything you did not
  expect (health checkers, scrapers, forgotten cron jobs).

### 2. Stop the process

Scale the deployment to zero (`kubectl scale deploy/legacy-portal --replicas=0`), or
`docker compose -f docker-compose.portal.yml -p otterworks-portal-<NS> stop legacy-portal`, or
`systemctl stop legacy-portal` on the on-prem hosts. The deployment/service definition, the
image and the data stay where they are.

- **Rollback:** scale back to one, or `systemctl start`. Under a minute.
- **Expires:** when step 5 removes the definition.
- **Soak:** 7 days with the process down and no incident attributable to it.

### 3. Retain the data

The shell owns no database, but a long-lived deployment may still have the monolith's
PostgreSQL volume from before the extraction. Before anything is deleted:

- take a final `pg_dump` of the monolith database, verify it restores into a scratch database,
  and store it with the retention class the data requires (the announcements, user_preferences
  and feedback tables are the only content);
- record the dump's location and checksum in the change ticket;
- mark the database read-only (`ALTER DATABASE ... SET default_transaction_read_only = on`) so
  nothing can write to it while it waits to be deleted.

- **Rollback:** not applicable; this step only adds a safety net.
- **Expires:** the dump is retained per the data retention policy, independent of the steps
  below. It is the last copy of pre-cutover state once step 6 runs.

### 4. Remove it from CI

Delete the `legacy-portal` job and its path filter from `.github/workflows/ci.yml` once the
module is gone from the repository (step 6). Until then CI keeps building the shell, which is
what proves it still compiles if you have to revert.

- **Rollback:** revert the workflow commit. Minutes.
- **Expires:** never — CI configuration is always revertible from git.

### 5. Remove it from Compose and Helm

- `docker-compose.portal.yml`: delete the `legacy-portal` service and the `legacy` profile,
  and drop `--profile legacy` from `PORTAL_PROFILES` / `PORTAL_ALL_PROFILES` in the `Makefile`.
- `services/legacy-portal/docker-compose.onprem.yml` and `deploy/legacy-portal.service`: delete
  with the module.
- Helm: delete the `legacy-portal` release (`helm uninstall legacy-portal -n <ns>`) and its
  values.

- **Rollback:** `git revert` the commit and redeploy; the image is still in the registry.
  Roughly one deploy cycle.
- **Expires:** when the pinned image is deleted from the registry (see "Break-glass rollback").

### 6. Release the ports and DNS, delete the database and volumes

The point of no return, and the only irreversible step.

1. Release port `8095` in the environment's port allocation table and delete the
   `legacy-portal` DNS record. Leave the name unassigned for at least 30 days so a stale client
   fails to resolve rather than reaching something else.
2. Delete the database and its volumes: `docker volume rm otterworks-portal-<NS>_legacy-portal-data`
   (or the equivalent PVC / RDS instance), only after the step 3 dump has been verified.
3. Delete `services/legacy-portal/` from the repository.

- **Rollback:** restore from the step 3 dump into a new database and redeploy the pinned image.
  Hours, not minutes, and any writes made against the extracted services in the meantime are
  not in that dump.
- **Expires:** immediately for the volumes; the dump remains the only recovery path.

## Break-glass rollback

Between now and step 6, rollback for a defect in an extracted service is:

| Situation | Action |
|---|---|
| Bad release of an extracted service | redeploy that service at its previous tag. The routing values do not change. This is the normal path. |
| The extraction itself is wrong for a context | redeploy `otterworks/legacy-portal:pre-retirement-c07b93bc` and point that context's URL at it |

The pinned image is built from commit `c07b93bc` on `demo/legacy-portal-migration` — the last
commit where the monolith served all three contexts, with the deprecation filter in place:

```bash
git worktree add /tmp/lp-pre-retirement c07b93bc
docker build -t otterworks/legacy-portal:pre-retirement-c07b93bc \
  /tmp/lp-pre-retirement/services/legacy-portal
```

Then run it and re-point one context:

```bash
docker run -d --name legacy-portal-rollback --network otterworks-portal-<NS>_default \
  -p 8096:8095 otterworks/legacy-portal:pre-retirement-c07b93bc
ANNOUNCEMENTS_API_URL=http://localhost:8096 npm run dev    # or the Compose/Helm equivalent
```

Two caveats that make this a break-glass path rather than a routine one:

- **It is a deployment, not a config change.** The shell has to be replaced with the pinned
  image before any URL is re-pointed.
- **The data does not come with it.** The monolith image starts from its own (empty, or
  restored) database; everything written through the extracted services since cutover lives in
  those services' databases and would have to be migrated back by hand.

This path is available until step 6 deletes the data, and only as long as the pinned image
exists. Keep it in the registry for at least 90 days after step 2, and record its digest in the
change ticket so it can be pulled by digest if the tag is ever reused.

## What is left afterwards

After step 6 the monolith is gone from the repository, the registry entry is a dated rollback
artifact rather than a deployable, and what remains of the estate is:

- three extracted services, each owning its own schema and database;
- the frozen contracts in `docs/migration/contracts/` and the parity harness in
  `tests/parity/portal/`, kept as the record of what the behaviour was and how it was proved;
- the recorded transcripts in `docs/migration/parity-evidence/`, which are the only remaining
  monolith-backed evidence once the pinned image is deleted;
- this document and `traffic-routing.md`, as the history of how the routing seam was closed.

Before step 6 (i.e. while `services/legacy-portal/` still exists), the shell is:
`LegacyPortalApplication`, `HealthController`, `GlobalExceptionHandler`,
`PortalBrandingSettings` and their tests — no datasource, no JPA, no schema, no bounded-context
code.
