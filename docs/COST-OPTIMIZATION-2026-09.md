# Cost optimization — September 2026 rebuild

Account spend had crept to roughly **$290/month (~$10.50/day)** for a platform
serving one perpetual tenant plus one ephemeral one. Everything was torn down
and rebuilt from Terraform with the changes in this PR. This note records what
existed before the teardown and what the minimal footprint is now.

## 1. What existed (August 2026, us-east-1)

Cost Explorer, 2026-08-01..2026-09-01, unblended:

| $/month | Service | What it was |
|--------:|---------|-------------|
| 90.56 | EC2 compute | `t3.xlarge` SPOT managed node (24/7) + a Karpenter `c5a.xlarge` launched for the second tenant |
| 74.10 | EKS | `otterworks-dev` control plane, Kubernetes 1.34 (standard support) |
| 27.73 | EC2-Other | EBS root volumes (60Gi gp3 per Karpenter node), public IPv4 |
| 21.83 | VPC | Public IPv4 charges; a NAT gateway in a separate demo VPC in us-east-2 |
| 16.83 | CloudWatch | EKS control-plane logs (`api`, `audit`, `authenticator`, never-expire group), 30-day app log groups |
| 16.68 | ELB | One NLB for the shared ingress-nginx controller |
| 15.68 | RDS | `otterworks-postgres-dev`, `db.t3.micro` |
| 12.60 | ElastiCache | `otterworks-redis-dev`, `cache.t3.micro` — **unused**: tenants run Redis in-cluster |
| 6.99 | KMS | CMKs for SNS/SQS/CloudWatch |
| 2.72 | ECS | Fargate MeiliSearch — **unused**: tenants run MeiliSearch in-cluster |
| ~3 | Secrets Manager, Route 53, S3, Lambda, ECR | legitimate |

Resources present at teardown time:

- Terraform states in `s3://otterworks-terraform-state`: `platform/`,
  `otterworks/` (application layer), `demo-platform/`.
- EKS `otterworks-dev` with managed node group `default` (1 × `t3.xlarge` SPOT)
  and Karpenter NodePool `tenants` (1 × `c5a.xlarge` SPOT).
- Helm releases: the 13 golden-app services in two tenant namespaces
  (`otterworks-main` and one ephemeral tenant), `ingress-nginx`, `cert-manager`,
  `karpenter`, `demo-platform` (ops dashboard + reaper).
- Application layer: RDS, ElastiCache, ECS MeiliSearch, 3 S3 buckets, DynamoDB
  tables, SNS/SQS, Cognito, IRSA roles, CloudWatch log groups.
- Demo control plane: DynamoDB control table, provisioner IAM user, GitHub
  Actions OIDC role, budget, Route 53 records under `otterworks.app`.
- us-east-2 (not managed from this repo): `devin-outpost-vpc-demo` VPC with a
  NAT gateway, `t4g.nano` instance and two EIPs.

## 2. What changed

| Change | Where | Saving |
|---|---|---|
| Shared ElastiCache Redis and ECS MeiliSearch are now opt-in (`enable_shared_cache`, `enable_shared_search`, default `false`). Tenants already run both in-cluster. | `infrastructure/terraform` | ~$15/mo |
| EKS control-plane logging reduced to `api` + `audit`; log group pre-created with 7-day retention instead of never-expire | `platform/terraform/modules/eks` | ~$10/mo |
| Application log retention 30 → 7 days | `infrastructure/terraform` | small |
| Managed node group ceiling 3 → 2, cheaper SPOT types (`m5a`, `t3a`) added to the pool | `platform/terraform/environments/dev.tfvars` | caps blast radius |
| Karpenter pool ceiling 400 vCPU / 1600Gi → 32 vCPU / 128Gi; node root volume 60 → 30Gi | `demo-platform/k8s/karpenter/nodepool.yaml` | ~$2/node/mo, hard stop |
| S3 buckets `force_destroy` so `terraform destroy` completes without manual emptying | `infrastructure/terraform/modules/storage` | operational |
| Budget alarm 700 → 200 USD/month | `demo-platform/infra/terraform` | alerting |
| Every resource tagged `creator = partner-workshops` via provider `default_tags` (all three roots) and the Karpenter `EC2NodeClass` | all roots | attribution |

Steady state after the rebuild is one `xlarge` SPOT node running the platform
add-ons plus the perpetual `t-main` tenant, one NLB, one `db.t3.micro`, and the
EKS control plane — roughly **$130–150/month**, with Karpenter adding SPOT
capacity only while additional workshop tenants are awake.

## 3. Rebuild order

```
terraform -chdir=platform/terraform apply -var-file=environments/dev.tfvars
terraform -chdir=infrastructure/terraform apply -var="db_password=..."
terraform -chdir=demo-platform/infra/terraform apply
./scripts/tenant-platform-baseline.sh          # ingress-nginx (one NLB), reaper
demo-platform/scripts/install-karpenter.sh     # Karpenter + NodePool
ACME_EMAIL=... ISSUER=letsencrypt-prod ./scripts/enable-dns-tls.sh   # external-dns, cert-manager, wildcard cert
helm upgrade --install demo-platform demo-platform/helm/demo-platform ...   # ops dashboard + reaper v2 (see chart README)
./scripts/deploy-tenant.sh main --ttl never --host-suffix otterworks.app
```

Gotchas hit during the September 2026 rebuild:

- **Register the perpetual tenant in the control table before (or immediately
  after) `deploy-tenant.sh main`.** `deploy-tenant.sh` does not write a
  `TENANT#<id>/META` item; the reaper v2 orphan sweep GCs any
  `otterworks-<id>` namespace without one, including `main`, and then drops its
  database. Put an item with `persistent: true` (the dashboard "persist" action
  does this) and wait for any in-flight reaper Job to finish first — a running
  reaper deletes the item at the end of its own GC pass.
- The `/aws/eks/<cluster>/cluster` log group and the
  `otterworks/dev/dashboard/passcode` secret both linger after a destroy (never
  expire / 30-day recovery window). Delete or import them before re-applying.
- A KMS key scheduled for deletion cannot decrypt a restored Secrets Manager
  secret; force-delete the secret and let Terraform recreate it.

Tear down with `scripts/teardown-cluster.sh` (drains load balancers first) and
then `scripts/teardown-dev.sh --all`.
