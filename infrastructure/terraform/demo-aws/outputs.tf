output "db2_volume_id" {
  description = "EBS volume id for the db2-archive static PV (values pv.volumeName)."
  value       = aws_ebs_volume.db2.id
}

output "db2_volume_az" {
  description = "AZ of the Db2 volume; the Db2 pod must be scheduled here."
  value       = aws_ebs_volume.db2.availability_zone
}

output "db2_volume_name" {
  value = local.db2_volume_name
}

output "bucket_name" {
  value = aws_s3_bucket.demo.bucket
}

output "s3_prefix" {
  value = "${var.namespace}/"
}

output "job_repository_url" {
  value = aws_ecr_repository.job.repository_url
}

output "tags" {
  value = local.tags
}

output "tenant_hosts" {
  description = "Tenant hostnames published in Route53 (empty when ingress_hostname is unset)."
  value       = [for r in aws_route53_record.tenant : r.fqdn]
}

output "job_role_arn" {
  description = "IRSA role the migration-job chart annotates its ServiceAccount with (S3 staging prefix only)"
  value       = aws_iam_role.job.arn
}
