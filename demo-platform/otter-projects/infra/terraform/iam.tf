# IRSA role for the otter-projects web pod + poller CronJob. Grants access to
# the projects table only — nothing else in the account.
data "aws_iam_policy_document" "trust" {
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
      values   = [local.app_sa]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "otterworks-otter-projects-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

data "aws_iam_policy_document" "app" {
  statement {
    sid    = "ProjectsTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
      "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable",
    ]
    resources = [
      aws_dynamodb_table.projects.arn,
      "${aws_dynamodb_table.projects.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "otter-projects-table"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}
