locals {
  collection_name = "${var.project}-search-${var.namespace}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    Module      = "opensearch"
    Namespace   = var.namespace
  }
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${local.collection_name}-encryption"
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

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${local.collection_name}-network"
  type = "network"
  policy = jsonencode([
    {
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

resource "aws_opensearchserverless_collection" "this" {
  name       = local.collection_name
  type       = "SEARCH"
  depends_on = [aws_opensearchserverless_security_policy.encryption, aws_opensearchserverless_security_policy.network]
  tags       = local.common_tags
}

resource "aws_opensearchserverless_access_policy" "data" {
  name = "${local.collection_name}-data"
  type = "data"
  policy = jsonencode([
    {
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
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems",
          ]
        }
      ]
      Principal = var.principal_arns
    }
  ])
}
