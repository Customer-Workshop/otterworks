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

  # deploy/teardown resolve shared RDS/S3/DynamoDB coordinates by reading the
  # application Terraform state (load_infra_outputs -> `terraform output`).
  # Read-only: TF 1.9 S3 backend without a lock table performs no writes here.
  statement {
    sid       = "TerraformStateList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.terraform_state_bucket}"]
  }
  statement {
    sid       = "TerraformStateRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.terraform_state_bucket}/*"]
  }

  # deploy-tenant.sh resolves the newest image tag per service from ECR.
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid    = "EcrResolveTags"
    effect = "Allow"
    actions = [
      "ecr:DescribeImages", "ecr:DescribeRepositories",
      "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
    ]
    resources = ["arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${var.ecr_repo_prefix}/*"]
  }

  # Reaper orphan sweep enumerates all app tables/buckets to compare against the
  # control table. List* are account-level (no resource ARN).
  statement {
    sid       = "ReaperEnumerate"
    effect    = "Allow"
    actions   = ["dynamodb:ListTables", "s3:ListAllMyBuckets"]
    resources = ["*"]
  }

  # Reaper GC of per-tenant Route53 records (host-based routing). Scoped to
  # hosted-zone record changes; list actions are account-level.
  statement {
    sid    = "ReaperRoute53"
    effect = "Allow"
    actions = [
      "route53:ListHostedZonesByName", "route53:ListHostedZones",
      "route53:ListResourceRecordSets", "route53:ChangeResourceRecordSets",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "dashboard" {
  name   = "control-plane"
  role   = aws_iam_role.dashboard.id
  policy = data.aws_iam_policy_document.dashboard.json
}
