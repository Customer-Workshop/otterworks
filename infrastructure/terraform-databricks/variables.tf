variable "databricks_host" {
  description = "Databricks workspace URL; set DATABRICKS_HOST in the environment."
  type        = string
  default     = null
  sensitive   = true
}

variable "databricks_token" {
  description = "Databricks PAT; set DATABRICKS_TOKEN in the environment."
  type        = string
  default     = null
  sensitive   = true
}

variable "warehouse_id" {
  description = "Existing serverless SQL warehouse used by managed SQL tables."
  type        = string
  default     = "565cd2fd713738c4"
}

variable "sftp_host" {
  description = "Fixture SFTP host stored in the ow_tp scope."
  type        = string
  default     = "127.0.0.1"
  sensitive   = true
}

variable "sftp_user" {
  description = "Fixture SFTP user stored in the ow_tp scope."
  type        = string
  default     = "mainframe"
  sensitive   = true
}

variable "sftp_password" {
  description = "Fixture or customer SFTP password; set TF_VAR_sftp_password."
  type        = string
  sensitive   = true
}

variable "finance_recipients" {
  description = "Workflow failure notification recipients."
  type        = list(string)
  default     = ["finance-reports@otterworks.dev"]
}
