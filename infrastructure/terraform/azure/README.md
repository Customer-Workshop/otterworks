# Azure target — per-namespace Terraform root

Owned by the **azure** unit. Implements the Azure side of the selective legacy data
migration demo (interface: `migration/CONTRACTS.md` §11). One `terraform apply` per
namespace token (`<run>-after`) creates:

| Resource | Name | Notes |
|---|---|---|
| Resource group | `rg-otterworks-<ns>` | everything below lives here |
| SQL logical server | `sql-otterworks-<ns>` | v12, TLS 1.2, SQL admin `ldmadmin` + Entra admin = deploying SP |
| SQL database | `sqldb-otterworks-<ns>` | **GP_S_Gen5_2 serverless**, min 0.5 vCore, auto-pause 60 min, 32 GB, no ZR, local backups |
| Storage account | `stow<ns-nohyphen><hash>` | LRS, TLS 1.2, no public blob access, shared-key auth on |
| Staging container | `staging-<ns>` | private; fixed-width UNLOAD files + manifests |
| Key Vault | `kvow<ns-nohyphen><hash>` | soft delete 7 d, purge protection **off**; secrets `azsql-admin-user/-password`, `azsql-reader-user/-password`, `staging-storage-key` |
| User-assigned identity | `id-otterworks-<ns>` | attached to SQL server, both apps and the job |
| Log Analytics | `log-otterworks-<ns>` | 30 d, Container Apps logs |
| Container Apps env | `cae-otterworks-<ns>` | Consumption workload profile |
| Container App | `ca-report-<ns>` / `ca-audit-<ns>` | external HTTPS ingress, `ARCHIVE_STORE=azuresql`, outputs `report_fqdn` / `audit_fqdn` |
| Container Apps job | `caj-ldm-<ns>` | manual trigger, 1 replica, 3600 s, env + secrets per CONTRACTS §8 |
| (private mode) | `vnet-otterworks-<ns>`, private endpoints + DNS zones | see below |

Every resource that supports tags carries `namespace, owner=otterworks-demo,
demo=legacy-data-migration, expires, run_token, state`. `terraform destroy` removes all of
it; `az resource list --tag namespace=<ns>` must return nothing afterwards.

## Prerequisites

* Terraform >= 1.6, `az` CLI, and for `apply_target_sql=true` (default)
  [go-sqlcmd](https://github.com/microsoft/go-sqlcmd) on `PATH` (or docker; docker mode
  applies the DDL but cannot create the managed-identity SQL user).
* Service principal auth through the standard `ARM_*` variables:

  ```bash
  export ARM_CLIENT_ID="$AZURE_CLIENT_ID" ARM_CLIENT_SECRET="$AZURE_CLIENT_SECRET" \
         ARM_TENANT_ID="$AZURE_TENANT_ID"   ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID"
  ```

  `ARM_CLIENT_SECRET` is also what `scripts/apply-sql.sh` uses to log in to the database as
  the Entra admin. Nothing here ever prints or outputs a secret.
* A fresh registry token for the Container Apps image pulls (ECR tokens live 12 h):
  `export TF_VAR_registry_password="$(aws ecr get-login-password --region us-east-1)"`.

## Commands (the deploy script runs exactly these)

```bash
NS=d24-after; RUN=${NS%-*}; STATE=${NS##*-}
cd infrastructure/terraform/azure

# separate state per namespace: only the key changes
terraform init -reconfigure -input=false \
  -backend-config="resource_group_name=rg-meridian-tfstate" \
  -backend-config="storage_account_name=stmeridiantfstate7c2e" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=otterworks/${NS}/terraform.tfstate"

terraform fmt -check -recursive && terraform validate

terraform plan -input=false -out="${NS}.plan" \
  -var namespace="$NS" -var run_token="$RUN" -var state="$STATE" \
  -var expires="$(date -u -d '+3 days' +%Y-%m-%dT%H:%M:%SZ)" \
  -var 'eks_egress_cidrs=["<NAT EIP>/32"]' \
  -var report_image=<ecr>/otterworks/report-service:<tag> \
  -var audit_image=<ecr>/otterworks/audit-service:<tag> \
  -var job_image=<ecr>/otterworks/ldm-job:<tag> \
  -var session_links_json='[{"label":"...","url":"https://..."}]'

terraform apply -input=false "${NS}.plan"          # ~12-15 min (Container Apps env dominates)
terraform output                                   # report_fqdn, audit_fqdn, sql_server_fqdn, ...

terraform destroy -input=false -auto-approve -var ... (same -var set)   # ~15-20 min
az resource list --tag namespace="$NS" -o table    # must print nothing
```

Passing the same `-var`s to `destroy` is required because validation runs on destroy
too; a `<ns>.tfvars` file (kept out of git) is the convenient way to do it.

### Post-apply SQL (`apply_target_sql`, default `true`)

`null_resource.sql_init` runs `scripts/apply-sql.sh` after the database and firewall exist:

1. `migration/target/sql/*.sql` in file order (idempotent, creates `mig`/`stg`/`arch`,
   ledger, rejects, purge audit, `ldm_report_reader`);
2. contained SQL user `ldmreader` (password in Key Vault) as `ldm_report_reader` — the
   report/audit Container Apps connect with it;
3. `CREATE USER [id-otterworks-<ns>] FROM EXTERNAL PROVIDER` (falls back to `WITH SID`
   when the server cannot query Entra) + `db_datareader`, `db_datawriter`, `db_ddladmin`.

The machine running Terraform gets a temporary SQL firewall rule for its public IP
(auto-detected, or set `deployer_cidrs`). It re-runs whenever the DDL files change.
`ldm init` (job unit) applies the same files, so `-var apply_target_sql=false` is safe
when neither sqlcmd nor a public SQL endpoint is available — schemas then appear on the
first job run.

## Cost

* **SQL serverless auto-pauses after 60 min idle**: compute cost drops to zero and only
  storage (≤ 32 GB) is billed. The first connection after a pause takes 30–60 s to resume;
  `apply-sql.sh` and the `ldm` stages retry on error 40613. Set `auto_pause_delay_in_minutes`
  to `-1` only for the talk if wake-up latency matters.
* Container Apps run on the **Consumption** profile: the report/audit apps scale 1→1 (they
  are demo pages, `min_replicas = 1` keeps them warm), the job costs nothing until executed.
* Log Analytics 30 d retention, storage LRS, Key Vault standard: cents per day.
* `expires` is an absolute UTC timestamp; the reaper (ops unit) destroys anything past it.

## Networking modes

**Public (default, `private_networking=false`)** — the decision recorded in
`migration/README.md`: Db2 has no public endpoint, so the migration Job runs in the EKS
tenant namespace and reaches Azure SQL over its public FQDN. Terraform creates one SQL
firewall rule per `eks_egress_cidrs` entry (the NAT gateway EIPs), `AllowAzureServices`
(0.0.0.0) so the Container Apps job/apps can connect, and a temporary rule for the
deployer while `apply_target_sql` runs. Storage and Key Vault keep public endpoints with
TLS 1.2 and no anonymous access.

**Private (`-var private_networking=true`)** — `vnet-otterworks-<ns>` (10.60.0.0/16 by
default) with a `/23` subnet delegated to `Microsoft.App/environments` and a `/24` for
private endpoints; private endpoints + `privatelink.*` DNS zones for SQL, blob and Key
Vault; `public_network_access_enabled=false` on SQL and storage. Key Vault keeps its
public endpoint but with `default_action=Deny` and an IP allow-list of the deployer
(`deployer_cidrs`, or the auto-discovered apply-machine IP) — Terraform writes the secrets
over the data plane, so a fully private vault would fail the apply. The Container Apps environment
is placed in the delegated subnet (its ingress stays external so the presenter can still
open the report). No SQL firewall rules are created and `sql_init` is skipped (the deployer
cannot reach the private endpoint) — run `ldm init` from inside the environment instead,
or use `run_job_in_azure=true`. In this mode the EKS Job cannot reach SQL at all; the
Container Apps job must run LOAD/VALIDATE/RECONCILE from the staging container.

The vault allow-list is whatever IP applied last, so a later `apply`/`destroy` from a
different machine (e.g. the scheduled reaper) is denied on the secret data plane. Either
pass stable egress CIDRs with `-var 'deployer_cidrs=["<cidr>"]'` on every run, or refresh
the ACL first: `terraform apply -target=azurerm_key_vault.this <same -var flags>` and then
`terraform destroy`. Public mode is unaffected.

Both modes pass `terraform validate` and `terraform plan` (28 vs 36 resources).

## RBAC (`manage_rbac`, default `false`)

Role assignments need `Microsoft.Authorization/roleAssignments/write`, which a
Contributor-only principal (the demo subscription SP) does not have. With the default the
Key Vault uses **access policies** (deployer: secrets get/list/set/delete/purge/recover;
identity: get/list) and the job reads the staging container with the storage key that is
already in its secrets. Set `manage_rbac=true` with an Owner/UAA principal to get the
CONTRACTS variant: Key Vault RBAC mode, `Key Vault Secrets Officer/User` and
`Storage Blob Data Reader` on the container for the identity.

## Region

`location` defaults to `eastus2` (contract). At verification time this subscription was
**refused Azure SQL server provisioning in East US 2 and East US** (`ProvisioningDisabled`
/ `RegionDoesNotAllowProvisioning`); `centralus` and `westus2` accepted it. Pass
`-var location=centralus` (all resources move together) or open a quota request.

ARM in `centralus` intermittently returned `404 ResourceNotFound` for the SQL database
(and once for a Container App) a few seconds after creation, while `az sql db show`
reported it `Online`. This is read-after-write lag, not a missing resource: re-run
`terraform apply` (untaint `azurerm_mssql_database.this` first if it was marked tainted);
the second pass converges without recreating anything.

## Files

| File | Content |
|---|---|
| `versions.tf` | terraform / provider pins, partial `azurerm` backend, provider features |
| `variables.tf` | contract inputs + validation (`namespace == "${run_token}-${state}"` in `locals.tf`) |
| `locals.tf` | names, tag map, firewall map, DDL hash |
| `main.tf` | RG, identity, storage, Key Vault + secrets, SQL server/db/firewall |
| `network.tf` | private-mode VNet, subnets, private endpoints, DNS |
| `containerapps.tf` | environment, report/audit apps, migration job |
| `sql-init.tf` + `scripts/apply-sql.sh` | post-apply DDL, reader user, identity user |
| `outputs.tf` | contract outputs (`report_fqdn`, `audit_fqdn`, `sql_server_fqdn`, …); no secrets |
