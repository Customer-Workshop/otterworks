# 07 — Access checklist

Evidence below records the commands actually run and their output. Secret values are
never printed or stored. The Oracle container was reused and remains running.

## Probe 1 — Oracle read as `OW_BILLING`: WORKS

**Command:**

```sh
docker exec -i otterworks-oracle-billing-oracle-billing-1 bash -lc "sqlplus -s ow_billing/ow_billing@localhost:1521/FREEPDB1" <<'SQL'
SET PAGESIZE 100
SET HEADING ON
SELECT COUNT(*) AS customer_master_count FROM customer_master;
SELECT COUNT(*) AS v_sql_count FROM v$sql;
EXIT;
SQL
```

**Actual output:**

```text
CUSTOMER_MASTER_COUNT
---------------------
		25000


V_SQL_COUNT
-----------
	173
```

This proves a source read and one of the D10-1 targeted surfaces. The shared-pool count
is volatile; the settled post-grant intake verification recorded `524`
(`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:59-70`).

## Probe 2 — Databricks warehouse query: WORKS

The current run base does not contain `scripts/tp_databricks/dbx.py`; the helper was
executed from the merged reference branch without adding it to this commit. The helper
uses the existing serverless warehouse and falls back to the `DATABRICKS_DEMO_*`
environment variables (`origin/tech-partnerships-solutions:scripts/tp_databricks/dbx.py:9-19,99-107,127-159`).

**Command:**

```sh
git show origin/tech-partnerships-solutions:scripts/tp_databricks/dbx.py > /tmp/ow_tp_dbx_setup_probe.py
DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" \
DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" \
python /tmp/ow_tp_dbx_setup_probe.py sql "SELECT 1 AS probe_value"
```

**Actual output:**

```text
1
```

No cluster or other compute was created.

## Probe 3 — Prefixed target-catalog scratch write: WORKS

No Terraform command was run. The table was prefixed, namespace-scoped, and dropped in
the same probe:

```sh
DBX='python /tmp/ow_tp_dbx_setup_probe.py'
DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" $DBX sql "CREATE TABLE IF NOT EXISTS ow_tp.bronze.ow_tp_setup_probe_demo (ns STRING, probe_value STRING) USING DELTA"
DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" $DBX sql "INSERT INTO ow_tp.bronze.ow_tp_setup_probe_demo VALUES ('demo', 'setup-ok')"
DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" $DBX sql "SELECT ns, probe_value FROM ow_tp.bronze.ow_tp_setup_probe_demo WHERE ns = 'demo' AND probe_value = 'setup-ok'"
DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" $DBX sql "DROP TABLE ow_tp.bronze.ow_tp_setup_probe_demo"
```

**Actual output:**

```text
-- create --

-- insert --
1	1
-- read --
demo	setup-ok
-- drop --
```

## Access-model one-pager

| Tier | Status and access model |
|---|---|
| Assessment principal | **PROPOSED** — metadata/read-only access to the in-scope Oracle schema and target metadata. |
| Migration principal | **PROPOSED** — sandbox write plus legacy read-only scoped to in-scope schemas; no legacy DDL/DML and no production-catalog grants. |
| Cutover principal | **PROPOSED** — customer-held production repoint rights, used once at STOP E. |
| Secret names | **PROPOSED** — assessment: `DATABRICKS_DEMO_HOST`, `DATABRICKS_DEMO_TOKEN`; migration: `DATABRICKS_DEMO_HOST`, `DATABRICKS_DEMO_TOKEN`, plus only approved `ow_tp` secret keys; cutover: customer-held repoint credential name. Values are never documented. |
| Attribution | **FACT** — activity must be attributable per session through the customer's own audit tables; the unified audit surface is readable after D10-1, but no observation window is authorized (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:178-224`). |

STOP A proposals to raise: confirm PII masking/least privilege, confirm the existing
serverless warehouse identity, and confirm the migration principal's exact legacy
read-only scope. Do not reopen D4-2 as a gate.
