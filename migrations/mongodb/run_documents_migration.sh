#!/usr/bin/env bash
# Run the document-estate migration twice and reconcile the result.
#
# Two runs are not redundant: the second one is what proves idempotency, and the
# recon report compares the store fingerprint taken after each of them.
#
# Usage:
#   migrations/mongodb/run_documents_migration.sh [NS] [RUN_MODE]
#
# Environment:
#   TP_MONGO_FIXTURE_URI  local deployment for RUN_MODE=fixture (default
#                         mongodb://localhost:27117)
#   DB_HOST/DB_PORT/...   legacy Postgres estate connection
#   EVIDENCE_DIR          where run summaries/fingerprints are written
#                         (default docs/tech-partnerships/recon/evidence)
set -euo pipefail

NS="${1:-demo}"
RUN_MODE="${2:-fixture}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/docs/tech-partnerships/recon/evidence}"
REPORT="$ROOT/docs/tech-partnerships/recon/mongo_documents.recon.json"

mkdir -p "$EVIDENCE_DIR"
cd "$ROOT"

run() { scripts/tp-run-deterministic.sh "$@"; }
migrate() { run uv run migrations/mongodb/migrate_documents.py "$@"; }
recon() { run uv run migrations/mongodb/recon_documents.py "$@"; }

echo "== policy self-test (paths this estate's rows do not exercise) =="
migrate --self-test

echo "== migration run 1 (ns=$NS run_mode=$RUN_MODE) =="
migrate --ns "$NS" --run-mode "$RUN_MODE" \
  --summary-json "$EVIDENCE_DIR/mongo_documents.$NS.run1.summary.json"
recon fingerprint --ns "$NS" --run-mode "$RUN_MODE" \
  --out "$EVIDENCE_DIR/mongo_documents.$NS.run1.fingerprint.json"

echo "== migration run 2 (idempotency) =="
migrate --ns "$NS" --run-mode "$RUN_MODE" \
  --summary-json "$EVIDENCE_DIR/mongo_documents.$NS.run2.summary.json"
recon fingerprint --ns "$NS" --run-mode "$RUN_MODE" \
  --out "$EVIDENCE_DIR/mongo_documents.$NS.run2.fingerprint.json"

echo "== reconciliation =="
recon report --ns "$NS" --run-mode "$RUN_MODE" \
  --after-first "$EVIDENCE_DIR/mongo_documents.$NS.run1.fingerprint.json" \
  --after-second "$EVIDENCE_DIR/mongo_documents.$NS.run2.fingerprint.json" \
  --out "$REPORT"

echo "== recon report schema gate =="
make tp-validate-recon FILE="$REPORT"
