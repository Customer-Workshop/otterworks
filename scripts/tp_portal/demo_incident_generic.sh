#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# demo_incident_generic.sh — Beat 4 "break the oracle" trigger/undo skeleton
# for the AWS portal showcase (bad canary + DLQ replay).
#
# The real demo_incident.sh is authored per run (see the Makefile's
# `demo-incident` target and runbook-aws-portal-demo-day.md) because it needs
# that run's function names, alias/version numbers, and API URL. This script is
# the generic, parameterized skeleton the run's showcase child starts from: it
# assembles the exact AWS CLI + traffic commands from environment variables and
# by default only PRINTS them (DRY_RUN=1). The showcase child fills in the
# run's values, sets DRY_RUN=0, rehearses both beats, and installs the result
# as scripts/tp_portal/demo_incident.sh on the run branch.
#
# Beats:
#   canary-break   publish a CHAOS_FAULT version of one converted function,
#                  shift a canary slice of alias traffic to it, drive traffic
#                  so the alarm evaluates (the rollback automation is the star)
#   canary-undo    repoint the alias 100% to the known-good version and strip
#                  CHAOS_FAULT from $LATEST
#   dlq-break      set a fault on the downstream consumer and push events
#                  through the front door so they dead-letter
#   dlq-undo       remove the fault and redrive the DLQ back to the source queue
#   self-test      offline dry-run of all four with dummy values (no AWS calls)
#
# Required env (per run; the showcase child hardcodes these in demo_incident.sh):
#   OW_TP_NS               run namespace (e.g. r20260819)
#   OW_TP_API_URL          the run's API Gateway base URL
#   OW_TP_TOKEN            demo bearer token (sensitive Terraform output)
#   OW_TP_CANARY_FUNCTION  Lambda to break (ow-tp-portal-<ns>-<context>)
#   OW_TP_CANARY_ALIAS     serving alias (default: live)
#   OW_TP_GOOD_VERSION     known-good published version number
#   OW_TP_FAULTY_VERSION   (dry-run only) version the faulty publish will get;
#                          under DRY_RUN=0 it is captured from publish-version
#   OW_TP_CANARY_WEIGHT    canary slice, 0..1 (default: 0.5)
#   OW_TP_CONSUMER_FUNCTION downstream consumer Lambda (DLQ beat)
#   OW_TP_DLQ_ARN          the consumer's dead-letter queue ARN
#   OW_TP_TRAFFIC_N        requests to drive per beat (default: 60)
#   OW_TP_TRAFFIC_PATH     API path traffic hits (default: /api/feedback/average-rating)
#   DRY_RUN                1 = print commands only (default), 0 = execute
#                          (DRY_RUN=0 additionally needs jq on PATH: fault
#                          set/clear merges the function's existing env vars)
# ------------------------------------------------------------------------------
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
OW_TP_CANARY_ALIAS="${OW_TP_CANARY_ALIAS:-live}"
OW_TP_CANARY_WEIGHT="${OW_TP_CANARY_WEIGHT:-0.5}"
OW_TP_TRAFFIC_N="${OW_TP_TRAFFIC_N:-60}"
OW_TP_TRAFFIC_PATH="${OW_TP_TRAFFIC_PATH:-/api/feedback/average-rating}"

usage() { sed -n '2,48p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

need() {
  local var
  for var in "$@"; do
    [[ -n "${!var:-}" ]] || { echo "missing required env: ${var}" >&2; exit 1; }
  done
}

run() {
  if [[ "${DRY_RUN}" == "0" ]]; then
    "$@"
  else
    printf 'DRY-RUN:'; printf ' %q' "$@"; printf '\n'
  fi
}

drive_traffic() {
  echo "# drive ${OW_TP_TRAFFIC_N} requests so the alarm window evaluates"
  local url
  url="$(printf '%q' "${OW_TP_API_URL}${OW_TP_TRAFFIC_PATH}")"
  run bash -c "for i in \$(seq 1 ${OW_TP_TRAFFIC_N}); do curl -s -o /dev/null -H \"Authorization: Bearer \${OW_TP_TOKEN}\" ${url}; sleep 1; done"
}

set_fault() { # set_fault <function> <oom|fail|off> — add/remove ONLY CHAOS_FAULT, preserving the function's real env vars
  local fn="$1" fault="$2" jq_expr
  if [[ "${fault}" == "off" ]]; then
    jq_expr='del(.CHAOS_FAULT)'
  else
    jq_expr=".CHAOS_FAULT = \"${fault}\""
  fi
  run bash -c "aws lambda update-function-configuration --function-name '${fn}' --environment \"\$(aws lambda get-function-configuration --function-name '${fn}' --query 'Environment.Variables' --output json | jq -c '{Variables: ((. // {}) | ${jq_expr})}')\""
  run aws lambda wait function-updated --function-name "${fn}"
}

canary_break() {
  need OW_TP_API_URL OW_TP_TOKEN OW_TP_CANARY_FUNCTION OW_TP_GOOD_VERSION
  echo "# 1. publish a faulty version (CHAOS_FAULT on) of ${OW_TP_CANARY_FUNCTION}"
  set_fault "${OW_TP_CANARY_FUNCTION}" oom
  local faulty_version
  if [[ "${DRY_RUN}" == "0" ]]; then
    faulty_version="$(aws lambda publish-version --function-name "${OW_TP_CANARY_FUNCTION}" \
      --description "chaos canary (demo beat 4)" --query Version --output text)"
  else
    run aws lambda publish-version --function-name "${OW_TP_CANARY_FUNCTION}" \
      --description "chaos canary (demo beat 4)"
    faulty_version="${OW_TP_FAULTY_VERSION:-FAULTY_VERSION}"
  fi
  echo "# 2. shift a ${OW_TP_CANARY_WEIGHT} canary slice of alias '${OW_TP_CANARY_ALIAS}' to version ${faulty_version}"
  run aws lambda update-alias \
    --function-name "${OW_TP_CANARY_FUNCTION}" \
    --name "${OW_TP_CANARY_ALIAS}" \
    --function-version "${OW_TP_GOOD_VERSION}" \
    --routing-config "AdditionalVersionWeights={${faulty_version}=${OW_TP_CANARY_WEIGHT}}"
  drive_traffic
  echo "# now do nothing: the alarm fires and the rollback automation repoints the alias itself."
}

canary_undo() {
  need OW_TP_CANARY_FUNCTION OW_TP_GOOD_VERSION
  echo "# repoint alias '${OW_TP_CANARY_ALIAS}' 100% at the known-good version and clear the fault"
  run aws lambda update-alias \
    --function-name "${OW_TP_CANARY_FUNCTION}" \
    --name "${OW_TP_CANARY_ALIAS}" \
    --function-version "${OW_TP_GOOD_VERSION}" \
    --routing-config "AdditionalVersionWeights={}"
  set_fault "${OW_TP_CANARY_FUNCTION}" off
}

dlq_break() {
  need OW_TP_API_URL OW_TP_TOKEN OW_TP_CONSUMER_FUNCTION
  echo "# 1. force the downstream consumer to fail every event"
  set_fault "${OW_TP_CONSUMER_FUNCTION}" fail
  echo "# 2. push events through the front door; they retry and dead-letter"
  drive_traffic
}

dlq_undo() {
  need OW_TP_CONSUMER_FUNCTION OW_TP_DLQ_ARN
  echo "# 1. heal the consumer"
  set_fault "${OW_TP_CONSUMER_FUNCTION}" off
  echo "# 2. redrive every dead-lettered message back to its source queue"
  run aws sqs start-message-move-task --source-arn "${OW_TP_DLQ_ARN}"
}

self_test() {
  bash -n "${BASH_SOURCE[0]}"
  local out
  out="$(
    DRY_RUN=1 \
    OW_TP_NS=selftest \
    OW_TP_API_URL=https://example.invalid \
    OW_TP_TOKEN=dummy \
    OW_TP_CANARY_FUNCTION=ow-tp-portal-selftest-feedback \
    OW_TP_GOOD_VERSION=1 \
    OW_TP_CONSUMER_FUNCTION=ow-tp-portal-selftest-consumer \
    OW_TP_DLQ_ARN=arn:aws:sqs:us-east-1:000000000000:ow-tp-portal-selftest-dlq \
    bash "${BASH_SOURCE[0]}" canary-break
    DRY_RUN=1 \
    OW_TP_CANARY_FUNCTION=ow-tp-portal-selftest-feedback \
    OW_TP_GOOD_VERSION=1 \
    bash "${BASH_SOURCE[0]}" canary-undo
    DRY_RUN=1 \
    OW_TP_API_URL=https://example.invalid \
    OW_TP_TOKEN=dummy \
    OW_TP_CONSUMER_FUNCTION=ow-tp-portal-selftest-consumer \
    bash "${BASH_SOURCE[0]}" dlq-break
    DRY_RUN=1 \
    OW_TP_CONSUMER_FUNCTION=ow-tp-portal-selftest-consumer \
    OW_TP_DLQ_ARN=arn:aws:sqs:us-east-1:000000000000:ow-tp-portal-selftest-dlq \
    bash "${BASH_SOURCE[0]}" dlq-undo
  )"
  echo "${out}" | grep -q 'DRY-RUN: aws lambda update-alias' || { echo "self-test: canary alias command missing" >&2; exit 1; }
  echo "${out}" | grep -q 'DRY-RUN: aws sqs start-message-move-task' || { echo "self-test: DLQ redrive command missing" >&2; exit 1; }
  if echo "${out}" | grep -v '^DRY-RUN\|^#' | grep -q 'aws '; then
    echo "self-test: found a non-dry-run aws invocation" >&2; exit 1
  fi
  echo "demo-incident-generic self-test: OK (all four beats render, dry-run only)"
}

case "${1:-}" in
  canary-break) canary_break ;;
  canary-undo) canary_undo ;;
  dlq-break) dlq_break ;;
  dlq-undo) dlq_undo ;;
  self-test) self_test ;;
  *) usage; exit 1 ;;
esac
