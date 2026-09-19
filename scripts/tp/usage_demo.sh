#!/usr/bin/env bash
set -euo pipefail

NS="${1:?usage: $0 <namespace>}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
BRIDGE_URL="${BRIDGE_URL:-http://localhost:8097}"
EMAIL="${EMAIL:-admin@otterworks.dev}"
PASSWORD="${PASSWORD:-Admin123!}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$HOME/tp-evidence/handoff3}"
export EMAIL PASSWORD
mkdir -p "$EVIDENCE_DIR"

login_body="$(python3 - <<'PY'
import json
import os
print(json.dumps({"email": os.environ["EMAIL"], "password": os.environ["PASSWORD"]}))
PY
)"
login_response="$(curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' -d "$login_body")"
token="$(printf '%s' "$login_response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')"
owner_id="$(printf '%s' "$login_response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["user"]["id"])')"
printf '%s\n' "$login_response" > "$EVIDENCE_DIR/usage-demo-login.json"

health_before="$(curl -fsS "$BRIDGE_URL/health")"
printf '%s\n' "$health_before" > "$EVIDENCE_DIR/usage-demo-bridge-health-before.json"
recorded_before="$(printf '%s' "$health_before" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("recorded", 0))')"
usage_before="$(curl -fsS "$BASE_URL/api/v1/billing/usage" \
  -H "Authorization: Bearer $token")"
printf '%s\n' "$usage_before" > "$EVIDENCE_DIR/usage-demo-usage-before.json"
events_before="$(printf '%s' "$usage_before" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("events", [])))')"

document_response="$(curl -fsS -X POST "$BASE_URL/api/v1/documents" \
  -H "Authorization: Bearer $token" \
  -H 'Content-Type: application/json' \
  -d "{\"title\":\"TP usage demo $NS\",\"content\":\"usage bridge verification\",\"owner_id\":\"$owner_id\"}")"
printf '%s\n' "$document_response" > "$EVIDENCE_DIR/usage-demo-document.json"

for _ in $(seq 1 30); do
  health="$(curl -fsS "$BRIDGE_URL/health")"
  printf '%s\n' "$health" > "$EVIDENCE_DIR/usage-demo-bridge-health.json"
  recorded="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("recorded", 0))')"
  if [ "$recorded" -gt "$recorded_before" ]; then
    break
  fi
  sleep 1
done
if [ "${recorded:-0}" -le "$recorded_before" ]; then
  echo "usage bridge did not record the document event within 30 seconds" >&2
  exit 1
fi

usage_response="$(curl -fsS "$BASE_URL/api/v1/billing/usage" \
  -H "Authorization: Bearer $token")"
printf '%s\n' "$usage_response" > "$EVIDENCE_DIR/usage-demo-usage.json"
events_after="$(printf '%s' "$usage_response" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("events", [])))')"
if [ "$events_after" -le "$events_before" ]; then
  echo "document usage event was not visible in billing usage" >&2
  exit 1
fi
echo "usage event match: count increase (event ID is not exposed)"
printf '%s\n' "$usage_response" | python3 -c '
import json, sys
events = json.load(sys.stdin).get("events", [])
print(json.dumps(events[0] if events else {}, indent=2))
'
