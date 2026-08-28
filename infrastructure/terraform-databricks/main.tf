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

# The Databricks provider exposes secret scopes as a resource, not a data
# source. Use a read-only API lookup through the external data source instead
# so the pre-existing scope remains outside Terraform resource management.
data "external" "secret_scope" {
  program = [
    "sh",
    "-c",
    <<-SCRIPT
      set -eu
      host="$${DATABRICKS_HOST%/}"
      response="$(curl --fail --silent --show-error \
        --header "Authorization: Bearer $${DATABRICKS_TOKEN:?DATABRICKS_TOKEN must be set}" \
        "$host/api/2.0/secrets/scopes/list")"
      printf '%s' "$response" | python3 -c 'import json, sys; d = json.load(sys.stdin); name = "${var.secret_scope}"; print(json.dumps({"scope_name": name, "scope_exists": str(any(s.get("name") == name for s in d.get("scopes", []))).lower()}))'
    SCRIPT
  ]
}
