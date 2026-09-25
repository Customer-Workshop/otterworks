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

  # Every feed URL must be an HTTPS object URL in this run's landing bucket
  # under <ns>/custbill_feed/, and there must be at least one. Rejects an unset
  # secret (which would full-refresh the target to empty), another namespace's
  # files, and any host other than the landing bucket.
  lifecycle {
    precondition {
      condition = length(local.custbill_feed_url_list) > 0 && alltrue([
        for u in local.custbill_feed_url_list :
        can(regex("^https://${aws_s3_bucket.landing.bucket}\\.s3([.-][a-z0-9-]+)?\\.amazonaws\\.com/${var.namespace}/custbill_feed/[^/?]+\\.dat(\\?.*)?$", u))
      ])
      error_message = "custbill_feed_urls must be one or more presigned HTTPS URLs for objects under s3://${aws_s3_bucket.landing.bucket}/${var.namespace}/custbill_feed/*.dat."
    }
  }
}

locals {
  # Same whitespace split as the connector's partition router (config['feed_urls'].split()).
  custbill_feed_url_list = [for u in regexall("\\S+", var.custbill_feed_urls) : u]
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
