#!/usr/bin/env bash
# Black-box smoke test: every webhook endpoint (including errors, 404s, 405s and
# browser-style Accept: text/html requests) must answer with a JSON body and an
# application/json content type. Never HTML, never a redirect to a UI.
#
#   BASE_URL   base of the service or gateway (default http://localhost:8092)
#   AUTH_HEADER extra header for authenticated calls, e.g. "Authorization: Bearer ..."
#               (when hitting the service directly, X-User-ID is used instead)
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8092}"
AUTH_HEADER="${AUTH_HEADER:-X-User-ID: smoke-user}"
SINK_URL="${SINK_URL:-http://webhook-sink:8093/hook}"

command -v jq >/dev/null || { echo "jq is required"; exit 2; }

pass=0; fail=0
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# check <name> <expected-status> <method> <path> [auth] [json-body]
check() {
  local name="$1" want="$2" method="$3" path="$4" auth="${5:-}" body="${6:-}"
  local hdr="$TMP/h" out="$TMP/b"
  local args=(-sS -o "$out" -D "$hdr" -X "$method" -H "Accept: text/html,application/xhtml+xml,*/*;q=0.8")
  [[ -n "$auth" ]] && args+=(-H "$AUTH_HEADER")
  [[ -n "$body" ]] && args+=(-H "Content-Type: application/json" --data "$body")
  curl "${args[@]}" "$BASE_URL$path" || true

  local status ct problems=()
  status="$(awk 'toupper($1) ~ /^HTTP\// {s=$2} END {print s}' "$hdr")"
  ct="$(awk 'BEGIN{IGNORECASE=1} /^content-type:/ {sub(/\r$/,""); print tolower($2)}' "$hdr" | tail -n1)"

  [[ "$status" == "$want" ]] || problems+=("status $status != $want")
  [[ "$ct" == application/json* ]] || problems+=("content-type '$ct' is not application/json")
  jq -e 'type == "object"' "$out" >/dev/null 2>&1 || problems+=("body is not a JSON object")
  if grep -qiE '<(!doctype|html|body|script|head)' "$out"; then problems+=("body contains HTML markup"); fi
  if grep -qiE '^location:' "$hdr"; then problems+=("unexpected redirect"); fi

  if [[ ${#problems[@]} -eq 0 ]]; then
    pass=$((pass+1)); printf 'PASS  %-4s %-58s %s json\n' "$method" "$path" "$status" >&2
  else
    fail=$((fail+1)); printf 'FAIL  %-4s %-58s %s\n' "$method" "$path" "$(IFS=';'; echo "${problems[*]}")" >&2
    echo "      body: $(head -c 300 "$out")" >&2
  fi
  cat "$out"
}

echo "== JSON-only smoke against $BASE_URL"

# Unauthenticated / infrastructure routes.
if [[ "$AUTH_HEADER" == X-User-ID* ]]; then
  check health          200 GET  /health          >/dev/null
  check ready           200 GET  /ready           >/dev/null
  check unknown         404 GET  /no/such/route   >/dev/null
  check index-html      404 GET  /index.html      >/dev/null
  check static          404 GET  /static/app.js   >/dev/null
  check favicon         404 GET  /favicon.ico     >/dev/null
  check bad-method      405 DELETE /health        >/dev/null
  check no-auth         401 GET  /api/v1/webhooks/subscriptions >/dev/null
else
  check gw-no-auth      401 GET  /api/v1/webhooks/subscriptions >/dev/null
fi

# Authenticated API surface.
check root            200 GET /api/v1/webhooks              auth >/dev/null
check root-slash      200 GET /api/v1/webhooks/             auth >/dev/null
check event-types     200 GET /api/v1/webhooks/event-types  auth >/dev/null
check stats           200 GET /api/v1/webhooks/stats        auth >/dev/null
check subs-empty      200 GET /api/v1/webhooks/subscriptions auth >/dev/null
check sub-404         404 GET /api/v1/webhooks/subscriptions/does-not-exist auth >/dev/null
check sub-bad-body    400 POST /api/v1/webhooks/subscriptions auth '{"url":"ftp://nope"}' >/dev/null
check sub-not-json    400 POST /api/v1/webhooks/subscriptions auth '<html><body>hi</body></html>' >/dev/null
check api-404         404 GET /api/v1/webhooks/nope         auth >/dev/null
check api-405         405 DELETE /api/v1/webhooks/deliveries auth >/dev/null

created="$(check sub-create 201 POST /api/v1/webhooks/subscriptions auth \
  "{\"url\":\"$SINK_URL\",\"eventTypes\":[\"file_uploaded\",\"document_created\"],\"description\":\"smoke\"}")"
sub_id="$(echo "$created" | tail -n1 | jq -r '.id')"
secret_on_create="$(echo "$created" | tail -n1 | jq -r '.secret // empty')"
[[ "$secret_on_create" == whsec_* ]] && { pass=$((pass+1)); echo "PASS  secret returned once on create"; } \
                                     || { fail=$((fail+1)); echo "FAIL  secret missing on create"; }

got="$(check sub-get 200 GET "/api/v1/webhooks/subscriptions/$sub_id" auth | tail -n1)"
if echo "$got" | jq -e 'has("secret") | not' >/dev/null; then pass=$((pass+1)); echo "PASS  secret omitted on read"; else fail=$((fail+1)); echo "FAIL  secret leaked on read"; fi

check sub-list        200 GET   /api/v1/webhooks/subscriptions auth >/dev/null
check sub-patch       200 PATCH "/api/v1/webhooks/subscriptions/$sub_id" auth '{"description":"smoke updated"}' >/dev/null
check sub-put-bad     400 PUT   "/api/v1/webhooks/subscriptions/$sub_id" auth '{"eventTypes":["not_an_event"]}' >/dev/null
check sub-rotate      200 POST  "/api/v1/webhooks/subscriptions/$sub_id/rotate-secret" auth >/dev/null
test_del="$(check sub-test 202 POST "/api/v1/webhooks/subscriptions/$sub_id/test" auth | tail -n1)"
del_id="$(echo "$test_del" | jq -r '.id')"

check deliveries      200 GET "/api/v1/webhooks/deliveries" auth >/dev/null
check deliveries-flt  200 GET "/api/v1/webhooks/deliveries?subscriptionId=$sub_id&limit=5" auth >/dev/null
check deliveries-bad  400 GET "/api/v1/webhooks/deliveries?status=bogus" auth >/dev/null
check delivery        200 GET "/api/v1/webhooks/deliveries/$del_id" auth >/dev/null
check attempts        200 GET "/api/v1/webhooks/deliveries/$del_id/attempts" auth >/dev/null
check delivery-404    404 GET "/api/v1/webhooks/deliveries/does-not-exist" auth >/dev/null
check dead-letters    200 GET "/api/v1/webhooks/dead-letters" auth >/dev/null
check replay-404      404 POST "/api/v1/webhooks/deliveries/does-not-exist/replay" auth >/dev/null
check sub-delete      200 DELETE "/api/v1/webhooks/subscriptions/$sub_id" auth >/dev/null
check sub-gone        404 GET "/api/v1/webhooks/subscriptions/$sub_id" auth >/dev/null

echo "== $pass passed, $fail failed"
[[ $fail -eq 0 ]]
