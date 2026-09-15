# U0 shared core

Set `LAKEBASE_MIGRATION_DSN` with `lakebase_env.sh`, then deploy the Lakebase
schema:

```bash
source tools/ow_tp_u0/lakebase_env.sh
python3 tools/ow_tp_u0/deploy_lakebase.py
```

Load the local Oracle fixture at one pinned SCN:

```bash
export ORACLE_FIXTURE_DSN='ow_billing/ow_billing@localhost:52521/FREEPDB1'
python3 tools/ow_tp_u0/load_u0.py \
  --oracle-dsn-env ORACLE_FIXTURE_DSN \
  --lakebase-dsn-env LAKEBASE_MIGRATION_DSN \
  --skip-delta \
  --evidence-out .migration/recon/U0_shared_core/load_evidence.json
```

Run reconciliation:

```bash
python3 -m tools.dbx_recon_oracle run \
  --unit U0_shared_core --family oracle \
  --mapping .migration/units/U0_shared_core/mapping_spec.json \
  --tolerances .migration/03_recon_tolerances.json \
  --canonicalization /opt/.devin/plugins/cache/github.com_Cognition-Partner-Workshops_dbx-migration-plugin-5890f19a/0.2.0/skills/oracle-plsql/canonicalization.json \
  --mode fixture --source-dsn-secret ORACLE_FIXTURE_DSN \
  --target-kind lakebase --target-secret LAKEBASE_MIGRATION_DSN \
  --target-catalog databricks_postgres \
  --allowed-targets-file .migration/allowed_targets.json \
  --target-schema ow_billing \
  --ops .migration/units/U0_shared_core/tier4_ops.json \
  --depth full --out /home/ubuntu/recon_fixture/run1
```
