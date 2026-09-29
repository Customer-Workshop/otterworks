#!/usr/bin/env bash
# Remove everything carrying the run token, then list what remains and fail if anything does.
#   usage: destroy.sh <token> [--dry-run]        (make demo-destroy NS=<token>)
# Covers: both namespaces (and every namespaced object in them), any other object in any
# namespace or cluster scope labelled demo.otterworks.app/run-token=<token>, ECR image tags
# prefixed <token>-, and the Route53 records external-dns created for the token's hosts.
source "$(dirname "$0")/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
start_transcript "${TOKEN}" destroy
SECONDS=0
aws_account_id; ensure_kubeconfig
run() { if [ "${DRY}" = 1 ]; then echo "DRY-RUN: $*"; else "$@"; fi; }
SEL="${TOKEN_LABEL}=${TOKEN}"

# Everything the after side creates lives in <token>-after (Kafka/KafkaNodePool/KafkaTopics, Knative Services and
# their revisions/routes, KEDA ScaledObjects + HPAs, Deployments, CronJob, k6 Jobs, monitors, Ingresses, the TLS
# certificate/secret and the Grafana dashboard ConfigMap), so deleting the namespace removes it all; list it first.
list_ns_objects() {
  local kinds; kinds="$(kubectl api-resources --namespaced --verbs=list,delete -o name 2>/dev/null | grep -v -E '^(events|events.events.k8s.io|endpoints|endpointslices.discovery.k8s.io|pods|replicasets.apps|controllerrevisions.apps)$' | paste -sd, -)"
  kubectl -n "$1" get "${kinds}" -o name --ignore-not-found 2>/dev/null | sed 's/^/      /'
}
log "1/4 namespaces labelled ${SEL}"
for ns in $(kubectl get ns -l "${SEL}" -o name) ; do run kubectl delete "${ns}" --wait=false; done
for ns in "$(ns_before "${TOKEN}")" "$(ns_after "${TOKEN}")"; do
  if kubectl get ns "${ns}" >/dev/null 2>&1; then
    log "   ${ns} contains:"; list_ns_objects "${ns}"
    [ "${DRY}" = 1 ] && echo "DRY-RUN: release_kafka_topics ${ns}" || release_kafka_topics "${ns}"
    run kubectl delete ns "${ns}" --wait=false
  fi
done

log "2/4 labelled objects outside those namespaces"
for r in $(kubectl api-resources --verbs=list,delete -o name 2>/dev/null | grep -v -E '^(events|events.events.k8s.io|namespaces)$'); do
  kubectl get "${r}" -A -l "${SEL}" -o jsonpath='{range .items[*]}{.metadata.namespace}{"|"}{.metadata.name}{"\n"}{end}' 2>/dev/null \
  | while IFS='|' read -r ns name; do
      [ -z "${name}" ] && continue
      case "${ns}" in "$(ns_before "${TOKEN}")"|"$(ns_after "${TOKEN}")") continue ;; esac
      if [ -n "${ns}" ]; then run kubectl -n "${ns}" delete "${r}" "${name}" --wait=false; else run kubectl delete "${r}" "${name}" --wait=false; fi
    done
done

log "3/4 ECR image tags ${TOKEN}-*"
for repo in $(aws ecr describe-repositories --region "${AWS_REGION}" --query "repositories[?starts_with(repositoryName,'otterworks-demo/ticketing/')].repositoryName" --output text); do
  ids="$(aws ecr list-images --region "${AWS_REGION}" --repository-name "${repo}" --filter tagStatus=TAGGED \
        --query "imageIds[?starts_with(imageTag,'${TOKEN}-')]" --output json)"
  [ "${ids}" = "[]" ] && continue
  log "   ${repo}: $(echo "${ids}" | jq -r '[.[].imageTag]|join(",")')"
  run aws ecr batch-delete-image --region "${AWS_REGION}" --repository-name "${repo}" --image-ids "${ids}" >/dev/null
done

log "4/4 waiting for namespaces to terminate and external-dns to drop the token's records"
[ "${DRY}" = 1 ] && { log "dry run: skipping verification"; exit 0; }
ZONE_ID="$(aws route53 list-hosted-zones-by-name --dns-name otterworks.app --max-items 1 --query 'HostedZones[0].Id' --output text)"
survivors() {
  kubectl get ns -o name | grep -E "namespace/${TOKEN}-" || true
  kubectl get ns -l "${SEL}" -o name || true
  for r in $(kubectl api-resources --verbs=list -o name 2>/dev/null | grep -v -E '^(events|events.events.k8s.io)$'); do
    kubectl get "${r}" -A -l "${SEL}" -o name 2>/dev/null | sed "s#^#${r}: #" || true
  done
  aws route53 list-resource-record-sets --hosted-zone-id "${ZONE_ID}" \
    --query "ResourceRecordSets[?contains(Name,'${TOKEN}-')].[Type,Name]" --output text | sed 's/^/route53: /'
  for repo in $(aws ecr describe-repositories --region "${AWS_REGION}" --query "repositories[?starts_with(repositoryName,'otterworks-demo/ticketing/')].repositoryName" --output text); do
    aws ecr list-images --region "${AWS_REGION}" --repository-name "${repo}" --filter tagStatus=TAGGED \
      --query "imageIds[?starts_with(imageTag,'${TOKEN}-')].imageTag" --output text | tr '\t' '\n' | sed "/^$/d;s#^#ecr ${repo}: #"
  done
}
for i in $(seq 1 30); do
  left="$(survivors | sort -u | sed '/^$/d')"
  [ -z "${left}" ] && break
  log "   ${i}/30: $(echo "${left}" | wc -l) remaining; next check in 20s"
  sleep 20
done
echo "---- remaining objects for token ${TOKEN} ----"
if [ -n "${left}" ]; then echo "${left}"; echo "---- FAIL: ${TOKEN} not clean after ${SECONDS}s ----"; exit 1; fi
echo "(none)"
echo "---- PASS: nothing carrying ${TOKEN} remains (${SECONDS}s) ----"
