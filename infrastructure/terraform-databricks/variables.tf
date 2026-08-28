variable "ns" {
  description = "Namespace for this migration run."
  type        = string
  default     = "demo"
}

variable "catalog" {
  description = "Pre-existing Unity Catalog catalog."
  type        = string
  default     = "ow_tp"
}

variable "warehouse_id" {
  description = "Pre-existing serverless SQL warehouse ID."
  type        = string
  default     = "565cd2fd713738c4"
}

variable "notebook_root" {
  description = "Parent-owned workspace root for migration notebooks."
  type        = string
  default     = "/Shared/ow_tp"
}

variable "landing_path" {
  description = "Pre-existing managed volume path for migration landings."
  type        = string
  default     = "/Volumes/ow_tp/bronze/landing"
}

variable "secret_scope" {
  description = "Pre-existing Databricks secret scope."
  type        = string
  default     = "ow_tp"
}
