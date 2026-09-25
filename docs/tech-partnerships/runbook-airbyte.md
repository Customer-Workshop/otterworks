# Demo Runbook — Airbyte Cloud + Devin: ingestion pipelines as code

**Duration:** ~20 minutes on stage.
**Story:** OtterWorks' legacy billing estate (the Oracle `CUSTOMER_MASTER` /
`INVOICE_*` tables behind the 1998 CUSTBILL chain) has to land in the lakehouse.
With a GUI-driven ingestion tool that is a person clicking through forms. With
Airbyte every source, destination, connection, stream and mapper is an API
object with an official Terraform provider, so the pipeline becomes code Devin
can write, review, apply, operate — and then open the familiar Airbyte screen to
show you it worked.

The pre-run (this PR) leaves one working pipeline behind. Every live beat is a
*change* to it, prompted from Slack or Jira the same way as the other tracks.

## What exists before the demo (`NS=demo`)

| Layer | Object | Where it comes from |
|---|---|---|
| Landing | `s3://ow-tp-airbyte-demo-landing-<acct>/demo/<table>/<table>.csv` + `manifest.json` (row counts, sha256) | `make tp-airbyte-land NS=demo` exports the Oracle estate; Airbyte Cloud cannot reach the on-VM database, so S3 is the reachable edge |
| Airbyte source | `ow-tp-airbyte-demo-billing-landing` (S3, one CSV stream per table) | `ingestion/airbyte/pipeline.tf` |
| Airbyte destination | `ow-tp-airbyte-demo-lakehouse` (Databricks, OAuth2 service principal `ow_tp_airbyte_demo`) | `ingestion/airbyte/pipeline.tf` |
| Airbyte connection | `ow-tp-airbyte-demo-billing` — `customer_master`, `invoice_header`, `entity_attr_value`; full refresh; daily 06:00 UTC | `ingestion/airbyte/pipeline.tf` |
| Bronze | `ow_tp.airbyte_demo.<table>` | landed by Airbyte |
| Evidence | `docs/tech-partnerships/recon/airbyte-ingest-demo.recon.json` | `make tp-airbyte-sync NS=demo` (two syncs, target-recomputed counts) |
| CI | `.github/workflows/tp-airbyte.yml` | plan on PR (posted as a comment), apply on push to `tp-run/**` |

`invoice_line` is exported to S3 but deliberately **not** in the connection: it
is beat 1.

Expected counts for `demo`: `customer_master` 25,000 · `invoice_header` 18,750 ·
`entity_attr_value` 8,333 · `invoice_line` 150,000 (37 orphaned lines — the
legacy estate's own data problem, which surfaces once beat 1 lands it).

## Demo flow

Beat 0 is you talking; beats 1, 2 and 4 are one prompt each; beat 3 is live if
time allows, otherwise the recording.

### Beat 0 — "this already exists" (2 min, no prompt)

Show the pre-run PR (Terraform module, workflow, recon JSON) and the green
connection in Airbyte Cloud. Point: nobody clicked through a wizard; the PR *is*
the pipeline definition, and the recon JSON is the proof it matches the source.

### Beat 1 — add a stream (5 min)

Prompt:

> Add INVOICE_LINE to the billing Airbyte connection as an incremental stream, hourly. Verify the sync in the Airbyte UI and post the row count.

What Devin does: adds `invoice_line = { sync_mode = "incremental_append", cursor_field = [...] }`
to `var.streams`, changes `sync_cron`, opens a PR (CI comments the plan), applies,
triggers a sync via the API, opens the connection in Airbyte Cloud and screenshots
the stream table and job status into the PR, reruns recon (150,000 rows, 37
orphans now visible in `planted_anomaly_detections`).

Contrast: in a GUI tool this is a stream toggle plus a schedule dropdown that
nobody reviews and nobody can diff.

### Beat 2 — bulk policy change (4 min)

Prompt:

> Hash the customer email and phone columns on every billing connection before they land in Databricks.

What Devin does: adds `mappers` (`hashing`, SHA-256) to the `customer_master`
stream in Terraform, one PR, apply, then opens the connection's **Mappings** tab
in the Airbyte UI to show the configured mappers, and queries Databricks to show
hashed values. Point: one reviewed change, applied to however many connections
match; a GUI tool is N edits.

### Beat 3 — custom connector (6 min, or the recording)

The legacy estate also emits a fixed-width billing feed from the ksh/Perl batch
chain that no off-the-shelf connector reads. Prompt:

> Build an Airbyte connector for the CUSTBILL fixed-width drop and add it as a source.

Devin writes a low-code connector manifest, uses the Connector Builder test panel
in the browser (a GUI-only step — the right use of the browser), publishes it to
the workspace, and wires it into Terraform as a custom source. This is the beat a
closed GUI tool cannot do at all. It is also the longest and the one most likely to
hit a builder quirk live, so the fallback is the pre-recorded run.

### Beat 4 — break it, let Devin fix it (4 min)

You, in Airbyte Cloud on stage: open the S3 source and replace the AWS secret
key with garbage, then trigger a sync. It fails; the failure email/Slack alert
arrives. Prompt:

> The billing sync just failed. Find out why, fix it, rerun it, confirm it's green.

What Devin does: reads the failed job through `GET /v1/jobs/<id>`, sees the S3
`config_error`, notices the source drifted from Terraform (`terraform plan` shows
the credential diff), re-applies (Terraform is the source of truth, so the fix is
"re-apply", not "edit the secret by hand"), reruns the sync, screenshots the green
job in the UI, posts the recon.

### Optional closer — the Fivetran comparison (3 min)

Only if a real Fivetran trial connector exists (Google Sheets → any free
destination, fed by the `OtterWorks billing export (demo)` sheet). Prompt:

> Migrate the Fivetran Google Sheets connector to Airbyte.

Devin reads the connector configuration from the Fivetran UI (no API-first path
there), writes the equivalent `airbyte_source_google_sheets` + connection in
Terraform, applies, and shows both UIs side by side. Skip it rather than fake it.

## Where the browser fits

Devin creates everything via Terraform/API and then uses the browser to *verify
and show*: connection status and stream table after each apply, the Mappings tab
in beat 2, the Connector Builder test panel in beat 3, the failed job page in
beat 4. It never uses the GUI as the primary way to create a pipeline — that is
the thing being replaced.

## Operator commands

```
make tp-up tp-seed NS=demo                 # legacy Oracle estate (see .agents/skills/oracle-billing-estate)
make tp-airbyte-init NS=demo               # terraform init against ow-tp/airbyte/demo.tfstate
make tp-airbyte-apply NS=demo              # S3 landing + IAM reader + Airbyte source/destination/connection
make tp-airbyte-land NS=demo               # Oracle -> CSV -> S3 (+ manifest.json)
make tp-airbyte-sync NS=demo               # sync, rerun, recount in Databricks, write recon JSON
make tp-validate-recon FILE=docs/tech-partnerships/recon/airbyte-ingest-demo.recon.json
```

Environment: `AIRBYTE_WORKSPACE_ID`, `AIRBYTE_CLIENT_ID`, `AIRBYTE_CLIENT_SECRET`
(Airbyte Cloud → Settings → Applications), `DATABRICKS_DEMO_HOST`,
`DATABRICKS_DEMO_TOKEN` (recon queries), `TF_VAR_databricks_client_id` /
`TF_VAR_databricks_client_secret` (the destination's OAuth2 service principal),
AWS credentials for the landing bucket and Terraform state. CI uses the
`ow-tp-airbyte-github-actions` OIDC role (`ingestion/airbyte/ci-role/`), passed as
the `AWS_TP_ROLE_ARN` repository secret.

## Gotchas found in the pre-run

- The Databricks destination wants a bare hostname. Passing the workspace URL
  with `https://` produced `Failed to connect to server: https://https:443`.
  `main.tf` strips the scheme.
- Airbyte's Databricks destination (4.x, OSS JDBC driver) failed to authenticate
  with a personal access token (`default auth: cannot configure default
  credentials ... auth_type=pat`) even though the same token worked against the
  REST API. An OAuth2 service principal (the documented recommendation) works.
  The principal needs `CAN_USE` on the warehouse and `USE_CATALOG`,
  `CREATE_SCHEMA`, `CREATE_TABLE`, `CREATE_VOLUME`, `MODIFY`, `SELECT`,
  `READ_VOLUME`, `WRITE_VOLUME` on `ow_tp`.
- The schema Airbyte creates is owned by the service principal; grant
  `USE_SCHEMA`/`SELECT` on `ow_tp.airbyte_<ns>` to whoever runs recon.
- The connections API echoes `cursor_field = ["_ab_source_file_last_modified"]`
  and a cron with a trailing ` UTC`; the module states both so `terraform plan`
  stays empty between beats.
- A demo-scale sync (three tables, ~52k rows) takes 3–5 minutes on Airbyte
  Cloud. Trigger it, then narrate the PR while it runs.
