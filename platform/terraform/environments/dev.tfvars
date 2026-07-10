aws_region         = "us-east-1"
environment        = "dev"
cluster_name       = "otterworks-dev"
cluster_version    = "1.32"
vpc_cidr           = "10.0.0.0/16"
az_count           = 2
enable_nat_gateway = false
# Cost-optimized dev: SPOT capacity (~70% cheaper) and a single node by default.
# Autoscaling can still grow to max_size under load.
node_instance_types = ["t3.large"]
node_capacity_type  = "SPOT"
node_desired_size   = 1
node_min_size       = 1
node_max_size       = 4
ecr_prefix          = "otterworks/"
