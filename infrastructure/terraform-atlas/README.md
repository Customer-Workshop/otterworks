# MongoDB Atlas shared stack

This is the parent/orchestrator-owned Terraform stack for the MongoDB migration
run. It manages only namespace database users and explicitly owned project
access-list entries. The pre-existing `otterworks-demo` Atlas cluster is read
through a data source and is never created, modified, paused, upgraded, or
destroyed here.

Migration children must not run `terraform apply` or `terraform destroy` from
this directory. They must not edit the project access list or manage database
users outside their assigned namespace.

## Usage

Set the Atlas provider credentials in the environment, copy the example
variables, and initialize locally:

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform validate
terraform apply
```

Terraform state is local to this directory. Do not commit `terraform.tfvars`
or state files. The committed `.terraform.lock.hcl` pins the provider
selections.

Retrieve a namespace password without printing other Terraform state:

```bash
terraform output -json passwords
terraform output -raw 'passwords["demo"]'
```

Terraform marks the password output sensitive, but the password is still
stored in local state because Atlas requires it for database-user management.
Protect the state file accordingly.

## Teardown proof

The parent may prove namespace teardown with:

```bash
terraform destroy
```

After destroy, verify through the Atlas API that only this stack's managed
namespace users and access-list entries disappeared. The shared cluster,
`otterworks-app`, `ow-tp-demo`, and unmanaged access-list entries must remain.
Then re-apply and confirm the configuration is clean:

```bash
terraform apply
terraform plan -detailed-exitcode
```

The final plan must exit `0`. Re-check data-plane connectivity after the
managed VM access-list entry is recreated.
