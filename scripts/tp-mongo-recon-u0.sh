#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/.migration/recon/U0"
# The org-level blueprint provisions the standard recon venv at this path.
RECON="${RECON:-/home/ubuntu/.venvs/recon/bin/recon}"
if [[ "$RECON" == "/home/ubuntu/.venvs/recon/bin/recon" && ! -x "$RECON" ]]; then
  RECON=recon
fi
RECON_BIN="$RECON"
if [[ -x "/home/ubuntu/.venvs/recon/bin/python" ]]; then
  PYTHON="/home/ubuntu/.venvs/recon/bin/python"
else
  PYTHON="${PYTHON:-/home/ubuntu/venvs/recon/bin/python}"
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
  return 0
}

run_recon \
  --unit U0-core \
  --mapping "$OUT/mapping/core.json" \
  --out "$OUT/core/"
run_recon \
  --unit U0-fixture_meta \
  --mapping "$OUT/mapping/fixture_meta.json" \
  --out "$OUT/fixture_meta/"
for code_type in "${EXPECTED_TYPES[@]}"; do
  run_recon \
    --unit "U0-codes-$code_type" \
    --mapping "$OUT/mapping/codes.json" \
    --param "code_type=$code_type" \
    --out "$OUT/codes/$code_type/"
done

printf '%s\n' 'unit | verdict'
printf '%s\n' '-----|--------'
python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
runs = [
    ("U0-core", out / "core" / "result.json"),
    ("U0-fixture_meta", out / "fixture_meta" / "result.json"),
]
runs.extend(
    (
        f"U0-codes-{code_type}",
        out / "codes" / code_type / "result.json",
    )
    for code_type in (
        "CUST_STATUS", "CUST_TYPE", "DUN_STATUS", "INV_STATUS", "NOTIF_KIND",
        "PHONE_TYPE", "PLAN_TIER", "SUB_STATUS", "TENANT_STATUS", "USAGE_KIND",
    )
)
for unit, path in runs:
    result = json.loads(path.read_text())
    print(f"{unit} | {result['verdict']}")
PY
exit 0
