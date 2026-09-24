# Per-namespace AWS resources for the legacy-data-migration demo (CONTRACTS.md §12.4).
# Everything is tagged namespace/owner/demo/expires so `demo-destroy` can verify
# with the Resource Groups Tagging API and the reaper can find expired tokens.

data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "this" {
  name = var.eks_cluster
}

data "aws_eks_node_groups" "this" {
  cluster_name = var.eks_cluster
}

data "aws_eks_node_group" "first" {
  cluster_name    = var.eks_cluster
  node_group_name = sort(data.aws_eks_node_groups.this.names)[0]
}

data "aws_subnet" "node_first" {
  id = sort(data.aws_eks_node_group.first.subnet_ids)[0]
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  tags = {
    namespace = var.namespace
    owner     = var.owner
    demo      = "legacy-data-migration"
    expires   = var.expires
  }
  db2_volume_az   = var.db2_volume_az != "" ? var.db2_volume_az : data.aws_subnet.node_first.availability_zone
  db2_volume_name = "otterworks-ldm-${var.namespace}-db2"
  bucket_name     = "otterworks-ldm-${var.namespace}-${local.account_id}"
  ecr_repo_name   = "otterworks-demo/${var.namespace}/ldm-job"
  tenant_hosts    = var.ingress_hostname != "" ? ["t-${var.namespace}", "api-t-${var.namespace}"] : []
}

# Db2 data volume, bound by the db2-archive chart as a static PersistentVolume
# (no dynamic provisioning: the cluster must never create AWS resources).
# Encrypted with the account default aws/ebs key; a per-namespace CMK would outlive the throwaway demo.
resource "aws_ebs_volume" "db2" { # nosemgrep: terraform.aws.security.aws-ebs-volume-encrypted-with-cmk.aws-ebs-volume-encrypted-with-cmk
  availability_zone = local.db2_volume_az
  size              = var.db2_volume_size_gib
  type              = "gp3"
  encrypted         = true

  tags = merge(local.tags, {
    Name                                       = local.db2_volume_name
    "kubernetes.io/cluster/${var.eks_cluster}" = "owned"
    "kubernetes.io/created-for/pv/name"        = local.db2_volume_name
    "kubernetes.io/created-for/pvc/namespace"  = "otterworks-${var.namespace}"
  })
}

# Unload files / evidence for this token, everything under prefix <namespace>/.
resource "aws_s3_bucket" "demo" {
  bucket        = local.bucket_name
  force_destroy = true
  tags          = { Name = local.bucket_name }
}

resource "aws_s3_bucket_public_access_block" "demo" {
  bucket                  = aws_s3_bucket.demo.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "demo" {
  bucket = aws_s3_bucket.demo.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "demo" {
  bucket = aws_s3_bucket.demo.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "demo" {
  bucket = aws_s3_bucket.demo.id
  rule {
    id     = "expire-staging"
    status = "Enabled"
    filter {
      prefix = "${var.namespace}/"
    }
    expiration {
      days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Tenant hostnames (§3.1): the shared external-dns only publishes fixed platform hosts, so the
# demo's t-<token>/api-t-<token> records point at the shared ingress-nginx load balancer here.
data "aws_route53_zone" "tenant" {
  count = length(local.tenant_hosts) > 0 ? 1 : 0
  name  = "${var.host_suffix}."
}

resource "aws_route53_record" "tenant" {
  for_each = toset(local.tenant_hosts)
  zone_id  = data.aws_route53_zone.tenant[0].zone_id
  name     = "${each.value}.${var.host_suffix}"
  type     = "CNAME"
  ttl      = 60
  records  = [var.ingress_hostname]
}

# Job image repository (CI or the presenter pushes the ldm image here).
# Mutable tags: CI re-pushes the per-branch tag on every build (see branch_tag_slug in tenant-common.sh).
resource "aws_ecr_repository" "job" { # nosemgrep: terraform.aws.security.aws-ecr-mutable-image-tags.aws-ecr-mutable-image-tags
  name                 = local.ecr_repo_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "job" {
  repository = aws_ecr_repository.job.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
