# ------------------------------------------------------------------------------
# OtterWorks OpenSearch Module (flagship replatform target)
# Amazon OpenSearch Serverless collection (type SEARCH) for search-service.
#
# Added ALONGSIDE modules/search (MeiliSearch on ECS Fargate) — the MeiliSearch
# module stays in place as the golden before-state. Every resource here is
# suffixed with var.namespace so parallel/repeated migrations never collide;
# revert with:  terraform destroy -target=module.opensearch
# ------------------------------------------------------------------------------

locals {
  # OpenSearch Serverless names must be 3-32 chars, lowercase. Namespaced.
  collection_name = "${var.project}-search-${var.namespace}"

  common_tags = {
    Module    = "opensearch"
    Project   = var.project
    Service   = "search-service"
    Namespace = var.namespace
  }
}

# --- Encryption policy (AWS-owned KMS key) ------------------------------------

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${var.project}-enc-${var.namespace}"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.collection_name}"]
      }
    ]
    AWSOwnedKey = true
  })
}

# --- Network policy (private VPC / SDK access; public disabled here) ----------

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${var.project}-net-${var.namespace}"
  type = "network"

  policy = jsonencode([
    {
      Description = "Allow API + dashboards access to the ${var.namespace} search collection"
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.collection_name}"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# --- Data access policy (least privilege: only the given principals) ----------

resource "aws_opensearchserverless_access_policy" "data" {
  name = "${var.project}-data-${var.namespace}"
  type = "data"

  policy = jsonencode([
    {
      Description = "search-service read/write on the ${var.namespace} collection"
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
          ]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DescribeCollectionItems",
            "aoss:UpdateCollectionItems",
          ]
        }
      ]
      Principal = var.data_access_principal_arns
    }
  ])
}

# --- The collection ------------------------------------------------------------

resource "aws_opensearchserverless_collection" "search" {
  name = local.collection_name
  type = "SEARCH"

  tags = local.common_tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
    aws_opensearchserverless_access_policy.data,
  ]
}
