# S3 landing zone the legacy billing exports are dropped into, plus a
# read-only IAM user whose key is handed to the Airbyte S3 source.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "landing" {
  bucket        = "${local.prefix}-landing-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_iam_user" "airbyte_reader" {
  name = "${local.prefix}-reader"
}

data "aws_iam_policy_document" "airbyte_reader" {
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.landing.arn]
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.landing.arn}/${var.namespace}/*"]
  }
}

resource "aws_iam_user_policy" "airbyte_reader" {
  name   = "landing-read"
  user   = aws_iam_user.airbyte_reader.name
  policy = data.aws_iam_policy_document.airbyte_reader.json
}

resource "aws_iam_access_key" "airbyte_reader" {
  user = aws_iam_user.airbyte_reader.name
}
