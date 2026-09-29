#!/usr/bin/env bash
# One purchase end-to-end on each public host and the resulting order/payment/confirmation records.
#   before: POST /api/purchase -> 201 CONFIRMED synchronously.
#   after:  POST /api/purchase -> 202 PENDING_PAYMENT, then order-placed -> payments -> payment-captured ->
#           confirmations -> order-confirmed; polls GET /api/orders/{ref} until CONFIRMED.
#   usage: smoke.sh <token> [performanceId]
source "$(dirname "$0")/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
PERF="${2:-1}"; KEY="smoke-$(date -u +%Y%m%dt%H%M%S)"
body() { printf '{"performanceId":%s,"email":"%s@example.test","quantity":2,"cardLast4":"4242","clientRef":"%s"}' "${PERF}" "$1" "$1"; }
post() { pub_curl "$1/api/purchase" -s -m 60 -o "$2" -w '%{http_code}' -H 'Content-Type: application/json' -X POST --data "$3"; }
rc=0

HB="https://$(host_before "${TOKEN}")"
code="$(post "${HB}" /tmp/"${TOKEN}"-smoke-before.json "$(body "${KEY}-before")")"
echo "== before ${HB}: POST /api/purchase -> ${code}"; jq -c . /tmp/"${TOKEN}"-smoke-before.json
ref="$(jq -r '.orderRef // empty' /tmp/"${TOKEN}"-smoke-before.json)"
if [ "${code}" = 201 ] && [ -n "${ref}" ]; then
  echo "   GET /api/orders/${ref}: $(pub_curl "${HB}/api/orders/${ref}" -s -m 20 | jq -c '{status, payment_outcome: (.paymentOutcome // .payment_outcome), tickets: ((.tickets // .items) | length)}')"
else echo "   FAIL: expected 201 with orderRef"; rc=1; fi

HA="https://$(host_after "${TOKEN}")"
code="$(post "${HA}" /tmp/"${TOKEN}"-smoke-after.json "$(body "${KEY}-after")")"
echo "== after ${HA}: POST /api/purchase -> ${code}"; jq -c . /tmp/"${TOKEN}"-smoke-after.json
ref="$(jq -r '.orderRef // empty' /tmp/"${TOKEN}"-smoke-after.json)"
if [ "${code}" = 202 ] && [ -n "${ref}" ]; then
  status=""; t0=${SECONDS}
  while (( SECONDS - t0 < 120 )); do
    status="$(pub_curl "${HA}/api/orders/${ref}" -s -m 20 | jq -r '.status // empty')"
    case "${status}" in CONFIRMED|PAYMENT_FAILED|PAYMENT_TIMEOUT|CANCELLED) break ;; esac
    sleep 3
  done
  echo "   GET /api/orders/${ref} after $((SECONDS - t0))s: $(pub_curl "${HA}/api/orders/${ref}" -s -m 20 | jq -c '{status, payment_outcome: (.paymentOutcome // .payment_outcome), total_cents, tickets: ([.items[]? | select(.ticket_code != null)] | length)}')"
  echo "   GET /api/payments/${ref}: $(pub_curl "${HA}/api/payments/${ref}" -s -m 20 | jq -c '{status, amountCents, attempts: (.attempts|length)}' 2>/dev/null || echo '(payments at 0 replicas)')"
  echo "   GET /api/confirmations/${ref}: $(pub_curl "${HA}/api/confirmations/${ref}" -s -m 20 | jq -c '{ticketCount, confirmation: .confirmation.status}')"
  [ "${status}" = CONFIRMED ] || { echo "   FAIL: order ${ref} ended ${status:-pending}"; rc=1; }
else echo "   FAIL: expected 202 with orderRef"; rc=1; fi
echo "== stats"; echo "   before: $(pub_curl "${HB}/api/stats" -s -m 20 | jq -c . | cut -c1-200)"; echo "   after:  $(pub_curl "${HA}/api/stats" -s -m 20 | jq -c . | cut -c1-200)"
exit "${rc}"
