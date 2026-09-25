# CUSTBILL fixed-width feed (copybook CBCUST01) from the ksh/Perl batch chain.
# No off-the-shelf connector reads it, so the workspace carries a custom
# low-code connector (connectors/custbill_fixedwidth/manifest.yaml, published
# from the Connector Builder). Terraform owns the source and the connection.

resource "airbyte_source_custom" "custbill_fixedwidth" {
  name          = "${local.prefix}-custbill-fixedwidth"
  workspace_id  = var.airbyte_workspace_id
  definition_id = var.custbill_definition_id

  configuration = jsonencode({
    feed_urls = var.custbill_feed_urls
  })
}

resource "airbyte_connection" "custbill" {
  name           = "${local.prefix}-custbill"
  source_id      = airbyte_source_custom.custbill_fixedwidth.source_id
  destination_id = airbyte_destination_databricks.lakehouse.destination_id

  namespace_definition                 = "destination"
  non_breaking_schema_updates_behavior = "propagate_columns"

  schedule = {
    schedule_type   = "cron"
    cron_expression = var.sync_cron
  }

  configurations = {
    streams = [
      {
        name        = "custbill_records"
        sync_mode   = "full_refresh_overwrite"
        primary_key = [["record_key"]]
      }
    ]
  }
}
