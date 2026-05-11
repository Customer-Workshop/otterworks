#!/bin/bash
set -euo pipefail

# OtterWorks Seed Data Loader
# Loads development data into running services.
# Idempotent: safe to run multiple times.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SEED_DIR="$REPO_ROOT/seed-data"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[seed]${NC} $1"; }
warn() { echo -e "${YELLOW}[seed]${NC} $1"; }
err()  { echo -e "${RED}[seed]${NC} $1" >&2; }

# Check dependencies
check_deps() {
  for cmd in psql aws jq curl; do
    if ! command -v "$cmd" &>/dev/null; then
      warn "Missing $cmd -- some seed steps will be skipped"
    fi
  done
}

# Postgres seed data (auth-service + document-service)
seed_postgres() {
  log "Seeding PostgreSQL (auth-service)..."
  if command -v psql &>/dev/null; then
    PGPASSWORD="${POSTGRES_PASSWORD:-otterworks}" psql \
      -h "${POSTGRES_HOST:-localhost}" \
      -p "${POSTGRES_PORT:-5432}" \
      -U "${POSTGRES_USER:-otterworks}" \
      -d otterworks \
      -f "$SEED_DIR/postgres/001_seed_users.sql" \
      2>&1 | grep -v "INSERT 0 0" || true
    log "  Users seeded."

    log "Seeding PostgreSQL (document-service)..."
    PGPASSWORD="${POSTGRES_PASSWORD:-otterworks}" psql \
      -h "${POSTGRES_HOST:-localhost}" \
      -p "${POSTGRES_PORT:-5432}" \
      -U "${POSTGRES_USER:-otterworks}" \
      -d otterworks \
      -f "$SEED_DIR/postgres/002_seed_documents.sql" \
      2>&1 | grep -v "INSERT 0 0" || true
    log "  Documents seeded."
  else
    warn "psql not found -- skipping PostgreSQL seed"
  fi
}

# DynamoDB seed data (file-metadata, audit-events, notifications)
seed_dynamodb() {
  log "Seeding DynamoDB tables..."
  if command -v aws &>/dev/null; then
    local endpoint="${AWS_ENDPOINT_URL:-http://localhost:4566}"

    for table_file in "$SEED_DIR"/dynamodb/*.json; do
      local filename
      filename=$(basename "$table_file")
      log "  Loading $filename..."

      # Each JSON file has a top-level key matching the table name
      for table_name in $(jq -r 'keys[]' "$table_file"); do
        local count
        count=$(jq -r ".[\"$table_name\"] | length" "$table_file")
        log "    Table $table_name: $count items"

        jq -c ".[\"$table_name\"][]" "$table_file" | while read -r item; do
          aws dynamodb put-item \
            --endpoint-url "$endpoint" \
            --table-name "$table_name" \
            --item "$item" \
            --condition-expression "attribute_not_exists(id)" \
            --region us-east-1 \
            2>/dev/null || true
        done
      done
    done
    log "  DynamoDB seeded."
  else
    warn "aws CLI not found -- skipping DynamoDB seed"
  fi
}

# MeiliSearch seed data
seed_search() {
  log "Seeding MeiliSearch..."
  local meili_url="${MEILISEARCH_URL:-http://localhost:7700}"

  if curl -sf "$meili_url/health" &>/dev/null; then
    # Create indexes if they don't exist
    curl -sf -X POST "$meili_url/indexes" \
      -H "Content-Type: application/json" \
      -d '{"uid":"otterworks-documents","primaryKey":"_id"}' 2>/dev/null || true
    curl -sf -X POST "$meili_url/indexes" \
      -H "Content-Type: application/json" \
      -d '{"uid":"otterworks-files","primaryKey":"_id"}' 2>/dev/null || true

    # Bulk load from the search index seed (NDJSON format, every other line is data)
    # Extract document entries and file entries separately
    local seed_file="$SEED_DIR/opensearch/search-index-seed.json"
    if [ -f "$seed_file" ]; then
      # Parse the NDJSON: action lines alternate with data lines
      local docs_json="[]"
      local files_json="[]"
      local current_index=""

      while IFS= read -r line; do
        # Check if this is an index action line
        if echo "$line" | jq -e '.index' &>/dev/null; then
          current_index=$(echo "$line" | jq -r '.index._index')
          local doc_id
          doc_id=$(echo "$line" | jq -r '.index._id')
        else
          # This is a data line - add the _id and append to the right array
          local enriched
          enriched=$(echo "$line" | jq --arg id "$doc_id" '. + {"_id": $id}')
          if [ "$current_index" = "otterworks-documents" ]; then
            docs_json=$(echo "$docs_json" | jq --argjson item "$enriched" '. + [$item]')
          elif [ "$current_index" = "otterworks-files" ]; then
            files_json=$(echo "$files_json" | jq --argjson item "$enriched" '. + [$item]')
          fi
        fi
      done < "$seed_file"

      # Post to MeiliSearch
      echo "$docs_json" | curl -sf -X POST "$meili_url/indexes/otterworks-documents/documents" \
        -H "Content-Type: application/json" -d @- 2>/dev/null || true
      echo "$files_json" | curl -sf -X POST "$meili_url/indexes/otterworks-files/documents" \
        -H "Content-Type: application/json" -d @- 2>/dev/null || true

      log "  MeiliSearch seeded."
    fi
  else
    warn "MeiliSearch not reachable -- skipping search seed"
  fi
}

main() {
  log "========================================="
  log "  OtterWorks Seed Data Loader"
  log "  \"Every otter needs a well-stocked river\""
  log "========================================="
  echo

  check_deps
  seed_postgres
  seed_dynamodb
  seed_search

  echo
  log "Seed data loading complete!"
  log "  Users:          25 otter-themed engineers"
  log "  Documents:      30 RFCs, ADRs, runbooks, and more"
  log "  Files:          16 DynamoDB file metadata entries"
  log "  Audit events:   30 trail entries"
  log "  Notifications:  20 mixed read/unread"
  log "  Search index:   Documents and files indexed"
  echo
  log "Browse the web app at http://localhost:3000"
  log "Admin dashboard at http://localhost:4200"
}

main "$@"
