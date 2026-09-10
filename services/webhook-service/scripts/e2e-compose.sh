#!/usr/bin/env bash
# End-to-end demo of the headless webhook service on localhost via docker compose:
#
#   gateway (/api/v1/webhooks, JWT) -> webhook-service -> Postgres
#   SNS otterworks-events -> SQS otterworks-webhook-events -> dispatcher -> webhook-sink
#
# Proves: subscription CRUD through the gateway, HMAC-verified delivery, retry with
# backoff (sink /flaky), dead-lettering to DB + SQS DLQ (sink /fail), replay, a
# queryable delivery log, and that every response on the API is JSON.
#
#   KEEP_UP=1   leave the stack running afterwards
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.infra.yml -f docker-compose.yml)
GATEWAY="${GATEWAY_URL:-http://localhost:8080}"
SINK="${SINK_URL:-http://localhost:8093}"
JWT_SECRET="${JWT_SECRET:-otterworks-local-dev-jwt-secret-change-me-in-production}"
SINK_SECRET="${WEBHOOK_SINK_SECRET:-whsec_localdemo_0123456789abcdef0123456789abcdef}"
export WEBHOOK_SINK_SECRET="$SINK_SECRET"
export WEBHOOK_DELIVERY_MAX_ATTEMPTS=4 WEBHOOK_DELIVERY_BACKOFF_BASE_MS=1000 WEBHOOK_DELIVERY_BACKOFF_MAX_SECONDS=5
USER_ID="e2e-user-$(date +%s)"

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32mOK\033[0m   %s\n' "$*"; }
die()  { printf '\033[1;31mFAIL\033[0m %s\n' "$*"; "${COMPOSE[@]}" logs --tail=50 webhook-service webhook-sink >&2 || true; exit 1; }

cleanup() {
  if [[ "${KEEP_UP:-0}" != "1" ]]; then
    step "tearing down"
    "${COMPOSE[@]}" stop webhook-service webhook-sink api-gateway >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for() { # url, seconds
  local url="$1" n="${2:-90}"
  for _ in $(seq 1 "$n"); do
    curl -fsS "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "timeout waiting for $url"
}

# ---- 1. bring up the minimum stack ------------------------------------------
step "starting postgres, localstack, webhook-service, webhook-sink, api-gateway"
"${COMPOSE[@]}" up -d postgres localstack
wait_for "http://localhost:4566/_localstack/health" 120
"${COMPOSE[@]}" up -d --build --no-deps webhook-service webhook-sink api-gateway
# webhook-service is deliberately not published on the host; probe it from inside the network.
for _ in $(seq 1 90); do
  "${COMPOSE[@]}" exec -T webhook-service wget -q -O /dev/null http://localhost:8092/health 2>/dev/null && break
  sleep 1
done
"${COMPOSE[@]}" exec -T webhook-service wget -q -O /dev/null http://localhost:8092/health || die "timeout waiting for webhook-service"
wait_for "$SINK/health"
wait_for "$GATEWAY/health"
# ready.d hook must have created the webhook queues
for _ in $(seq 1 60); do
  "${COMPOSE[@]}" exec -T localstack awslocal sqs get-queue-url --queue-name otterworks-webhook-events >/dev/null 2>&1 && break
  sleep 1
done
"${COMPOSE[@]}" exec -T localstack awslocal sqs get-queue-url --queue-name otterworks-webhook-dlq >/dev/null || die "webhook DLQ not provisioned"
ok "stack is up; queues provisioned"

# ---- 2. mint a JWT the gateway accepts (same HS256 dev secret) ----------------
TOKEN="$(python3 - "$JWT_SECRET" "$USER_ID" <<'PY'
import base64, hmac, hashlib, json, sys, time
secret, sub = sys.argv[1], sys.argv[2]
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
p = b64(json.dumps({"sub": sub, "user_id": sub, "email": sub + "@example.com", "roles": ["user"], "exp": int(time.time()) + 3600}).encode())
sig = b64(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
print(f"{h}.{p}.{sig}")
PY
)"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
api() { # method path [body]
  local m="$1" p="$2" b="${3:-}"
  if [[ -n "$b" ]]; then curl -sS -X "$m" "${AUTH[@]}" --data "$b" "$GATEWAY$p"; else curl -sS -X "$m" "${AUTH[@]}" "$GATEWAY$p"; fi
}

# ---- 3. subscriptions CRUD through the gateway --------------------------------
step "creating subscriptions via $GATEWAY/api/v1/webhooks"
mk() { api POST /api/v1/webhooks/subscriptions "{\"url\":\"http://webhook-sink:8093/$1\",\"eventTypes\":$2,\"secret\":\"$SINK_SECRET\",\"description\":\"e2e $1\"}"; }
SUB_OK="$(mk hook '["file_uploaded","document_created"]' | jq -r .id)"
SUB_FLAKY="$(mk flaky '["*"]' | jq -r .id)"
SUB_FAIL="$(mk fail '["file_uploaded"]' | jq -r .id)"
[[ "$SUB_OK" != null && "$SUB_FLAKY" != null && "$SUB_FAIL" != null ]] || die "subscription create failed"
api GET "/api/v1/webhooks/subscriptions/$SUB_OK" | jq -e 'has("secret") | not' >/dev/null || die "secret leaked on GET"
api PATCH "/api/v1/webhooks/subscriptions/$SUB_OK" '{"description":"e2e hook (patched)"}' | jq -e '.description == "e2e hook (patched)"' >/dev/null || die "PATCH failed"
[[ "$(api GET /api/v1/webhooks/subscriptions | jq -r .count)" == "3" ]] || die "expected 3 subscriptions"
ok "3 subscriptions created, read, patched; secrets not exposed on read"

# ---- 4. publish a real event on the SNS bus -----------------------------------
step "publishing file_uploaded to SNS otterworks-events"
EVENT_FILE_ID="file-$(date +%s)"
"${COMPOSE[@]}" exec -T localstack awslocal sns publish \
  --topic-arn arn:aws:sns:us-east-1:000000000000:otterworks-events \
  --message "{\"eventType\":\"file_uploaded\",\"fileId\":\"$EVENT_FILE_ID\",\"userId\":\"$USER_ID\",\"fileName\":\"e2e.txt\",\"timestamp\":\"$(date -u +%FT%TZ)\"}" >/dev/null
ok "published"

# ---- 5. wait for the delivery lifecycle to settle -----------------------------
step "waiting for deliveries: hook->delivered, flaky->delivered after retries, fail->dead_letter"
deadline=$((SECONDS + 90))
while :; do
  D="$(api GET "/api/v1/webhooks/deliveries?limit=50")"
  s_ok="$(echo "$D"    | jq -r --arg s "$SUB_OK"    '.deliveries[] | select(.subscriptionId==$s) | .status' | head -n1)"
  s_flaky="$(echo "$D" | jq -r --arg s "$SUB_FLAKY" '.deliveries[] | select(.subscriptionId==$s) | .status' | head -n1)"
  s_fail="$(echo "$D"  | jq -r --arg s "$SUB_FAIL"  '.deliveries[] | select(.subscriptionId==$s) | .status' | head -n1)"
  printf '   hook=%s flaky=%s fail=%s\n' "${s_ok:-?}" "${s_flaky:-?}" "${s_fail:-?}"
  if [[ "$s_ok" == delivered && "$s_flaky" == delivered && "$s_fail" == dead_letter ]]; then break; fi
  (( SECONDS < deadline )) || die "deliveries did not settle in time: $D"
  sleep 2
done
DEL_OK="$(echo "$D"    | jq -r --arg s "$SUB_OK"    '.deliveries[] | select(.subscriptionId==$s) | .id' | head -n1)"
DEL_FLAKY="$(echo "$D" | jq -r --arg s "$SUB_FLAKY" '.deliveries[] | select(.subscriptionId==$s) | .id' | head -n1)"
DEL_FAIL="$(echo "$D"  | jq -r --arg s "$SUB_FAIL"  '.deliveries[] | select(.subscriptionId==$s) | .id' | head -n1)"
[[ "$(api GET "/api/v1/webhooks/deliveries/$DEL_OK/attempts"    | jq -r .count)" == 1 ]] || die "hook should succeed first try"
[[ "$(api GET "/api/v1/webhooks/deliveries/$DEL_FLAKY/attempts" | jq -r .count)" == 3 ]] || die "flaky should take 3 attempts"
[[ "$(api GET "/api/v1/webhooks/deliveries/$DEL_FAIL/attempts"  | jq -r .count)" == 4 ]] || die "fail should exhaust 4 attempts"
api GET "/api/v1/webhooks/deliveries/$DEL_FLAKY/attempts" | jq -r '.attempts[] | "   flaky attempt \(.number): \(.statusCode) at \(.attemptedAt)"'
ok "retry with backoff and dead-letter transitions observed via the delivery log"

# ---- 6. delivery log queries ---------------------------------------------------
step "querying the delivery log"
[[ "$(api GET "/api/v1/webhooks/deliveries?status=dead_letter" | jq -r .count)" == 1 ]] || die "status filter"
[[ "$(api GET "/api/v1/webhooks/deliveries?eventType=file_uploaded" | jq -r .count)" == 3 ]] || die "eventType filter"
[[ "$(api GET "/api/v1/webhooks/deliveries?subscriptionId=$SUB_FAIL" | jq -r .count)" == 1 ]] || die "subscription filter"
[[ "$(api GET "/api/v1/webhooks/dead-letters" | jq -r '.deliveries[0].id')" == "$DEL_FAIL" ]] || die "dead-letters endpoint"
api GET "/api/v1/webhooks/stats" | jq -c .
ok "filters, dead-letters and stats work"

# ---- 7. signature verification at the receiver ---------------------------------
step "checking HMAC signatures at the sink"
R="$(curl -sS "$SINK/received" | jq --arg a "$DEL_OK" --arg b "$DEL_FLAKY" --arg c "$DEL_FAIL" \
  '{received: [.received[] | select(.deliveryId==$a or .deliveryId==$b or .deliveryId==$c)]} | .count = (.received|length)')"
total="$(echo "$R" | jq -r .count)"
unverified="$(echo "$R" | jq -r '[.received[] | select(.signatureVerified==false)] | length')"
[[ "$total" == 8 && "$unverified" == 0 ]] || die "expected 8 signed requests (1+3+4), got total=$total unverified=$unverified"
echo "$R" | jq -r --arg d "$DEL_OK" '.received[] | select(.deliveryId==$d) | "   payload.type=\(.body.type) fileId=\(.body.data.fileId)"'
ok "all $total requests carried a valid X-OtterWorks-Signature"

# ---- 8. SQS dead-letter queue -----------------------------------------------------
step "checking the SQS DLQ"
# Drain in several rounds: earlier runs may have left messages on the queue.
DLQ_MSG=""
for _ in $(seq 1 10); do
  DLQ_MSG="$("${COMPOSE[@]}" exec -T localstack awslocal sqs receive-message \
    --queue-url http://localhost:4566/000000000000/otterworks-webhook-dlq --wait-time-seconds 2 --max-number-of-messages 10 --visibility-timeout 120 \
    | jq -r --arg d "$DEL_FAIL" '.Messages[]?.Body | fromjson | select(.deliveryId==$d) | .deliveryId' | head -n1)"
  [[ "$DLQ_MSG" == "$DEL_FAIL" ]] && break
done
[[ "$DLQ_MSG" == "$DEL_FAIL" ]] || die "dead-lettered delivery not found on otterworks-webhook-dlq"
ok "dead letter published to otterworks-webhook-dlq"

# ---- 9. replay --------------------------------------------------------------------
step "replaying the dead-lettered delivery after fixing the receiver"
# Realistic recovery: point the broken subscription at a healthy endpoint, then replay.
api PATCH "/api/v1/webhooks/subscriptions/$SUB_FAIL" '{"url":"http://webhook-sink:8093/hook"}' | jq -e '.url | endswith("/hook")' >/dev/null || die "patch url"
api POST "/api/v1/webhooks/deliveries/$DEL_FAIL/replay" | jq -e '.status == "pending" and .maxAttempts > .attempts' >/dev/null || die "replay"
for _ in $(seq 1 30); do
  st="$(api GET "/api/v1/webhooks/deliveries/$DEL_FAIL" | jq -r .status)"
  [[ "$st" == delivered ]] && break
  sleep 1
done
[[ "$st" == delivered ]] || die "replayed delivery ended as $st"
[[ "$(api GET "/api/v1/webhooks/dead-letters" | jq -r .count)" == 0 ]] || die "replayed delivery should leave dead-letters"
[[ "$(api GET "/api/v1/webhooks/deliveries/$DEL_FAIL/attempts" | jq -r .count)" == 5 ]] || die "attempt history should be preserved across replay"
ok "replay re-queued the delivery; history kept (4 failed + 1 delivered attempts)"

# ---- 10. JSON-only smoke through the gateway ----------------------------------------
step "JSON-only smoke test through the gateway"
BASE_URL="$GATEWAY" AUTH_HEADER="Authorization: Bearer $TOKEN" SINK_URL="http://webhook-sink:8093/hook" \
  bash services/webhook-service/scripts/smoke-json-only.sh

# ---- 11. headless: image contains a single binary and nothing UI-shaped -------------
step "inspecting the webhook-service image for static/template content"
FILES="$(docker run --rm --entrypoint sh "$(docker compose -f docker-compose.infra.yml -f docker-compose.yml images -q webhook-service | head -n1)" -c 'find /app -type f')"
[[ "$FILES" == "/app/server" ]] || die "unexpected files in image: $FILES"
ok "image ships exactly /app/server"

step "cleaning up subscriptions"
for s in "$SUB_OK" "$SUB_FLAKY" "$SUB_FAIL"; do api DELETE "/api/v1/webhooks/subscriptions/$s" >/dev/null; done

printf '\n\033[1;32mE2E PASSED\033[0m headless webhook-service: CRUD via gateway, signed deliveries off SNS/SQS, retries, dead-letter (DB+DLQ), replay, JSON-only.\n'
