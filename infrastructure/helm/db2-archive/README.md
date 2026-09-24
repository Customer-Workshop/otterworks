# db2-archive

Db2 Community Edition (`icr.io/db2_community/db2:11.5.9.0`) for one legacy-data-migration tenant
namespace - the legacy `ARCHIVE` store that the migration extracts from and purges. Owned by the
**source** unit (CONTRACTS.md 13.1). Private only: ClusterIP, no ingress, no LoadBalancer.

## What it deploys

| Object | Name | Notes |
|---|---|---|
| StatefulSet | `db2-archive` | 1 replica, privileged (Db2 CE requirement), `LICENSE=accept`, `DBNAME` derived from the token |
| Service | `db2-archive` | ClusterIP, 50000 (Db2) + 8080 (health) |
| PVC | `db2-archive-data` | `storageClassName: ""` + `volumeName` -> binds the static gp3 PV created by ops Terraform; never dynamic |
| NetworkPolicy | `db2-archive` | 50000 only from same-namespace pods labelled `ldm/db2-client: "true"`; 8080 only from the monitoring namespace (+ optional node CIDRs) |
| ConfigMaps | `db2-archive-health`, `-ddl`, `-seed` | health server script, DDL from `migration/source/db2/ddl`, seed generator + `load.sh` |
| Hook Job | `db2-archive-init` | post-install/upgrade: generates SEED-SPEC data, ships it into `db2-archive-0`, runs `load.sh` (idempotent) |

`/health` on 8080 is `files/health.py` (python3 stdlib, shipped in the Db2 image), started in the Db2
container beside the stock entrypoint (`python3 health.py & exec setup_db2_instance.sh`) so its CLP
uses the live instance directly. It returns 200 iff `db2 CONNECT TO <DBNAME>` succeeds (503 with the
SQLCODE text otherwise); startup/readiness/liveness probes all use it, so a dead engine restarts Db2.
CONTRACTS.md calls this a sidecar; it is in-container for IPC/instance-home reasons, same port and
semantics. First boot (instance + database create) takes 5-15 min; the startup probe
allows 20 min.

`files/ddl` and `files/seed` are symlinks into `migration/source/`; Helm follows them, so the chart
always packages the DDL and generator from the same commit.

## Values

| Key | Default | Meaning |
|---|---|---|
| `namespaceToken` | `""` | `<run>-<state>` (e.g. `d24-after`); DB name = `upper(run[0:7]) + B|A` (`D24A`) |
| `dbName` | `""` | Override the derived DB name (max 8 chars) |
| `owner` / `expires` | `otterworks-demo` / - | Required labels; `expires` is `YYYY-MM-DDTHH:MM:SSZ` (label gets `_` for `:`, annotation `demo/expires-at` the exact value) |
| `credentialsSecret` | `db2-archive-credentials` | Existing Secret with `DB2_USER` / `DB2_PASSWORD` (`DB2_PASSWORD` = `db2inst1` password) |
| `pv.volumeName` / `pv.size` | - / `20Gi` | Static PV name from Terraform, claim size |
| `resources` | req `500m`/`2Gi`, lim `2`/`4Gi` | Fits the tenant ResourceQuota |
| `initJob.enabled` / `initJob.scale` | `true` / `"1"` | Run the seed hook; `"0.01"` for smoke tests |
| `networkPolicy.monitoringNamespace` / `nodeCIDRs` | `monitoring` / `[]` | Health-port ingress sources |

## Install (by the ops deploy script)

```bash
kubectl -n otterworks-d24-after create secret generic db2-archive-credentials \
  --from-literal=DB2_USER=db2inst1 --from-literal=DB2_PASSWORD="$DB2_PASSWORD"
helm upgrade --install db2-archive infrastructure/helm/db2-archive -n otterworks-d24-after \
  --set namespaceToken=d24-after --set pv.volumeName=pv-db2-d24-after \
  --set expires=2026-10-01T00:00:00Z --timeout 60m
```

Clients (migration job, UNLOAD01 runner) need the pod label `ldm/db2-client: "true"` and connect to
`db2-archive.otterworks-<token>.svc.cluster.local:50000`, database `<DBNAME>`.

## Seed timings (measured locally on the same image, 2 CPUs)

Generation at full scale: ~76 s. `load.sh` (DDL + `LOAD ... OF ASC` of 1.2M/4.1M/40 rows + SET
INTEGRITY + RUNSTATS): see `migration/source/seed/README.md`.
