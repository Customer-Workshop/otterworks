#!/usr/bin/env bash
# Build and push the monolith image, tagged with the git tree hash of ticketing/monolith.
# Skips the build when that tag is already in ECR.   usage: build-monolith.sh [--force]
source "$(dirname "$0")/lib.sh"
aws_account_id
TAG="$(monolith_tag)"
IMAGE="${ECR_PREFIX}/monolith:${TAG}"
if [ "${1:-}" != "--force" ] && aws ecr describe-images --region "${AWS_REGION}" \
    --repository-name otterworks-demo/ticketing/monolith --image-ids imageTag="${TAG}" >/dev/null 2>&1; then
  log "image exists: ${IMAGE}"; echo "${IMAGE}"; exit 0
fi
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}" >/dev/null
docker build -t "${IMAGE}" "${TKT_ROOT}/monolith" >&2
docker push "${IMAGE}" >&2
echo "${IMAGE}"
