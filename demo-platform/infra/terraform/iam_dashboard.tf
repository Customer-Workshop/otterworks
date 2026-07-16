# IRSA role assumed by the dashboard web pod + runner Jobs (SA
# otterworks-platform:demo-ops-dashboard). Deliberately scoped — this is NOT the
# broad otterworks-* tenant wildcard; it grants only what the control plane needs.
data "aws_iam_policy_document" "dashboard_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:sub"
      values   = [local.dashboard_sa]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dashboard" {
  name               = "otterworks-demo-ops-dashboard-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.dashboard_trust.json
}

data "aws_iam_policy_document" "dashboard" {
  # Full control of the control table (+ any indexes).
  statement {
    sid    = "ControlTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
      "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable",
    ]
    resources = [
      aws_dynamodb_table.control.arn,
      "${aws_dynamodb_table.control.arn}/index/*",
    ]
  }

  # Reaper GC of per-tenant items in the SHARED app tables.
  statement {
    sid    = "SharedTenantDataGC"
    effect = "Allow"
    actions = [
      "dynamodb:Query", "dynamodb:Scan", "dynamodb:DeleteItem",
      "dynamodb:BatchWriteItem", "dynamodb:DescribeTable",
    ]
    resources = ["arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${var.shared_dynamodb_table_prefix}*"]
  }

  # Reaper GC of per-tenant object prefixes in the SHARED app buckets.
  statement {
    sid       = "SharedBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.shared_s3_bucket_prefix}*"]
  }
  statement {
    sid       = "SharedBucketObjectGC"
    effect    = "Allow"
    actions   = ["s3:DeleteObject", "s3:GetObject"]
    resources = ["arn:aws:s3:::${var.shared_s3_bucket_prefix}*/*"]
  }

  # Read cluster info to build a kubeconfig (k8s authz is via RBAC, see helm/).
  statement {
    sid       = "DescribeCluster"
    effect    = "Allow"
    actions   = ["eks:DescribeCluster"]
    resources = [data.aws_eks_cluster.this.arn]
  }

  # Teardown maintains IRSA trust on the shared per-service roles (add/remove the
  # tenant namespace SA). Scoped to the otterworks-* service roles only.
  statement {
    sid       = "TenantIrsaTrust"
    effect    = "Allow"
    actions   = ["iam:GetRole", "iam:UpdateAssumeRolePolicy"]
    resources = ["arn:aws:iam::${local.account_id}:role/otterworks-*"]
  }
}

resource "aws_iam_role_policy" "dashboard" {
  name   = "control-plane"
  role   = aws_iam_role.dashboard.id
  policy = data.aws_iam_policy_document.dashboard.json
}
