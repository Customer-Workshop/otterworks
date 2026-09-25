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
| CI | `.github/workflows/tp-airbyte.yml` | fmt/validate on PRs; plan + apply on push to `tp-run/**` (namespace from `ingestion/airbyte/NAMESPACE`) |

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
to `var.streams`, changes `sync_cron`, opens a PR (CI lints), merges, CI applies,
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

What the dry run actually did (about 50 minutes end to end, most of it in the
Builder UI; the recording is attached to the PR):

1. Ran the legacy chain (`sftp_ingest_poll` → `parse_custbill_fixedwidth`) to get a
   real CUSTBILL drop: two files, 100 records, copybook CBCUST01 (CUST-ID X(10),
   CUST-NAME X(30), BILL-DATE 9(8), BILL-AMT 9(10)V99 implied decimal, CURRENCY X(3),
   REC-TYPE X(2)). Uploaded them to
   `s3://<landing-bucket>/demo/custbill_feed/` and minted 7-day presigned URLs —
   the bucket stays private; the connector reads over HTTPS.
2. Wrote `ingestion/airbyte/connectors/custbill_fixedwidth/manifest.yaml`:
   `IterableDecoder` (one record per line), a `ListPartitionRouter` over the feed
   URLs, a record filter that drops HDR/TRL and short lines, and `AddFields`
   slices that type each column (ISO date, decimal amount, `INVOICE`/`CREDIT`/
   `UNKNOWN`, `record_key = file:md5(record)`). Checked it locally against the
   legacy parser output first: 100/100 records identical.
3. Builder quirk hit live, as predicted: with the feed URLs declared as an
   `array` input, the test panel showed the values but never passed them to the
   manifest (`'feed_urls' is a required property`). Fix: declare the input as a
   multiline `string` and `split()` it in the partition router. Re-imported, both
   partitions returned 50 typed records in the test panel, published as
   `ow-tp-custbill-fixedwidth` v1.
4. Terraform: `airbyte_source_custom` (definition id of the published connector is
   a non-secret default in `variables.tf`; the presigned URLs come in via
   `TF_VAR_custbill_feed_urls`) plus an `airbyte_connection` to the existing
   Databricks destination. Plan was 2 to add / 0 to change / 0 to destroy; apply
   took under a minute.
5. Two API-triggered syncs: 2m32s and 1m16s, 100 rows each. Databricks recount of
   `ow_tp.airbyte_demo.custbill_records` matched the legacy parser exactly (100 rows,
   82 invoices / 18 credits, GBP 37 / USD 35 / EUR 28, amount sum 510391.14).
   Recon: `docs/tech-partnerships/recon/airbyte-custbill-fixedwidth.recon.json`.

Caveats to say out loud: the copybook has no invoice id, so none is emitted (the
prompt's "invoice id" is a wish, not a field); presigned URLs expire after 7 days,
so a repeat run needs fresh ones in `TF_VAR_custbill_feed_urls`.

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

### Closer — the Fivetran comparison (3 min)

Prompt:

> Migrate the Fivetran Google Sheets connector to Airbyte.

Fivetran has an API and a Terraform provider too; this beat is not "Fivetran
can't". It is the same point as the rest of the track: the pipeline ends up as
reviewable code in this repo, with a recon report, rather than as clicks in a
vendor console. What the pre-run actually found and did:

**Read from the Fivetran UI** (read-only, recorded): two Google Sheets
connections against the `OtterWorks billing export (demo)` sheet. `g_sheets.demo`
is active — User OAuth, the whole sheet by URL plus one named range
(`NamedRange1`), every 6 hours, Fivetran naming, destination `Warehouse` =
Databricks (catalog `ow_tp`, warehouse `565cd2fd713738c4`), last sync
successful in 56 s but **0 rows loaded** and "no schema to configure". The
second connection (`google_sheets.demo`) was left paused and incomplete. Fivetran's
Google Sheets connector loads one named range as one table, so a sheet with two
tabs needs two ranges (and here, effectively, two connections).

**Maps 1:1 to `ingestion/airbyte/gsheets.tf`:** spreadsheet URL →
`configuration.spreadsheet_id`; 6-hourly schedule → `cron_expression =
"0 0 0/6 * * ? UTC"`; Databricks destination → the existing
`airbyte_destination_databricks.lakehouse` (schema `airbyte_demo`, no DDL);
"Fivetran naming" → `names_conversion = true` (snake_case headers).

**Does not map 1:1:**

- *Auth.* Fivetran's User OAuth is a browser flow with no code artefact. Airbyte
  also offers Google OAuth in its UI, so the live source was authorised there,
  then `terraform import`ed. Airbyte masks the resulting credentials on read, so
  the resource ignores `configuration` after creation and the auth block is a
  variable (`TF_VAR_google_sheets_credentials`: service-account JSON *or* OAuth
  client + refresh token). A service-account key is the path that is fully
  declarative end to end.
- *Named range vs tabs.* Airbyte reads every tab as a stream; the connection
  selects `customers` and `invoices` explicitly. There is no named-range concept.
- *Duplicate headers.* The `customers` tab has `cust_id`/`cust_no`/`cust_name`
  twice. Airbyte disambiguates them by cell (`cust_id_A1`, `cust_id_G1`, …)
  and still lands all 50 rows. Fivetran's 0-row load was not investigated
  further — the trial estate was left untouched — so treat that as unverified.
- *State.* The Terraform module is the source of truth for the Airbyte side;
  the Fivetran connector stays configured only in Fivetran.

Evidence: `docs/tech-partnerships/recon/airbyte-gsheets-demo.recon.json` (two
API-triggered syncs, 50 + 200 rows recounted in Databricks after each,
`idempotency_rerun` performed) and the side-by-side screenshots on the PR.
Tooling: `ingestion/airbyte/tools/gsheets_sync_and_recon.py --ns demo
--connection-id <id>`.

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
