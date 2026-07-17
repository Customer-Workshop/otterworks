# OtterWorks Demo Platform (control plane)

A self-contained control plane for running **many ephemeral OtterWorks demo tenants** on the
shared `otterworks-dev` EKS cluster, designed to scale to **high tens of tenants**. It adds a
platform plane (dashboard + durable state + reaper + DNS/TLS) on top of the existing per-tenant
tooling in `../scripts/` (`deploy-tenant.sh`, `teardown-tenant.sh`, `inject-bug.sh`, …).

> Scoped to OtterWorks only (per decision), kept in this monorepo rather than
> `platform-engineering-shared-services`.

## Two planes
See `docs/architecture.md` and the diagram `docs/platform-vs-multitenant.png`.

- **Platform plane (shared, always-on, one of each):** ingress-nginx + 1 NLB, cert-manager
  (wildcard TLS), external-dns (Route53), 1 RDS instance, shared S3/DynamoDB (tenant-prefixed),
  the **Demo Ops Dashboard**, a durable **DynamoDB control table**, and the **reaper**.
- **Multi-tenant plane (ephemeral, per checkout):** namespace `otterworks-<id>` (all services +
  in-cluster Redis/Meili), its DB `otterworks_<id>`, its prefix in the shared S3/Dynamo, an
  ingress host `t-<id>.demo.otterworks.xyz`, mapped to git branch `workshop-<id>`.

## Layout
```
demo-platform/
  docs/          architecture, control-table schema, API contract, plan-B, diagram
  infra/terraform/  control table + dashboard IRSA (+ gated Route53/DNS IAM)
  dashboard/     Next.js ops dashboard (passcode auth, checkout/check-in, reaper panel)
  runner/        image that runs deploy/teardown/inject Jobs (carries repo + toolchain)
  reaper/        reaper v2 CronJob + orphan sweeper (schedule from control table)
  helm/          charts to deploy the dashboard + reaper into otterworks-platform
```

## Checkout / check-in model
A **checkout** reserves a tenant id (atomic lock in the control table), maps it to an
OtterWorks git **branch** (`workshop-<id>`), and deploys that branch into `otterworks-<id>`.
A **check-in** tears the tenant down and frees the id. All state lives in the control table, so
it is **independent of the ephemeral infra** — it survives teardown, node churn, and pod
restarts. The reaper reconciles desired (table) vs actual (cluster/AWS) and GCs everything,
including **orphans** with no matching tenant record.

## Scale to high-tens
Autoscaling (Karpenter / raised node-group max), VPC **prefix delegation** (avoid pod-IP
exhaustion), PgBouncer for RDS connection limits, single shared managed services with in-resource
namespacing (Scope A; see `docs/plan-B-consolidation.md` for the future 1-bucket/1-table
collapse). Details in `docs/architecture.md` §7.

## Status
This is being built incrementally; see the PR description for what is live vs designed.
