# DNS/TLS is gated behind enable_dns until otterworks.app is registered in
# Route53. Once the domain exists, `terraform apply -var enable_dns=true` creates
# the hosted zone (if managing it here) and an IRSA role that external-dns +
# cert-manager (DNS-01) use to manage records for *.demo.otterworks.app.
#
# NOTE: domain *registration* (route53domains register-domain) is a manual,
# contact-info + ICANN-verification step done out of band; this only manages the
# hosted zone + DNS automation IAM.

resource "aws_route53_zone" "demo" {
  count = var.enable_dns ? 1 : 0
  name  = var.dns_zone_name

  tags = {
    Name = var.dns_zone_name
  }
}

data "aws_iam_policy_document" "dns_trust" {
  count = var.enable_dns ? 1 : 0
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringLike"
      variable = "${local.oidc_url}:sub"
      values = [
        "system:serviceaccount:external-dns:external-dns",
        "system:serviceaccount:cert-manager:cert-manager",
      ]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dns" {
  count              = var.enable_dns ? 1 : 0
  name               = "otterworks-demo-dns-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.dns_trust[0].json
}

data "aws_iam_policy_document" "dns" {
  count = var.enable_dns ? 1 : 0
  statement {
    effect    = "Allow"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = ["arn:aws:route53:::hostedzone/${aws_route53_zone.demo[0].zone_id}"]
  }
  statement {
    effect    = "Allow"
    actions   = ["route53:ListHostedZones", "route53:ListResourceRecordSets", "route53:GetChange"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "dns" {
  count  = var.enable_dns ? 1 : 0
  name   = "dns-automation"
  role   = aws_iam_role.dns[0].id
  policy = data.aws_iam_policy_document.dns[0].json
}
