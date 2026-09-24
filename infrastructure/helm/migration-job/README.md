# migration-job

Owned by the **job** unit. One `batch/v1` Job per `ldm` stage (CONTRACTS.md §13.2), run in the demo
tenant namespace beside `db2-archive`. No Service, no Ingress, no probes: a Job serves nothing.

```sh
helm upgrade --install ldm-extract-r1 infrastructure/helm/migration-job -n otterworks-d24-after \
  --set namespaceToken=d24-after --set stage=extract --set runId=r20260924150000 \
  --set image.tag=<tag> --set expires=2026-10-01T00:00:00Z \
  --set env.AZSQL_SERVER=sql-otterworks-d24-after.database.windows.net \
  --set env.AZSQL_DATABASE=sqldb-otterworks-d24-after --set env.DB2_DATABASE=D24A \
  --set-file manifest.base=migration/manifest.yaml \
  --set-file manifest.overlay=migration/manifests/d24-after.yaml
kubectl -n otterworks-d24-after wait --for=condition=complete job/ldm-extract-r20260924150000
```

The image defaults to the token's own ECR repository,
`<image.registry>/<image.repositoryPrefix>/<namespaceToken>/ldm-job`; set `image.repository` to
override it entirely. Source (Db2) credentials are only read for `extract`, `purge` and `all`; `load`,
`validate` and `reconcile` can run where Db2 is unreachable (e.g. Container Apps) with only the Azure
settings present.

`/work/staging` is an `emptyDir`: it does not survive from one Job to the next. Run the stages as
separate Jobs only when `env.AZ_STORAGE_ACCOUNT` / `env.AZ_STAGING_CONTAINER` are set (extract uploads
every range to the staging container and load downloads it back); otherwise use `stage=all` so extract
and load share one pod.

Unloading defaults to the manifest `source.unload_command` (the UNLOAD01 wrapper baked into the image).
Set `env.LDM_UNLOAD_MODE=builtin` to use `ldm`'s own fixed-width writer instead.

Credentials come from Secrets `db2-archive-credentials` (`DB2_USER`, `DB2_PASSWORD`) and `ldm-azure`
(`AZSQL_USER`, `AZSQL_PASSWORD`, `AZ_STORAGE_KEY`); the chart never carries secret values. Every object
is labelled `demo/namespace`, `demo/name`, `demo/owner`, `demo/expires` and annotated
`demo/expires-at` for the reaper.
