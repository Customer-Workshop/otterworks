#!/usr/bin/env bash
# Install Kubernetes Cluster Autoscaler wired to the otterworks-dev managed node
# group's ASG, so nodes scale with pending pods instead of manual desiredSize
# bumps. See docs/scaling.md §1. Karpenter is the heavier but better high-tens
# alternative (bin-packs mixed instance types).
#
# Prereq: the node/IRSA role must allow autoscaling:Describe*, ec2:Describe*,
# autoscaling:SetDesiredCapacity, autoscaling:TerminateInstanceInAutoScalingGroup
# on the node group's ASG (auto-discovered via the k8s.io/cluster-autoscaler tags
# EKS adds to managed node groups).
set -euo pipefail
CLUSTER="${EKS_CLUSTER:-otterworks-dev}"

helm repo add autoscaler https://kubernetes.github.io/autoscaler >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler \
  --namespace kube-system \
  --set autoDiscovery.clusterName="${CLUSTER}" \
  --set awsRegion="${AWS_REGION:-us-east-1}" \
  --set extraArgs.balance-similar-node-groups=true \
  --set extraArgs.skip-nodes-with-system-pods=false \
  --set extraArgs.scale-down-unneeded-time=5m \
  --wait --timeout 5m

echo "[cluster-autoscaler] installed. Watch: kubectl -n kube-system logs -l app.kubernetes.io/name=aws-cluster-autoscaler -f"
