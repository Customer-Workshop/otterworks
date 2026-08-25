#!/usr/bin/env bash
# Prove the reconciliation is not vacuously green.
#
# A recon that would still pass after an anomaly stopped being surfaced proves
# nothing, so this check deliberately drops one reported version gap and one
# reported orphaned snapshot from the migrated store and requires the recon to
# fail with those exact entries listed as `missing`. It also exercises the
# empty-source no-op. The migration is re-run at the end, which restores the
# store (deterministic keys, so the rerun rewrites what was mutated).
#
# Usage: migrations/mongodb/verify_recon_gate.sh [NS] [RUN_MODE]
set -euo pipefail

NS="${1:-demo}"
RUN_MODE="${2:-fixture}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
EVIDENCE_DIR="${EVIDENCE_DIR:-$ROOT/docs/tech-partnerships/recon/evidence}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$ROOT"
mkdir -p "$EVIDENCE_DIR"

run() { scripts/tp-run-deterministic.sh "$@"; }

echo "== 0. provision an empty namespace in the local source fixture =="
run uv run --no-project --with psycopg2-binary python3 - <<'PY'
import sys
sys.path.insert(0, "migrations/mongodb")
import psycopg2
from mongo_common import pg_config

SCHEMA = "otterworks_emptyns"  # never ns=demo: this path issues DDL
DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {SCHEMA}.documents (
    id UUID PRIMARY KEY, title VARCHAR(500) NOT NULL, content TEXT NOT NULL DEFAULT '',
    content_type VARCHAR(50) NOT NULL DEFAULT 'text/markdown', owner_id UUID NOT NULL,
    folder_id UUID, is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    is_template BOOLEAN NOT NULL DEFAULT FALSE, word_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS {SCHEMA}.document_versions (
    id UUID PRIMARY KEY, document_id UUID NOT NULL REFERENCES {SCHEMA}.documents (id),
    version_number INTEGER NOT NULL, title VARCHAR(500) NOT NULL, content TEXT NOT NULL,
    created_by UUID NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS {SCHEMA}.document_snapshots (
    id UUID PRIMARY KEY, document_id UUID NOT NULL, state_b64 TEXT NOT NULL,
    label VARCHAR(100), created_by UUID NOT NULL, created_at TIMESTAMPTZ NOT NULL);
"""
conn = psycopg2.connect(**pg_config())
conn.autocommit = True
conn.cursor().execute(DDL)
conn.close()
print(f"  ok  {SCHEMA} present and empty")
PY

echo "== 1. empty source set is a no-op =="
run uv run migrations/mongodb/migrate_documents.py --ns emptyns --run-mode "$RUN_MODE" \
  --summary-json "$TMP/empty.json"
python3 - "$TMP/empty.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
assert s["empty_source_noop"] is True, s
assert s["migrated"] == {"documents": 0, "versions_embedded": 0, "snapshots": 0}, s
print("  ok  empty source: no-op, exit 0, nothing written")
PY

echo "== 2. drop one surfaced version gap and one surfaced orphan from the store =="
run uv run --no-project --with pymongo==4.8.0 python3 - "$NS" "$RUN_MODE" <<'PY'
import sys, os
sys.path.insert(0, "migrations/mongodb")
from pymongo import MongoClient
from mongo_common import DOCUMENTS, SNAPSHOTS, database_name, mongo_uri

ns, run_mode = sys.argv[1], sys.argv[2]
db = MongoClient(mongo_uri(run_mode))[database_name(ns)]
doc = db[DOCUMENTS].find_one({"ns": ns, "version_gaps": {"$ne": []}})
snap = db[SNAPSHOTS].find_one({"ns": ns, "orphaned": True})
db[DOCUMENTS].update_one({"_id": doc["_id"]}, {"$set": {"version_gaps": []}})
db[SNAPSHOTS].update_one({"_id": snap["_id"]}, {"$set": {"orphaned": False}})
print(f"  mutated document {doc['legacy_id']} (gaps {doc['version_gaps']} -> [])")
print(f"  mutated snapshot {snap['legacy_id']} (orphaned true -> false)")
PY

echo "== 3. recon must FAIL and name the lost anomalies =="
set +e
run uv run migrations/mongodb/recon_documents.py report --ns "$NS" --run-mode "$RUN_MODE" \
  --after-first "$EVIDENCE_DIR/mongo_documents.$NS.run1.fingerprint.json" \
  --after-second "$EVIDENCE_DIR/mongo_documents.$NS.run2.fingerprint.json" \
  --out "$TMP/mutated.recon.json"
status=$?
set -e
python3 - "$TMP/mutated.recon.json" "$status" <<'PY'
import json, sys
report, status = json.load(open(sys.argv[1])), int(sys.argv[2])
missing = report["planted_anomaly_detections"]["missing"]
assert status != 0, "recon exited zero after an anomaly stopped being surfaced"
assert len(missing) == 2, missing
assert any(m.startswith("version_gaps:") for m in missing), missing
assert any(m.startswith("orphaned_snapshots:") for m in missing), missing
failed = [c["id"] for c in report["checks"] if c["result"] != "pass"]
print(f"  ok  recon exit={status}, missing={missing}")
print(f"  ok  failing checks: {failed}")
PY

echo "== 4. re-run the migration to restore the store =="
run uv run migrations/mongodb/migrate_documents.py --ns "$NS" --run-mode "$RUN_MODE" \
  --summary-json "$TMP/restore.json" > /dev/null
run uv run migrations/mongodb/recon_documents.py report --ns "$NS" --run-mode "$RUN_MODE" \
  --after-first "$EVIDENCE_DIR/mongo_documents.$NS.run1.fingerprint.json" \
  --after-second "$EVIDENCE_DIR/mongo_documents.$NS.run2.fingerprint.json" \
  --out "$TMP/restored.recon.json" > /dev/null
python3 - "$TMP/restored.recon.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
failed = [c["id"] for c in report["checks"] if c["result"] != "pass"]
assert not failed, failed
assert report["planted_anomaly_detections"]["missing"] == []
print("  ok  store restored by rerun, recon green again")
PY
echo "recon gate verified: an unsurfaced planted anomaly fails the reconciliation"
