output "cluster_name" {
  description = "EKS cluster name"
  value       = data.aws_eks_cluster.this.name
}

output "cluster_version" {
  description = "Current EKS cluster Kubernetes version"
  value       = data.aws_eks_cluster.this.version
}

output "ebs_csi_driver_role_arn" {
  description = "IAM role ARN for the EBS CSI driver"
  value       = aws_iam_role.ebs_csi_driver.arn
}

output "ebs_csi_driver_addon_version" {
  description = "Installed EBS CSI driver addon version"
  value       = aws_eks_addon.ebs_csi_driver.addon_version
}
