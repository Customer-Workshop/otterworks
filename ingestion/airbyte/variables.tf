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
  default     = "0 0 6 * * ? UTC"
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
  }
}
