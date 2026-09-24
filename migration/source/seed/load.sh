#!/usr/bin/env bash
# load.sh <dir> - apply the ARCHIVE/MIGAUDIT DDL (once) and bulk-load the fixed-width seed files into Db2.
#
# Runs inside the db2-archive pod as the instance owner (db2inst1) or anywhere with a Db2 CLP that
# can CONNECT TO $DB2_DATABASE. Uses `db2 LOAD ... OF ASC` (SEED-SPEC.md §1), never row inserts.
#
# Env: DB2_DATABASE (default D24A), DB2_USER / DB2_PASSWORD (optional; instance owner needs none),
#      LDM_DDL_DIR (default: ../db2/ddl next to this script), LDM_SKIP_DDL=1 to skip DDL,
# Idempotent: if ARCHIVE.DOCARCH already holds the row count in seed-summary.json the load is skipped.
set -euo pipefail

DIR="${1:?usage: load.sh <dir with RETNPLCY.asc DOCARCH.asc FILEAUD.asc seed-summary.json>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DDL_DIR="${LDM_DDL_DIR:-$HERE/../db2/ddl}"
DB="${DB2_DATABASE:-D24A}"
LOG_DIR="${LDM_LOAD_LOG_DIR:-$DIR/load-logs}"
mkdir -p "$LOG_DIR"

log() { printf '%s load.sh %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

for f in RETNPLCY.asc DOCARCH.asc FILEAUD.asc seed-summary.json; do
  [[ -f "$DIR/$f" ]] || { log "missing $DIR/$f"; exit 12; }
done

expected_rows() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["files"][sys.argv[2]]["rows"])' "$DIR/seed-summary.json" "$1"; }

db2_connect() {
  if [[ -n "${DB2_USER:-}" && -n "${DB2_PASSWORD:-}" ]]; then
    db2 -o- connect to "$DB" user "$DB2_USER" using "$DB2_PASSWORD" >/dev/null
  else
    db2 -o- connect to "$DB" >/dev/null
  fi
}

# The CLP front end finds its back end via its parent PID: any extra fork (a pipe, a nested `$(...)`)
# lands on a fresh back end with no connection. Db2 output therefore always goes through a file.
CLP_OUT="$LOG_DIR/.clp.out"
scalar() { db2 -x "$1" > "$CLP_OUT"; local v; read -r v < "$CLP_OUT"; SCALAR="${v//[[:space:]]/}"; }  # result in $SCALAR (no subshell)

# Run one CLP statement; on failure print the Db2 message (SQLCODE/SQLSTATE) and exit 8.
run() {
  if ! db2 -v "$1" > "$CLP_OUT" 2>&1; then
    if [[ "$1" != LOAD* ]] || ! grep -q "SQL3107W\|SQL3500W\|Number of rows committed" "$CLP_OUT"; then
      grep -E 'SQL[0-9]+[NWC]|SQLSTATE' "$CLP_OUT" >&2 || cat "$CLP_OUT" >&2
      db2 connect reset >/dev/null 2>&1 || true
      exit 8
    fi
  fi
  cat "$CLP_OUT"
}

db2_connect
log "connected to $DB"

if [[ "${LDM_SKIP_DDL:-0}" != "1" ]]; then
  scalar "SELECT COUNT(*) FROM SYSCAT.TABLES WHERE TABSCHEMA='ARCHIVE' AND TABNAME='FILEAUD'"
  if [[ "$SCALAR" == "1" ]]; then
    log "DDL already applied, skipping"
  else
    for sql in "$DDL_DIR"/*.sql; do
      log "applying $(basename "$sql")"
      db2 -tvf "$sql" > "$LOG_DIR/ddl-$(basename "$sql").log" 2>&1 || { grep -E 'SQL[0-9]+N' "$LOG_DIR/ddl-$(basename "$sql").log" >&2; exit 8; }
    done
  fi
fi

want=$(expected_rows DOCARCH.asc)
scalar "SELECT COUNT(*) FROM ARCHIVE.DOCARCH"; have="$SCALAR"
if [[ "$have" == "$want" ]]; then
  log "ARCHIVE.DOCARCH already holds $have rows; seed load skipped"
  db2 connect reset >/dev/null
  exit 0
fi
if [[ "$have" != "0" ]]; then
  log "ARCHIVE.DOCARCH holds $have rows (expected 0 or $want); refusing to load on top"
  exit 12
fi

# METHOD L positions come from FIELD-DERIVATION.md §2-4 (1-based, inclusive).
load_table() {
  local table="$1" reclen="$2" positions="$3" file="$DIR/$1.asc"
  local msg="$LOG_DIR/load-$table.msg"
  log "LOAD $file -> ARCHIVE.$table"
  # One line: CLP treats a newline inside the filetmod string as part of the keyword.
  run "LOAD FROM $file OF ASC MODIFIED BY reclen=$reclen binarynumerics packeddecimal timestampformat=\"YYYY-MM-DD-HH.MM.SS.UUUUUUUUUUUU\" METHOD L ($positions) MESSAGES $msg INSERT INTO ARCHIVE.$table NONRECOVERABLE" > "$LOG_DIR/load-$table.log"
  local loaded
  loaded=$(grep -E 'Number of rows committed' "$LOG_DIR/load-$table.log" | awk '{print $NF}')
  local want; want=$(expected_rows "$table.asc")
  if [[ "$loaded" != "$want" ]]; then
    log "ARCHIVE.$table: LOAD committed $loaded rows, expected $want (see $msg)"
    exit 8
  fi
  log "ARCHIVE.$table: $loaded rows"
}

load_table RETNPLCY 128 "1 4, 5 64, 65 66, 67 70, 71 71, 72 75, 76 107"
load_table DOCARCH 256 "1 16, 17 52, 53 54, 55 58, 59 90, 91 106, 107 122, 123 162, 163 170, 171 171, 172 179, 180 243, 244 251, 252 254"
load_table FILEAUD 160 "1 20, 21 36, 37 40, 41 72, 73 84, 85 88, 89 90, 91 105, 106 145"

run "SET INTEGRITY FOR ARCHIVE.RETNPLCY, ARCHIVE.DOCARCH, ARCHIVE.FILEAUD IMMEDIATE CHECKED" > "$LOG_DIR/set-integrity.log"
for t in RETNPLCY DOCARCH FILEAUD; do
  run "RUNSTATS ON TABLE ARCHIVE.$t WITH DISTRIBUTION AND INDEXES ALL" > "$LOG_DIR/runstats-$t.log"
done

for t in RETNPLCY DOCARCH FILEAUD; do
  scalar "SELECT COUNT(*) FROM ARCHIVE.$t"; have="$SCALAR"
  want=$(expected_rows "$t.asc")
  [[ "$have" == "$want" ]] || { log "ARCHIVE.$t has $have rows after load, expected $want"; exit 8; }
  log "verified ARCHIVE.$t rows=$have"
done
db2 connect reset >/dev/null
log "seed load complete"
