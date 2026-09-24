variable "namespace" {
  description = "Namespace token <run>-<state>, e.g. d24-after (CONTRACTS.md §3.1)."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,11}-(before|after)$", var.namespace))
    error_message = "namespace must match ^[a-z][a-z0-9]{1,11}-(before|after)$."
  }
  validation {
    condition     = var.namespace != "main" && !startswith(var.namespace, "main-")
    error_message = "namespace main / main-* is never used for demo resources."
  }
}

variable "run_token" {
  description = "RUN part of the token (namespace without -<state>)."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,11}$", var.run_token))
    error_message = "run_token must match ^[a-z][a-z0-9]{1,11}$."
  }
}

variable "state" {
  description = "before or after. Ops never applies this module with before."
  type        = string
  validation {
    condition     = contains(["before", "after"], var.state)
    error_message = "state must be before or after."
  }
}

variable "location" {
  description = "Azure region for every resource."
  type        = string
  default     = "eastus2"
}

variable "owner" {
  description = "Owner tag value; fixed by contract."
  type        = string
  default     = "otterworks-demo"
  validation {
    condition     = var.owner == "otterworks-demo"
    error_message = "owner must be otterworks-demo."
  }
}

variable "expires" {
  description = "Absolute UTC expiry timestamp YYYY-MM-DDTHH:MM:SSZ written to the expires tag; the reaper destroys the namespace after this."
  type        = string
  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$", var.expires))
    error_message = "expires must be an absolute UTC timestamp like 2026-09-27T15:00:00Z."
  }
}

variable "private_networking" {
  description = "true: VNet, private endpoints for SQL + storage + Key Vault, Container Apps environment inside the VNet, public network access disabled. false (default): public endpoints guarded by firewall rules."
  type        = bool
  default     = false
}

variable "eks_egress_cidrs" {
  description = "CIDRs the Kubernetes migration Job egresses from (NAT gateway EIPs /32 or node public IPs). One SQL firewall rule each. May be empty only when private_networking is true."
  type        = list(string)
  validation {
    condition     = alltrue([for c in var.eks_egress_cidrs : can(cidrhost(c, 0))])
    error_message = "every eks_egress_cidrs entry must be a valid IPv4 CIDR."
  }
}

variable "report_image" {
  description = "Full image reference for the Azure-facing report-service Container App."
  type        = string
}

variable "audit_image" {
  description = "Full image reference for the Azure-facing audit-service Container App."
  type        = string
}

variable "job_image" {
  description = "Full image reference for the ldm migration job (Container Apps job)."
  type        = string
}

variable "run_job_in_azure" {
  description = "Informational: whether ops runs LOAD/VALIDATE/RECONCILE on the Container Apps job. The job is provisioned either way; this only sets a tag and LDM_RUN_IN_AZURE on the job."
  type        = bool
  default     = false
}

variable "registry_server" {
  description = "Container registry hosting the three images."
  type        = string
  default     = "599083837640.dkr.ecr.us-east-1.amazonaws.com"
}

variable "registry_username" {
  description = "Registry username (AWS for an ECR token)."
  type        = string
  default     = "AWS"
}

variable "registry_password" {
  description = "Registry password (fresh ECR token supplied by ops at apply time). Stored as a Container Apps secret, never output."
  type        = string
  sensitive   = true
}

variable "session_links_json" {
  description = "JSON array of {label,url} passed to the Container Apps as LDM_SESSION_LINKS."
  type        = string
  default     = "[]"
  validation {
    condition     = can(jsondecode(var.session_links_json))
    error_message = "session_links_json must be valid JSON."
  }
}

variable "apply_target_sql" {
  description = "Run migration/target/sql/*.sql and the managed-identity user grant against the database at apply time (needs sqlcmd or docker on the machine running Terraform, and a public SQL endpoint reachable from it). ldm init applies the same files, so this only makes schemas exist right after apply."
  type        = bool
  default     = true
}

variable "manage_rbac" {
  description = "Create Azure role assignments (Key Vault in RBAC mode, Storage Blob Data Reader for the identity). Requires Owner / User Access Administrator on the deploying principal; with Contributor only (the demo subscription) leave false: Key Vault uses access policies and the migration job reads staging with the storage key."
  type        = bool
  default     = false
}

variable "deployer_cidrs" {
  description = "Extra CIDRs allowed through the SQL firewall for the machine that runs terraform apply (needed by apply_target_sql when not private). Empty: the deployer's public IP is discovered at plan time."
  type        = list(string)
  default     = []
}

variable "vnet_address_space" {
  description = "Address space of the VNet created when private_networking is true."
  type        = string
  default     = "10.90.0.0/16"
}
