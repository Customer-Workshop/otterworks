# Google Sheets -> Databricks. Migrated from the Fivetran trial connector
# (Google Sheets, User OAuth, one spreadsheet, 6-hourly schedule) into the
# same Terraform module and Databricks destination as the rest of the estate.
#
# The live source was authorised through Airbyte Cloud's Google OAuth consent
# flow and imported into state. Airbyte masks source configuration on read (the
# provider stores none of it after import) and never hands the refresh token
# back, so `configuration` is only sent on create -- from env via
# var.google_sheets_credentials -- and is ignored on later plans. Without this
# every plan after an import would try to PUT a credential-less configuration.
# Spreadsheet or auth changes on the live source go through the Airbyte UI/API,
# and this block is updated to match.

locals {
  gsheets_credentials = (
    var.google_sheets_credentials.service_account_json != null
    ? { service_account_key_authentication = { service_account_info = var.google_sheets_credentials.service_account_json } }
    : {
      authenticate_via_google_o_auth = {
        client_id     = var.google_sheets_credentials.oauth_client_id
        client_secret = var.google_sheets_credentials.oauth_client_secret
        refresh_token = var.google_sheets_credentials.oauth_refresh_token
      }
    }
  )
}

resource "airbyte_source_google_sheets" "billing_export" {
  name         = "${local.prefix}-billing-export-gsheets"
  workspace_id = var.airbyte_workspace_id

  configuration = {
    spreadsheet_id   = var.google_sheets_spreadsheet_url
    names_conversion = true
    credentials      = local.gsheets_credentials
  }

  lifecycle {
    ignore_changes = [configuration]
  }
}

resource "airbyte_connection" "gsheets" {
  name           = "${local.prefix}-billing-export-gsheets"
  source_id      = airbyte_source_google_sheets.billing_export.source_id
  destination_id = airbyte_destination_databricks.lakehouse.destination_id

  namespace_definition                 = "destination"
  non_breaking_schema_updates_behavior = "propagate_columns"

  schedule = {
    schedule_type   = "cron"
    cron_expression = var.gsheets_sync_cron
  }

  configurations = {
    streams = [
      for tab in var.google_sheets_tabs : {
        name      = tab
        sync_mode = "full_refresh_overwrite"
      }
    ]
  }
}
