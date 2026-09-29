#!/usr/bin/env bash
# Replica counts at rest for both namespaces of a run (what the runbook shows before the run).
#   usage: status.sh <token>
source "$(dirname "$0")/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
ensure_kubeconfig
for ns in "$(ns_before "${TOKEN}")" "$(ns_after "${TOKEN}")"; do
  echo "== ${ns}"
  if ! kubectl get ns "${ns}" >/dev/null 2>&1; then echo "   (absent)"; continue; fi
  kubectl -n "${ns}" get deploy,statefulset -o custom-columns='KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas' 2>/dev/null
  kubectl -n "${ns}" get ksvc -o custom-columns='KSVC:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,URL:.status.url' 2>/dev/null || true
  kubectl -n "${ns}" get scaledobject -o custom-columns='SCALEDOBJECT:.metadata.name,TARGET:.spec.scaleTargetRef.name,MIN:.spec.minReplicaCount,MAX:.spec.maxReplicaCount,ACTIVE:.status.conditions[?(@.type=="Active")].status' 2>/dev/null || true
  echo "   running pods: $(kubectl -n "${ns}" get pods --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)"
done
