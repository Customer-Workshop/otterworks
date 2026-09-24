# Legacy data migration demo — presenter runbook

Selective migration of the document-retention-history slice (`DOCARCH`, `FILEAUD`,
`RETNPLCY`) from Db2 (container on EKS standing in for Db2 for z/OS) to Azure SQL
Database. Db2 stays the system of record; the point of the demo is **proving which
source rows are safe to delete** and producing a row-by-row reconciliation.

Binding interfaces (tokens, names, tags, stage CLI, exit codes): `migration/CONTRACTS.md`.
Architecture and stage semantics: `migration/README.md`. This page is the operator view.

## 1. What runs where

| Token | Namespace | Db2 database | Azure | Serves retention history from |
|---|---|---|---|---|
| `d24-before` | `otterworks-d24-before` | `D24B` | none | Db2 (`ARCHIVE_STORE=db2`) |
| `d24-after` | `otterworks-d24-after` | `D24A` (validated rows purged) | `rg-otterworks-d24-after` | Azure SQL (`ARCHIVE_STORE=azuresql`) |

Both tenants are ordinary OtterWorks tenants (`scripts/deploy-tenant.sh`) behind the shared
ingress: `https://t-<token>.otterworks.app` (web) and `https://api-t-<token>.otterworks.app`.
The AFTER tenant has `PEER_APP_URL=https://t-d24-before.otterworks.app` so the admin
dashboard can deep-link the same document in the BEFORE copy.

**Networking (decided, do not re-open).** Db2 is a StatefulSet in the tenant namespace with
no public endpoint. The migration therefore runs as Kubernetes Jobs *in the same namespace*
and reaches Azure SQL over its **public endpoint**; Terraform creates an Azure SQL firewall
rule for the EKS NAT egress IPs (`deploy-demo.sh` discovers them and passes
`eks_egress_cidrs`). `EXTRACT` and `PURGE` always run beside Db2 on EKS. `LOAD`, `VALIDATE`
and `RECONCILE` run on EKS by default; with `execution.run_job_in_azure: true` in the
overlay they run as executions of the Container Apps job `caj-ldm-<token>` reading the
staging container instead. Private networking (VNet + private endpoint) is behind
`private_networking` (`AZURE_PRIVATE_NETWORKING=true`), default **off**.

Everything created carries `namespace=<token> owner=otterworks-demo demo=legacy-data-migration
expires=<UTC timestamp>` (cloud tags) and `demo/namespace`, `demo/name`,
`app.kubernetes.io/part-of=otterworks-ldm` (Kubernetes labels). Terraform state is per
token: AWS `otterworks/demo/<token>/terraform.tfstate` in `otterworks-terraform-state`,
Azure `otterworks/<token>/terraform.tfstate` in the `TFSTATE_AZ_*` storage account.

## 2. Prerequisites (presenter workstation or CI runner)

Tools: `aws`, `kubectl`, `helm`, `terraform >= 1.7`, `jq`, `az` (AFTER only), `openssl`, and
for the AFTER token [go-sqlcmd](https://github.com/microsoft/go-sqlcmd) on `PATH` (falls back
to `docker run mcr.microsoft.com/mssql-tools`, which cannot grant the managed identity - Entra
auth - so prefer go-sqlcmd).

```bash
aws sts get-caller-identity                      # account 599083837640
aws eks update-kubeconfig --name otterworks-dev --region us-east-1
export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id otterworks/dev/rds/master \
  --region us-east-1 --query SecretString --output text | jq -r .password)
# AFTER token only:
export AZURE_CLIENT_ID=... AZURE_CLIENT_SECRET=... AZURE_TENANT_ID=... AZURE_SUBSCRIPTION_ID=...
export TFSTATE_AZ_ACCOUNT=<storage account> TFSTATE_AZ_RESOURCE_GROUP=<rg> TFSTATE_AZ_CONTAINER=tfstate
```

The scripts run `az login --service-principal` themselves and export the `ARM_*`
equivalents for Terraform. No secret value is ever printed; Kubernetes Secrets are applied
from stdin, never from argv. The one exception the Azure CLI forces is `az login
--service-principal -p <secret>` (it accepts a client secret only on argv); it runs once per
process and is skipped when the CLI is already logged in to the right subscription. Follow-up:
switch `.github/workflows/demo-reaper.yml` to `azure/login` with OIDC to remove it entirely.

The Db2 chart (`infrastructure/helm/db2-archive`), migration-job chart
(`infrastructure/helm/migration-job`) and Azure root (`infrastructure/terraform/azure`) are
owned by other units; `deploy-demo.sh` refuses to start (exit 3) with a "not found (owned by
the … unit)" message if they are missing from the branch.

## 3. Reset from a clean account

```bash
make demo-verify-clean NS=d24-before   # both must exit 0 before you start
make demo-verify-clean NS=d24-after
```

If either reports survivors, `make demo-destroy NS=<token>` first (section 7).

## 4. Bring up both deployments

```bash
make demo-up NS=d24-before TTL=72h
make demo-up NS=d24-after  TTL=72h
```

`demo-up` = `scripts/deploy-demo.sh up <token>`; it validates the token
(`^[a-z][a-z0-9]{1,11}-(before|after)$`, never `main`) before touching anything and runs:

1. **aws terraform (demo-aws)** — `infrastructure/terraform/demo-aws`: gp3 20 GiB EBS volume
   for Db2 in the node group's AZ (static PV, the cluster never provisions AWS resources),
   S3 bucket `otterworks-ldm-<token>-<account>`, ECR repo `otterworks-demo/<token>/ldm-job`.
2. **deploy-tenant** — the golden app via `scripts/deploy-tenant.sh <token> --ttl … --host-suffix …`,
   then the demo labels and `demo/expires` annotation on the namespace, and the S3 prefix `<token>/`.
3. **db2 seed** — Secret `db2-archive-credentials` (generated once, reused on re-run), Helm
   release `db2-archive` with `dbName=D24B|D24A` and the static PV, then the seed (chart
   hook when the chart exposes `seed:`, otherwise `migration/source/seed/load.sh`).
   The seed is idempotent (skip when SHA-256s already match).
4. **wiring (db2)** — Secret `archive-store-credentials` (`ARCHIVE_STORE=db2`, `DB2_*`,
   `LDM_S3_*`) fed to `report-service`, `audit-service`, `admin-dashboard`.
5. **azure terraform apply** (only when the overlay `migration/manifests/<token>.yaml` has
   `azure: true`) — per-token backend key, a generated var file
   `.demo/<token>/azure.auto.tfvars.json` (no secrets; git-ignored), NAT egress CIDRs,
   ECR pull credentials for the Container Apps copies of Report/Audit, plan + apply.
6. **wiring (azuresql)** — reads the SQL credential from Key Vault, writes Secrets
   `archive-store-credentials` (`ARCHIVE_STORE=azuresql`, `AZSQL_*`, `AZ_*`, `PEER_APP_URL`)
   and `ldm-azure`, restarts the three services, installs the migration-job chart *without*
   starting a stage, and runs `ldm init` (schema + MIG-06 prior-run fixture).

It ends with the hostnames and a per-stage timing table; the full transcript is
`.demo/<token>/deploy-<ts>.log`. Rehearse without credentials: `DRY_RUN=1 make demo-up NS=…`.

Expected (measured on a clean account; fill in your numbers from the timing table):

| Stage | d24-before | d24-after |
|---|---|---|
| aws terraform (demo-aws) | ~1 min | ~1 min |
| deploy-tenant | 6–10 min | 6–10 min |
| db2 seed (5.3 M rows) | 20–35 min | 20–35 min |
| azure terraform apply | — | 8–12 min (SQL server + ACA env dominate) |
| wiring | < 1 min | 1–2 min |

Run the two `demo-up`s in parallel terminals; the whole reset is bounded by the Db2 seed.

## 5. Run the migration (AFTER only)

```bash
make demo-migrate NS=d24-after RUN_ID=r$(date -u +%Y%m%d%H%M%S)
```

Refuses `migrate: false` overlays (so it can never run against `d24-before`). For each
stage `extract → load → validate → purge → reconcile` it renders one `batch/v1` Job
`ldm-<stage>-<run_id>` from the migration-job chart (or triggers the Container Apps job for
`load`/`validate`/`reconcile` when `run_job_in_azure: true`), streams the log, and stops
with that stage's exit code (contract §9.4). On success it copies `report.html`,
`report.csv`, `report.json` into `.demo/d24-after/<run_id>/` (from the staging container
when Azure is configured, otherwise from the admin API). Transcript:
`.demo/d24-after/migrate-<run_id>-<ts>.log`.

Expected counts (contract §14 / SEED-SPEC): `RETNPLCY` 40/40/40/0/0,
`DOCARCH` 180 000 / 179 980 / 179 963 / 179 963 / 37, `FILEAUD` 620 000 / 620 000 /
619 995 / 619 995 / 5 (extracted / loaded / validated / purged / failed). All seven failure
classes MIG-01…MIG-07 must appear in the failed-row section. Typical wall time 10–20 min;
`extract` and `load` dominate.

## 6. What to click

1. Open `https://t-d24-before.otterworks.app` and `https://t-d24-after.otterworks.app` side
   by side; log in as the demo admin in both.
2. Open the **same archived document** (pick a `DOC_ID` from the report's validated set)
   in both. Identical retention history and audit-trail values; the AFTER footer shows the
   store as *Azure SQL*, the BEFORE footer *Db2*.
3. Admin dashboard → **Migration report** in AFTER: one row per source table with
   extracted/loaded/validated/purged/failed; expand **Failed rows** — source key, rejection
   rule, SQLSTATE or conversion error. Point out MIG-07: table-level storage-charge totals
   agree, the per-retention-class totals do not, so those rows were *not* purged.
4. Click **Export CSV** — same content as `.demo/d24-after/<run_id>/report.csv`.
5. Show that a failed row (e.g. a MIG-05 orphan `FILEAUD` event) is **still in the AFTER Db2**
   copy while a validated one is gone: only fully validated rows are purge-safe.
6. Footer links: the Devin sessions that produced each unit (`migration/sessions/*.yaml`).

## 7. Destroy

```bash
make demo-destroy NS=d24-after
make demo-destroy NS=d24-before
```

`scripts/demo-destroy.sh <token>` (transcript `.demo/<token>/destroy-<ts>.log`):

1. Azure: `terraform destroy` with the per-token backend when the state blob or resource
   group exists (falls back to `az group delete` when the Terraform root is unavailable).
2. Helm: delete `ldm-*` Jobs, uninstall `db2-archive` and any `otterworks-ldm` releases,
   remove the static PV.
3. Tenant: the existing `scripts/teardown-tenant.sh <token>` (namespace, tenant database,
   IRSA trust).
4. AWS: `aws s3 rm s3://…/<token>/ --recursive`, `terraform destroy` of `demo-aws`; tagged
   survivors (EBS volume, ECR repo, bucket) are deleted directly as a backstop.
5. **Verify** and exit non-zero on any survivor:
   `aws resourcegroupstaggingapi get-resources --tag-filters Key=namespace,Values=<token>`
   empty, `az resource list --tag namespace=<token>` empty, `az group exists` false,
   `kubectl get ns otterworks-<token>` NotFound, no PV labelled `demo/namespace=<token>`, and the tenant database
   `otterworks_<token>` absent on RDS (probed by a short in-cluster `psql` Job; needs
   `DB_PASSWORD`).

Verification refuses to certify - exits non-zero - when it *cannot* check something it
should: an Azure-backed token (`azure: true` or any `-after` token without an overlay)
with no `AZURE_*` credentials, or `DB_PASSWORD` unset. "Skipped" never counts as clean.

`make demo-verify-clean NS=<token>` runs step 5 alone. Typical destroy: 5–8 min
(before), 10–15 min (after; SQL server deletion is the long pole).

## 8. Reaper

`scripts/demo-reaper.sh` (default `--dry-run`) lists AWS (Resource Groups Tagging API),
Azure (`az resource list` / `az group list`) and cluster namespaces tagged
`demo=legacy-data-migration`, groups them by `namespace`, and — with `--apply` — runs
`demo-destroy.sh` for every token whose `expires` (+ grace, default 15 m) is in the past.
Tokens with a malformed `namespace` tag are reported and skipped, never destroyed. A token
with some expired and some live resources is skipped until everything has expired.
`.github/workflows/demo-reaper.yml` runs it hourly with `--apply` (AWS OIDC via
`AWS_ROLE_ARN`, Azure via the `AZURE_*` / `TFSTATE_AZ_*` repository secrets) and uploads the
transcripts. `make demo-reaper` (report) / `make demo-reaper APPLY=1`.

For the talk, deploy with `TTL=72h`; the reaper removes both tenants afterwards without
anyone remembering to.

## 9. Cost notes

- AWS: one gp3 20 GiB volume (~$1.60/month), S3 unload files (< 5 GB, 7-day lifecycle),
  ECR (10-image lifecycle). The tenant itself runs on the shared SPOT node group; Db2 needs
  about 2 vCPU / 4 GiB while seeding.
- Azure (AFTER only): SQL serverless GP 2 vCore auto-pauses after 60 min idle (compute
  ~$0.50/vCore-hour while active, storage ~$0.12/GB-month); Container Apps environment
  consumption plan (Report/Audit copies scale to zero); storage account + Key Vault are cents.
  A 72 h window with a couple of hours of active use is well under $50.
- Both deployments stay up for the talk; destroy immediately afterwards (section 7) or let
  the reaper do it.

## 10. Evidence checklist

Copy from `.demo/<token>/` into `docs/demos/evidence/<token>/` (or attach to the PR):

- `deploy-<ts>.log` for both tokens (includes the timing table and Terraform apply output)
- the Azure Terraform apply output inside `deploy-<ts>.log` (`d24-after`; no plan file is written because it would embed the ECR pull credential)
- `migrate-<run_id>-<ts>.log`, `<run_id>/report.html`, `<run_id>/report.csv`
- `destroy-<ts>.log` from a **throwaway** token (`<initials>1-after`) showing the clean
  verification — never from `d24-*` before the talk, never `main`
- screen recording of section 6; hostnames of both deployments; session links
