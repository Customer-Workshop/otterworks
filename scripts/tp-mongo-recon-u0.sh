#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/.migration/recon/U0"
cd "$REPO_ROOT"
# The org-level blueprint provisions the standard recon venv at this path.
RECON="${RECON:-/home/ubuntu/.venvs/recon/bin/recon}"
if [[ "$RECON" == "/home/ubuntu/.venvs/recon/bin/recon" && ! -x "$RECON" ]]; then
  RECON=recon
fi
RECON_BIN="$RECON"
if [[ -x "/home/ubuntu/.venvs/recon/bin/python" ]]; then
  PYTHON="${PYTHON:-/home/ubuntu/.venvs/recon/bin/python}"
elif [[ -x "/home/ubuntu/venvs/recon/bin/python" ]]; then
  PYTHON="${PYTHON:-/home/ubuntu/venvs/recon/bin/python}"
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
  --out "$OUT/mapping/core.json" \
  --collection tenants --collection plans
"$PYTHON" "$REPO_ROOT/scripts/tp_mongo/unit_mapping.py" \
  --out "$OUT/mapping/codes.json" \
  --collection codes
"$PYTHON" "$REPO_ROOT/scripts/tp_mongo/unit_mapping.py" \
  --out "$OUT/mapping/fixture_meta.json" \
  --collection fixture_meta

# schema/01_tables.sql (7) and schema/02_horror.sql (3) are the evidence-backed
# sources; coverage.md has the CODES row but does not enumerate code_type values.
EXPECTED_TYPES=(
  CUST_STATUS CUST_TYPE DUN_STATUS INV_STATUS NOTIF_KIND PHONE_TYPE
  PLAN_TIER SUB_STATUS TENANT_STATUS USAGE_KIND
)
CODE_TYPES="$("$PYTHON" "$REPO_ROOT/scripts/tp_mongo/code_types.py" \
  --dsn-secret OW_BILLING_FIXTURE_DSN)"
printf '%s\n' "$CODE_TYPES" > "$OUT/code_types.txt"
actual_count="$(printf '%s\n' "$CODE_TYPES" | sed '/^$/d' | wc -l)"
if [[ "$actual_count" -ne 10 ]]; then
  echo "ERROR: expected exactly 10 Oracle CODE_TYPE values, found $actual_count" >&2
  diff -u \
    <(printf '%s\n' "${EXPECTED_TYPES[@]}" | sort) \
    <(printf '%s\n' "$CODE_TYPES" | sed '/^$/d' | sort) >&2 || true
  exit 2
fi
if ! diff -u \
  <(printf '%s\n' "${EXPECTED_TYPES[@]}" | sort) \
  <(printf '%s\n' "$CODE_TYPES" | sed '/^$/d' | sort); then
  echo "ERROR: Oracle CODE_TYPE values differ from the evidence-backed expected list" >&2
  exit 2
fi

run_recon() {
  local unit="$1"
  local out_dir="$2"
  shift 2
  rm -rf "$out_dir"
  set +e
  "$RECON_BIN" run \
    --family oracle \
    --tolerances "$REPO_ROOT/.migration/02_tolerances.json" \
    --canonicalization "$REPO_ROOT/.migration/recon_canonicalization.json" \
    --mode live \
    --source-dsn-secret OW_BILLING_FIXTURE_DSN \
    --target-uri-secret MONGODB_ATLAS_URI \
    --target-db ow_tp_mongodb_032752 \
    --source-concurrency 1 \
    --seed 0 \
    "$@"
  local rc=$?
  set -e
  RUN_UNITS+=("$unit")
  RUN_OUTS+=("$out_dir")
  RUN_RCS+=("$rc")
}

RUN_UNITS=()
RUN_OUTS=()
RUN_RCS=()
run_recon \
  U0-core "$OUT/core/" \
  --unit U0-core \
  --mapping "$OUT/mapping/core.json" \
  --out "$OUT/core/"
run_recon \
  U0-fixture_meta "$OUT/fixture_meta/" \
  --unit U0-fixture_meta \
  --mapping "$OUT/mapping/fixture_meta.json" \
  --out "$OUT/fixture_meta/"
for code_type in "${EXPECTED_TYPES[@]}"; do
  run_recon \
    "U0-codes-$code_type" "$OUT/codes/$code_type/" \
    --unit "U0-codes-$code_type" \
    --mapping "$OUT/mapping/codes.json" \
    --param "code_type=$code_type" \
    --out "$OUT/codes/$code_type/"
done

printf '%s\n' 'unit | verdict | rc'
printf '%s\n' '-----|---------|---'
overall_rc=0
for index in "${!RUN_UNITS[@]}"; do
  unit="${RUN_UNITS[$index]}"
  out_dir="${RUN_OUTS[$index]}"
  invocation_rc="${RUN_RCS[$index]}"
  result_path="$out_dir/result.json"
  verdict="MISSING"
  if [[ -f "$result_path" ]]; then
    if verdict="$("$PYTHON" - "$result_path" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    result = json.load(handle)
print(result["verdict"])
PY
)"; then
      :
    else
      verdict="UNPARSEABLE"
    fi
  fi
  printf '%s | %s | %s\n' "$unit" "$verdict" "$invocation_rc"
  if [[ "$invocation_rc" -ne 0 || "$verdict" != "PASS" ]]; then
    overall_rc=1
  fi
done
exit "$overall_rc"
