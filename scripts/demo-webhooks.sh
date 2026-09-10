#!/usr/bin/env bash
set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8080}"
SINK="${SINK:-http://localhost:8093}"
EMAIL="${EMAIL:-admin@otterworks.dev}"
PASSWORD="${PASSWORD:-Admin123!}"
PARTNER_EMAIL="${PARTNER_EMAIL:-webhook-partner@otterworks.dev}"
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 1; }
curl -fsS "$GATEWAY/health" >/dev/null || { echo "gateway is not ready" >&2; exit 1; }
curl -fsS "$SINK/health" >/dev/null || { echo "sink is not ready" >&2; exit 1; }

echo "=== 1) login ==="
login=$(curl -fsS -X POST "$GATEWAY/api/v1/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
TOKEN=$(jq -r '.accessToken // .access_token' <<<"$login")
[[ "$TOKEN" != "null" && -n "$TOKEN" ]] || { echo "$login" >&2; exit 1; }
AUTH=(-H "Authorization: Bearer $TOKEN")
OWNER_ID=$(jq -r '.user.id // .id' <<<"$login")
echo "logged in"

echo "=== 2) register partner and create subscription ==="
partner_payload=$(jq -n --arg email "$PARTNER_EMAIL" --arg password "$PASSWORD" '{email:$email,password:$password,displayName:"Webhook Partner"}')
curl -sS -o /dev/null -w '%{http_code}' -X POST "$GATEWAY/api/v1/auth/register" -H 'Content-Type: application/json' -d "$partner_payload" | grep -Eq '^(201|409)$'
sub=$(curl -fsS -X POST "$GATEWAY/api/v1/webhooks/subscriptions" "${AUTH[@]}" -H 'X-User-ID: ignored' -H 'Content-Type: application/json' -d '{"target_url":"http://webhook-sink:8093/","event_types":["file.shared","document.updated","comment.added"]}')
SUB_ID=$(jq -r '.id' <<<"$sub"); SECRET=$(jq -r '.secret' <<<"$sub")
echo "$sub" | jq '{id,secret,target_url,event_types}'

echo "=== 3) restart sink with the secret ==="
WEBHOOK_SINK_SECRET="$SECRET" docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --no-deps webhook-sink
for _ in $(seq 1 30); do curl -fsS "$SINK/health" >/dev/null && break; sleep 1; done

echo "=== 4) test ping ==="
curl -fsS -X POST "$GATEWAY/api/v1/webhooks/subscriptions/$SUB_ID/test" "${AUTH[@]}" | jq .
for _ in $(seq 1 30); do count=$(curl -fsS "$SINK/received" | jq -r '.count'); [[ "$count" -ge 1 ]] && break; sleep 1; done
curl -fsS "$SINK/received" | jq .

echo "=== 5) upload and share a file ==="
partner_login=$(curl -fsS -X POST "$GATEWAY/api/v1/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$PARTNER_EMAIL\",\"password\":\"$PASSWORD\"}")
PARTNER_ID=$(jq -r '.user.id // .id' <<<"$partner_login")
tmp_file=$(mktemp); printf 'webhook demo\n' >"$tmp_file"; upload=$(curl -fsS -X POST "$GATEWAY/api/v1/files/upload" "${AUTH[@]}" -F "file=@$tmp_file;type=text/plain"); rm -f "$tmp_file"
FILE_ID=$(jq -r '.file.id // .id' <<<"$upload")
curl -fsS -X POST "$GATEWAY/api/v1/files/$FILE_ID/share" "${AUTH[@]}" -H 'Content-Type: application/json' -d "{\"shared_with\":\"$PARTNER_ID\",\"permission\":\"viewer\",\"shared_by\":\"$OWNER_ID\"}" | jq .
for _ in $(seq 1 45); do curl -fsS "$SINK/received" | jq -e '[.items[] | select(.event=="file.shared")] | length > 0' >/dev/null && break; sleep 1; done
curl -fsS "$SINK/received" | jq .

echo "=== 6) deliveries ==="
curl -fsS "${GATEWAY}/api/v1/webhooks/deliveries?subscription_id=${SUB_ID}" "${AUTH[@]}" | jq .

echo "=== 7) fail-mode retry demonstration ==="
WEBHOOK_SINK_FAIL_MODE=1 WEBHOOK_SINK_SECRET="$SECRET" docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --no-deps webhook-sink
curl -fsS -X POST "$GATEWAY/api/v1/webhooks/subscriptions/$SUB_ID/test" "${AUTH[@]}" | jq .
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  deliveries=$(curl -fsS "${GATEWAY}/api/v1/webhooks/deliveries?subscription_id=${SUB_ID}" "${AUTH[@]}")
  echo "$deliveries" | jq '.data | map({id,status,attempts,last_error})'
  echo "$deliveries" | jq -e '[.data[] | select(.status=="failed")] | length > 0' >/dev/null && break
  sleep 2
done

echo "=== 8) restore sink ==="
WEBHOOK_SINK_FAIL_MODE=0 WEBHOOK_SINK_SECRET="$SECRET" docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --no-deps webhook-sink
curl -fsS "$SINK/received" | jq .
curl -fsS "${GATEWAY}/api/v1/webhooks/deliveries?subscription_id=${SUB_ID}" "${AUTH[@]}" | jq .
