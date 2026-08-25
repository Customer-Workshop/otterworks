output "cluster_standard_srv" {
  description = "The pre-existing Atlas cluster's standard SRV connection string."
  value       = data.mongodbatlas_advanced_cluster.target.connection_strings[0].standard_srv
}

output "database_names" {
  description = "Managed application and quarantine database names by namespace."
  value = {
    for namespace in var.namespaces : namespace => {
      application = "ow_tp_mongodb_${namespace}"
      quarantine  = "ow_tp_mongodb_${namespace}_quarantine"
    }
  }
}

output "usernames" {
  description = "Managed Atlas database usernames by namespace."
  value = {
    for namespace in var.namespaces : namespace => "ow_tp_mongodb_${namespace}"
  }
}

output "passwords" {
  description = "Managed Atlas database passwords by namespace."
  sensitive   = true
  value = {
    for namespace in var.namespaces : namespace => mongodbatlas_database_user.namespace[namespace].password
  }
}
