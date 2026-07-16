#!/usr/bin/env bash
# Enable VPC-CNI prefix delegation so t3.large nodes can run up to ~110 pods each
# (vs 35 default), removing the pod-IP exhaustion wall at high-tens of tenants.
#
# OPT-IN: existing nodes keep their old limit; only NEW nodes pick this up, so
# drain/recycle nodes during a quiet window after applying. See docs/scaling.md §2.
set -euo pipefail
CLUSTER="${EKS_CLUSTER:-otterworks-dev}"
REGION="${AWS_REGION:-us-east-1}"

echo "[prefix-delegation] setting aws-node env on cluster ${CLUSTER}"
kubectl -n kube-system set env daemonset aws-node \
  ENABLE_PREFIX_DELEGATION=true \
  WARM_PREFIX_TARGET=1

echo "[prefix-delegation] done. Recycle nodes to apply, e.g.:"
echo "  kubectl drain <node> --ignore-daemonsets --delete-emptydir-data && \\"
echo "  aws ec2 terminate-instances --region ${REGION} --instance-ids <id>   # ASG replaces it"
echo "Verify new nodes advertise more pods: kubectl get node <new-node> -o jsonpath='{.status.allocatable.pods}'"
