variable "aws_region" {
  description = "AWS region for the isolated report Lambda resources"
  type        = string
  default     = "us-east-2"
}

variable "namespace" {
  description = "Suffix used to isolate every report Lambda resource"
  type        = string
  default     = "ea3c"
}

variable "lambda_jar_path" {
  description = "Path to the flat Lambda deployment JAR"
  type        = string
  default     = "../../../services/report-service/target/report-service-lambda.jar"
}

variable "lambda_memory" {
  description = "Lambda memory allocation in MB"
  type        = number
  default     = 2048
}

variable "analytics_service_url" {
  description = "Analytics service URL used while generating reports"
  type        = string
  default     = "http://analytics-service:8088"
}

variable "audit_service_url" {
  description = "Audit service URL used while generating reports"
  type        = string
  default     = "http://audit-service:8090"
}

variable "auth_service_url" {
  description = "Auth service URL used by report-service"
  type        = string
  default     = "http://auth-service:8081"
}
