# These workspace objects pre-date this stack and are shared with other demos.
# They are data sources only: managing them as resources would let a stray
# terraform apply or terraform destroy delete another demo's estate.

data "databricks_catalog" "shared" {
  name = var.catalog
}

data "databricks_schema" "bronze" {
  name = "${var.catalog}.bronze"
}

data "databricks_schema" "silver" {
  name = "${var.catalog}.silver"
}

data "databricks_schema" "gold" {
  name = "${var.catalog}.gold"
}

data "databricks_volume" "landing" {
  name = "${var.catalog}.bronze.landing"
}

data "databricks_sql_warehouse" "shared" {
  id = var.warehouse_id
}
