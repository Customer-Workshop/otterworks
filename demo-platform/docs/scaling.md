# Scaling the demo platform to high-tens of tenants

Grounded in the live `otterworks-dev` cluster (one SPOT `t3.large` managed node group). Each
full tenant is ~15 pods (11 backends + 2 frontends + Redis + MeiliSearch). This doc lists the
concrete limits you hit as tenant count climbs and the fix for each — with ready-to-run
commands. Applied changes are noted; **opt-in** changes are scripted but intentionally NOT
force-applied to the live cluster (they recycle nodes and would disturb running tenants).

## 1. Node capacity / autoscaling — PARTIALLY APPLIED
- **Done:** node group `maxSize` raised **4 → 20** (`aws eks update-nodegroup-config`), so the
  cluster *can* grow. `desiredSize` kept at 4 to cap idle cost.
- **Do:** run **Cluster Autoscaler** (or Karpenter) so nodes scale with pending pods instead of
  manual `desiredSize` bumps. `scripts/install-cluster-autoscaler.sh` installs CA wired to this
  node group's ASG (needs the node/IRSA role to allow `autoscaling:*Describe*` +
  `SetDesiredCapacity` + `TerminateInstanceInAutoScalingGroup`). Karpenter is the better
  high-tens choice (bin-packs mixed instance sizes, faster) but is a larger change.
- **Lean on scale-to-zero:** idle tenants cost nothing when scaled down
  (`scripts/tenant-scale.sh <id> down`). Wire the dashboard/reaper to auto-scale-down tenants
  idle > N minutes.

## 2. Pod IP exhaustion (VPC-CNI) — THE hard wall — OPT-IN
Every pod gets a real VPC IP. A `t3.large` allows **35** pods/node by default (3 ENIs × 12 − 1).
At ~15 pods/tenant that's ~2 tenants/node, and you exhaust private-subnet CIDRs fast.
- **Fix:** enable **VPC-CNI prefix delegation** (`ENABLE_PREFIX_DELEGATION=true`) → up to **110**
  pods/node and far denser IP packing (/28 prefixes instead of one IP per pod).
  `scripts/enable-prefix-delegation.sh` sets it; **new nodes** pick it up, so drain/recycle
  nodes during a quiet window. Also confirm the private subnets have enough free CIDR space
  (widen subnets / add a secondary CIDR if not).

## 3. Shared RDS connection limits — OPT-IN
All per-tenant databases live on one RDS instance. Connections ≈ pools × SQL-services × tenants
and will exhaust `max_connections` (a `db.t3.medium` allows ~410). ~5 SQL services × a small
pool × 40 tenants blows past that.
- **Fix:** front RDS with **PgBouncer** (transaction pooling) — `k8s/pgbouncer.yaml` +
  `scripts/install-pgbouncer.sh` deploy it in `otterworks-platform`; point tenant DB URLs at
  `pgbouncer.otterworks-platform:6432`. Alternatively size the instance up. Per-tenant restricted
  DB users are future hardening (see `plan-B-consolidation.md`).

## 4. Ingress / DNS — see architecture.md §6
One ingress-nginx + one NLB handles many Ingress objects fine. Move tenants to **host-based**
wildcard routing (`*.demo.otterworks.app`) so each tenant is its own origin (no cookie/asset
collisions, no nip.io fragility). external-dns + a single wildcard TLS cert cover all tenants.

## 5. Cost + concurrency guardrails
- Enforce a **max concurrent tenants** in the dashboard checkout path (reject over the cap).
- Default a short **TTL** (8h) and rely on the reaper; expose extend in the dashboard.
- Per-tenant `ResourceQuota`/`LimitRange` already cap spend (4 CPU / 8Gi req, 40 pods).
- Track a rough cost estimate per tenant in the dashboard (nodes × on-demand-equivalent).

## 6. Control-plane durability
The DynamoDB control table has **PITR** + deletion protection, so platform state survives
tenant churn, node recycles, and cluster loss — independent of the ephemeral infra.

## Quick capacity math
| Setting | pods/node | ~tenants/node | at 20 nodes |
|---|---|---|---|
| default `t3.large` | 35 | ~2 | ~40 (IP-bound first) |
| + prefix delegation | 110 | ~7 | ~140 (node/cost-bound) |

High-tens (≈40–80 tenants) is reachable with prefix delegation + autoscaling + PgBouncer;
without prefix delegation you hit pod-IP exhaustion well before node cost becomes the limit.
