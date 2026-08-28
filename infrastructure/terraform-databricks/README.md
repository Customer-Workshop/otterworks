# OW_BILLING Databricks shared foundation

This stack is parent-owned. It references the existing shared Databricks
catalog, schemas, managed volume, secret scope, and serverless SQL warehouse;
it does not create or destroy them. State is parent-local: there is no backend
block, and no state files may be committed.

Children add exactly one file, `jobs_<unit>.tf`, and nothing else. Children
never run `terraform apply` or `terraform destroy`; the parent owns shared
state and application.

## Workspace and compute rules

- Shared catalog, schema, volume, secret-scope, and warehouse objects are
  referenced as data sources only.
- Never use `databricks_cluster` or any hourly-cost resource.
- Compute is the pinned serverless SQL warehouse or serverless notebook tasks.
- Jobs are named `ow_tp_<unit>`.
- Every job takes an `ns` parameter.
- Volume paths are `<ns>/<unit>/...`.
- Child jobs consume this stack's outputs instead of hardcoding shared values.

Provider authentication is supplied by the `DATABRICKS_HOST` and
`DATABRICKS_TOKEN` environment variables. Invocation may map the demo
credentials to those names; credentials and host values must never be written
to files.

Format and validate without applying:

```sh
terraform fmt -check
terraform init -backend=false
terraform validate
```

Never run `terraform apply` or `terraform destroy` from a child branch.
