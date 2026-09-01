#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/.migration/recon/U5"
RECON="${RECON:-/home/ubuntu/.venvs/recon/bin/recon}"
if [[ "$RECON" == "/home/ubuntu/.venvs/recon/bin/recon" && ! -x "$RECON" ]]; then
  RECON=recon
fi
PYTHON="${PYTHON:-/home/ubuntu/.venvs/recon/bin/python}"

if [[ ! -v OW_BILLING_FIXTURE_DSN || ! -v MONGODB_ATLAS_URI ]]; then
  echo "ERROR: OW_BILLING_FIXTURE_DSN and MONGODB_ATLAS_URI must be set" >&2
  exit 2
fi
if ! command -v "$RECON" >/dev/null 2>&1; then
  echo "ERROR: recon CLI not found: $RECON" >&2
  exit 2
fi

mkdir -p "${OUT}/mapping"
cd "${REPO_ROOT}"
"$PYTHON" "${REPO_ROOT}/scripts/tp_mongo/unit_mapping.py" \
  --out "${OUT}/mapping/u5.json" \
  --collection invoices \
  --collection credit_notes \
  --exclude-embed invoices.dunning_attempts

RUN_OUT="${1:-${OUT}/gate/}"
rm -rf "$RUN_OUT"
set +e
"$RECON" run \
  --unit U5 \
  --family oracle \
  --mapping "${OUT}/mapping/u5.json" \
  --tolerances "${REPO_ROOT}/.migration/02_tolerances.json" \
  --canonicalization "${REPO_ROOT}/.migration/recon_canonicalization.json" \
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
printf 'U5 | %s | rc=%s\n' "$verdict" "$rc"
[[ "$rc" -eq 0 && "$verdict" == "PASS" ]]
