variable "project_id" {
  description = "MongoDB Atlas project ID."
  type        = string
}

variable "cluster_name" {
  description = "Pre-existing Atlas cluster name. This stack reads it but never manages it."
  type        = string
  default     = "otterworks-demo"
}

variable "namespaces" {
  description = "Namespaces for which Atlas database users and databases are managed."
  type        = list(string)
  default     = ["demo"]
}

variable "access_entries" {
  description = "Project IP access-list entries managed by this stack."
  type = map(object({
    ip_address = string
    comment    = string
  }))
  default = {
    vm_egress = {
      ip_address = "140.232.64.3"
      comment    = "otterworks-tp track=mongodb namespace=demo"
    }
  }
}
