variable "namespace" {
  description = "Run namespace (NS=<ns>); scopes the S3 prefix, Airbyte names, and Databricks schema."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z0-9]{1,31}$", var.namespace))
    error_message = "namespace must be 1-31 lowercase alphanumerics (it is embedded in S3 bucket and schema names)."
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "airbyte_workspace_id" {
  description = "Airbyte Cloud workspace UUID."
  type        = string
}

variable "airbyte_client_id" {
  type      = string
  sensitive = true
}

variable "airbyte_client_secret" {
  type      = string
  sensitive = true
}

variable "databricks_host" {
  description = "Workspace host (with or without https://)."
  type        = string
  sensitive   = true
}

variable "databricks_client_id" {
  description = "OAuth2 application (client) ID of the ow_tp_airbyte_<ns> service principal."
  type        = string
  sensitive   = true
}

variable "databricks_client_secret" {
  type      = string
  sensitive = true
}

variable "databricks_warehouse_id" {
  description = "Existing serverless SQL warehouse; the module never creates compute."
  type        = string
  default     = "565cd2fd713738c4"
}

variable "databricks_catalog" {
  type    = string
  default = "ow_tp"
}

variable "sync_cron" {
  description = "Quartz cron for the billing connection (Airbyte uses 6-7 field Quartz syntax)."
  type        = string
  default     = "0 0 * * * ? UTC"
}

variable "custbill_definition_id" {
  description = "Workspace definition UUID of the custom CUSTBILL fixed-width connector (published from the Connector Builder as ow-tp-custbill-fixedwidth v1). Not a secret; the default is the demo workspace's definition."
  type        = string
  default     = "002e525a-c47b-4d04-86d3-f5c166608bb9"
}

variable "custbill_feed_urls" {
  description = "HTTPS URLs of the CUSTBILL fixed-width feed files (presigned S3 URLs under <ns>/custbill_feed/), one per line. Supplied via TF_VAR_custbill_feed_urls, never committed."
  type        = string
  sensitive   = true
}

variable "streams" {
  description = "Legacy billing tables landed under s3://<bucket>/<ns>/<table>/ and how each is synced."
  type = map(object({
    sync_mode    = string
    primary_key  = optional(list(string), []) # required for *_deduped modes
    cursor_field = optional(list(string), [])
  }))
  default = {
    customer_master   = { sync_mode = "full_refresh_overwrite" }
    invoice_header    = { sync_mode = "full_refresh_overwrite" }
    entity_attr_value = { sync_mode = "full_refresh_overwrite" }
    # Lines arrive as new files; dedup on line_id, cursor is the S3 file mtime.
    invoice_line = { sync_mode = "incremental_deduped_history", primary_key = ["line_id"] }
  }
}

variable "google_sheets_spreadsheet_url" {
  description = "Share link of the billing export spreadsheet (same sheet the Fivetran connector read)."
  type        = string
  default     = "https://docs.google.com/spreadsheets/d/1OiNyOfHhBBDy0xyTBWduyo8kSnjMQOjPFSmJEfToF80"
}

variable "google_sheets_tabs" {
  description = "Spreadsheet tabs landed as streams (one Databricks table each)."
  type        = list(string)
  default     = ["customers", "invoices"]
}

variable "google_sheets_credentials" {
  description = <<-EOT
    Google auth for the Sheets source, from env only (TF_VAR_google_sheets_credentials).
    Either a service-account JSON, or the OAuth client + refresh token that Airbyte's
    consent flow produced. Only read when the source is CREATED; a source that was
    authorised in the Airbyte UI and imported needs none of it (see gsheets.tf).
    The provider requires every OAuth attribute to be non-null even for an imported
    source, so the defaults are the literal marker "import-only". Creating a source
    with that marker fails Airbyte's connection check at apply time instead of
    producing a source that cannot read the sheet (see the check block in gsheets.tf).
  EOT
  type = object({
    service_account_json = optional(string)
    oauth_client_id      = optional(string, "import-only")
    oauth_client_secret  = optional(string, "import-only")
    oauth_refresh_token  = optional(string, "import-only")
  })
  validation {
    condition = (
      var.google_sheets_credentials.service_account_json != null
      || alltrue([for v in [var.google_sheets_credentials.oauth_client_id, var.google_sheets_credentials.oauth_client_secret, var.google_sheets_credentials.oauth_refresh_token] : v == "import-only"])
      || alltrue([for v in [var.google_sheets_credentials.oauth_client_id, var.google_sheets_credentials.oauth_client_secret, var.google_sheets_credentials.oauth_refresh_token] : v != "import-only"])
    )
    error_message = "OAuth needs oauth_client_id, oauth_client_secret and oauth_refresh_token together (or use service_account_json)."
  }
  default   = {}
  sensitive = true
}

variable "gsheets_sync_cron" {
  description = "Quartz cron for the Google Sheets connection; every 6 hours, matching the Fivetran schedule."
  type        = string
  default     = "0 0 0/6 * * ? UTC"
}
