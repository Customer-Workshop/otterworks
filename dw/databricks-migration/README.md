# Databricks migration scaffold

This directory is the target-side scaffold for the warehouse migration demo.
It converts exactly one asset: `mart.returns_rate_by_category`.

## Current execution mode

This run uses **local Spark + Delta fallback mode**. No Databricks workspace host
is available in this environment. The local landing zone is
`/home/ubuntu/dwdemo/lakehouse` by default and can be changed with
`DW_LAKEHOUSE_ROOT`.

The extractor reads the legacy Postgres stand-in using `DW_POSTGRES_DSN` and
writes Delta directories named after their source tables. The converted
PySpark implementation reads those Delta tables and writes
`mart__returns_rate_by_category`.

## Workspace deployment

With a real workspace, set `DATABRICKS_HOST` and authentication as required by
the Databricks CLI, then run:

```bash
databricks bundle validate -t development
databricks bundle deploy -t development
databricks bundle run -t development returns-rate-by-category
```

The bundle's job cluster and source paths are already workspace-shaped; only
the workspace authentication and environment-specific cluster settings need to
be supplied. The Postgres DSN and lakehouse root should be provided as
workspace job environment configuration rather than local defaults.
