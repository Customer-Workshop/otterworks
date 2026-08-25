data "mongodbatlas_advanced_cluster" "target" {
  project_id = var.project_id
  name       = var.cluster_name
}

resource "random_password" "namespace" {
  for_each = toset(var.namespaces)

  length  = 32
  special = false
}

resource "mongodbatlas_database_user" "namespace" {
  for_each = toset(var.namespaces)

  project_id         = var.project_id
  username           = "ow_tp_mongodb_${each.key}"
  password           = random_password.namespace[each.key].result
  auth_database_name = "admin"

  roles {
    role_name     = "readWrite"
    database_name = "ow_tp_mongodb_${each.key}"
  }

  roles {
    role_name     = "dbAdmin"
    database_name = "ow_tp_mongodb_${each.key}"
  }

  roles {
    role_name     = "readWrite"
    database_name = "ow_tp_mongodb_${each.key}_quarantine"
  }

  roles {
    role_name     = "dbAdmin"
    database_name = "ow_tp_mongodb_${each.key}_quarantine"
  }

  scopes {
    name = var.cluster_name
    type = "CLUSTER"
  }
}

resource "mongodbatlas_project_ip_access_list" "managed" {
  for_each = var.access_entries

  project_id = var.project_id
  ip_address = each.value.ip_address
  comment    = each.value.comment
}
