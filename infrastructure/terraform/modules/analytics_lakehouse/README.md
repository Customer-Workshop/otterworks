# analytics_lakehouse

RE-ARCHITECT target for `analytics-service` persistence: an **S3 data lake in
Apache Iceberg table format**, cataloged in **AWS Glue** and queried with
**Amazon Athena**.

This module is **additive and fully namespaced** (`var.namespace`). It never
replaces the durable PostgreSQL "before" and touches **no shared/`main`
resource**: it reuses the existing analytics data-lake bucket (from the
`storage` module) under a dedicated `iceberg-<ns>/` warehouse prefix, so the app
stays wired through the same `analytics.s3.data-lake-bucket` config it already
exposes.

## Resources (all suffixed with `-<ns>`)

- `aws_glue_catalog_database` — Iceberg catalog database `otterworks_analytics_<ns>`.
- `aws_glue_catalog_table` — the `analytics_events` Iceberg table (Iceberg v2).
- `aws_athena_workgroup` — namespaced workgroup, results to the bucket below.
- `aws_s3_bucket` (+ public-access-block, SSE, 14-day lifecycle) — Athena query results.
- `aws_iam_policy` — least-privilege Glue/Athena/S3 access, scoped to exactly this
  namespace's database, table, workgroup, warehouse prefix, and results bucket.

## Wiring

Enabled from the root module by `enable_analytics_lakehouse = true` (default
`false`). When enabled, the root attaches `iam_policy_arn` to the existing
`analytics-service` IRSA role via a new `aws_iam_role_policy_attachment` (the
role resource itself is untouched). `scripts/deploy-dev.sh` passes the Glue
database, Athena workgroup, and results location to the service, and the config
flip `ANALYTICS_REPOSITORY_BACKEND=iceberg` selects the lakehouse adapter.

## Revert (one command)

```
terraform destroy -target=module.analytics_lakehouse
```

plus dropping the `ANALYTICS_REPOSITORY_BACKEND=iceberg` config flip. The
PostgreSQL "before" is unaffected throughout.
