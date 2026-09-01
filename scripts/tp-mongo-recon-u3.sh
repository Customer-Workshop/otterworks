#!/usr/bin/env bash
# One harness run over the U3 subscriptions feed; result.json is the only merge authority.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/.migration/recon/U3"
cd "$REPO_ROOT"
RECON="${RECON:-/home/ubuntu/.venvs/recon/bin/recon}"
if [[ "$RECON" == "/home/ubuntu/.venvs/recon/bin/recon" && ! -x "$RECON" ]]; then
  RECON=recon
fi
RECON_BIN="$RECON"
if [[ -x "/home/ubuntu/.venvs/recon/bin/python" ]]; then
  PYTHON="${PYTHON:-/home/ubuntu/.venvs/recon/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

if [[ ! -v OW_BILLING_FIXTURE_DSN ]]; then
  echo "ERROR: OW_BILLING_FIXTURE_DSN must be set in the environment" >&2
  exit 2
fi
if [[ ! -v MONGODB_ATLAS_URI ]]; then
  echo "ERROR: MONGODB_ATLAS_URI must be set in the environment" >&2
  exit 2
fi
if ! command -v "$RECON_BIN" >/dev/null 2>&1; then
  echo "ERROR: recon CLI not found: $RECON_BIN" >&2
  exit 2
fi

mkdir -p "$OUT"
"$PYTHON" "$REPO_ROOT/scripts/tp_mongo/unit_mapping.py" \
  --out "$OUT/mapping/u3.json" \
  --collection subscriptions \
  --collection subscriptions_hist

RUN_OUT="${1:-$OUT/gate/}"
rm -rf "$RUN_OUT"
set +e
"$RECON_BIN" run \
  --unit U3 \
  --family oracle \
  --mapping "$OUT/mapping/u3.json" \
  --tolerances "$REPO_ROOT/.migration/02_tolerances.json" \
  --canonicalization "$REPO_ROOT/.migration/recon_canonicalization.json" \
  --mode live \
  --source-dsn-secret OW_BILLING_FIXTURE_DSN \
  --target-uri-secret MONGODB_ATLAS_URI \
  --target-db ow_tp_mongodb_032752 \
  --source-concurrency 1 \
  --seed 0 \
  --out "$RUN_OUT"
rc=$?
set -e

result="$RUN_OUT/result.json"
verdict="MISSING"
if [[ -f "$result" ]]; then
  verdict="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$result" \
    2>/dev/null || echo UNPARSEABLE)"
fi
printf 'U3 | %s | rc=%s\n' "$verdict" "$rc"
[[ "$rc" -eq 0 && "$verdict" == "PASS" ]]
