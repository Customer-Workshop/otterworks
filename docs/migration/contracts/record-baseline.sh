#!/usr/bin/env bash
# Records the wire-level behaviour of the legacy-portal monolith as a JSON transcript.
# The transcript is the reference every extracted service is graded against.
#
#   cd services/legacy-portal && ./mvnw -B -DskipTests package && java -jar target/legacy-portal.jar &
#   docs/migration/contracts/record-baseline.sh > /tmp/baseline.json
#
# BASE defaults to the monolith; point it at a decomposed service to replay the same
# requests against the new implementation.
set -uo pipefail

BASE="${BASE:-http://localhost:8095}"

emit() {
  local method="$1" path="$2" body="${3:-}"
  local out status
  if [ -n "$body" ]; then
    out=$(curl -sS -o /tmp/.probe.body -w '%{http_code}' -X "$method" "$BASE$path" \
      -H 'Content-Type: application/json' -d "$body")
  else
    out=$(curl -sS -o /tmp/.probe.body -w '%{http_code}' -X "$method" "$BASE$path")
  fi
  status="$out"
  python3 - "$method" "$path" "$status" <<'PY'
import json, sys
method, path, status = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open('/tmp/.probe.body').read()
try:
    parsed = json.loads(raw)
except Exception:
    parsed = raw
print(json.dumps({"method": method, "path": path, "status": int(status), "body": parsed}))
PY
}

{
  emit GET /health
  emit GET /actuator/health

  # --- announcements ---
  emit GET  /api/announcements
  emit GET  /api/announcements?publishedOnly=false
  emit GET  /api/announcements/999999
  emit POST /api/announcements '{"title":"Parity A","body":"unpublished body","published":false}'
  emit POST /api/announcements '{"title":"Parity B","body":"published body","published":true}'
  emit POST /api/announcements '{"title":"","body":"blank title","published":false}'
  emit POST /api/announcements '{"body":"missing title"}'
  emit POST /api/announcements/1/publish
  emit POST /api/announcements/1/publish
  emit POST /api/announcements/999999/publish
  emit GET  /api/announcements
  emit DELETE /api/announcements/1
  emit GET  /api/announcements/abc
  emit GET  '/api/announcements?publishedOnly=maybe'
  emit POST /api/announcements '{"title":"Unknown field","body":"B","extra":"ignored"}'
  emit POST /api/announcements 'not json'

  # --- user preferences ---
  emit GET /api/preferences/unknown-user
  emit GET /api/preferences/unknown-user
  emit PUT /api/preferences/u1 '{"theme":"dark","locale":"fr-FR","emailNotifications":false}'
  emit GET /api/preferences/u1
  emit PUT /api/preferences/u1 '{"theme":"","locale":"fr-FR","emailNotifications":false}'
  emit PUT /api/preferences/u1 '{"theme":"dark"}'
  emit GET /api/preferences
  emit PATCH /api/preferences/u1 '{"theme":"dark"}'

  # --- feedback ---
  emit GET  /api/feedback/average-rating
  emit POST /api/feedback '{"userId":"u1","rating":5,"message":"great"}'
  emit POST /api/feedback '{"userId":"u1","rating":1,"message":"bad"}'
  emit POST /api/feedback '{"userId":"u2","rating":3,"message":"ok"}'
  emit POST /api/feedback '{"userId":"u1","rating":0,"message":"below range"}'
  emit POST /api/feedback '{"userId":"u1","rating":6,"message":"above range"}'
  emit POST /api/feedback '{"userId":"u1","rating":3,"message":""}'
  emit GET  /api/feedback?userId=u1
  emit GET  /api/feedback?userId=nobody
  emit GET  /api/feedback/average-rating
  emit GET  /api/feedback
  emit POST /api/feedback '{"userId":"u3","message":"no rating"}'
} | python3 -c 'import json,sys; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()], indent=2))'
