#!/usr/bin/env bash
# run.sh <TABLE> <KEY_FROM> <KEY_TO> <OUT_FILE>  - manifest `source.unload_command` (CONTRACTS.md 5.4)
#
# Unloads every row of ARCHIVE.<TABLE> matching $LDM_SELECT_WHERE and KEY_FROM <= key <= KEY_TO,
# ordered by key, as copybook-exact fixed-width records:
#   1. db2 EXPORT ... OF DEL (NOCHARDEL, '|' delimited, FOR BIT DATA columns as HEX()) -> work file
#   2. UNLOAD01 (GnuCOBOL) formats the work file into OUT_FILE
#   3. sidecars OUT_FILE.cnt (row count) and OUT_FILE.sha256 (sha256sum format)
# Last stdout line:  UNLOAD01 ROWS=<n> BYTES=<n*LRECL> SHA256=<hex>
# Exit: 0 ok | 8 Db2 error ("SQLCODE=<n> SQLSTATE=<s>: ..." on stderr) | 12 I/O error
#
# Env: LDM_SELECT_WHERE (complete SQL boolean, default 1=1), DB2_DATABASE (default D24A),
#      DB2_USER / DB2_PASSWORD (optional), UNLOAD01_DEL=<file> to skip Db2 and format an existing
#      export (local tests). Read-only: this script never updates or deletes Db2 rows.
set -euo pipefail

TABLE="${1:?usage: run.sh <TABLE> <KEY_FROM> <KEY_TO> <OUT_FILE>}"
KEY_FROM="${2?}"
KEY_TO="${3?}"
OUT="${4:?usage: run.sh <TABLE> <KEY_FROM> <KEY_TO> <OUT_FILE>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HERE/bin/UNLOAD01"
WHERE="${LDM_SELECT_WHERE:-1=1}"
DB="${DB2_DATABASE:-D24A}"

die_io() { echo "UNLOAD01 E: $*" >&2; exit 12; }

case "$TABLE" in
  RETNPLCY)
    KEY=POLICY_CODE; LRECL=128
    COLS="POLICY_CODE, POLICY_DESC, RETENTION_YEARS, SUCCESSOR_CODE, ACTIVE_FLAG, DISPOSITION_ACTION, EFFECTIVE_TS" ;;
  DOCARCH)
    KEY=ARCH_KEY; LRECL=256
    COLS="ARCH_KEY, DOC_ID, VERSION_NO, RETENTION_CLASS, LAST_ACCESS_TS, STORAGE_CHARGE, UNIT_RATE, HEX(OWNER_NAME), HEX(DISPOSITION_DT), LEGAL_HOLD_FLAG, CHECKSUM_ALG, CONTENT_SHA256, BYTE_SIZE, SOURCE_SYS" ;;
  FILEAUD)
    KEY=AUDIT_KEY; LRECL=160
    COLS="AUDIT_KEY, ARCH_KEY, EVENT_TYPE, EVENT_TS, ACTOR_ID, RETENTION_CLASS, DISPOSITION_CODE, CLIENT_IP, DETAIL_TEXT" ;;
  *) die_io "unknown table '$TABLE' (RETNPLCY|DOCARCH|FILEAUD)" ;;
esac

[[ -x "$BIN" ]] || make -s -C "$HERE" build >&2 || die_io "cannot build $BIN"
mkdir -p "$(dirname "$OUT")" || die_io "cannot create $(dirname "$OUT")"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/unload01.XXXXXX")" || die_io "mktemp failed"
trap 'rm -rf "$WORK"' EXIT
DEL="$WORK/$TABLE.del"

if [[ -n "${UNLOAD01_DEL:-}" ]]; then
  cp "$UNLOAD01_DEL" "$DEL" || die_io "cannot read $UNLOAD01_DEL"
else
  # Key bounds are fixed-width CHAR keys (copybooks: [A-Z0-9-], blank-padded to the column width, e.g. the
  # MIG-04 keys); anything else is refused rather than quoted, so a bound can never carry a CLP
  # terminator or SQL into the EXPORT statement.
  for k in "$KEY_FROM" "$KEY_TO"; do
    [[ "$k" =~ ^[A-Za-z0-9_.:-]{1,64}\ {0,64}$ ]] || die_io "key bound '$k' is not a plain key literal"
  done
  command -v db2 >/dev/null || die_io "db2 CLP not on PATH"
  q() { printf "'%s'" "$1"; }
  SQL="SELECT $COLS FROM ARCHIVE.$TABLE WHERE ($WHERE) AND $KEY >= $(q "$KEY_FROM") AND $KEY <= $(q "$KEY_TO") ORDER BY $KEY"
  if [[ -n "${DB2_USER:-}" && -n "${DB2_PASSWORD:-}" ]]; then
    CONNECT="CONNECT TO $DB USER $DB2_USER USING $DB2_PASSWORD"
  else
    CONNECT="CONNECT TO $DB"
  fi
  # Commands go through a 0600 script file so credentials never show up in `ps`. CLP output is
  # scanned for the SQLCODE/SQLSTATE of any failure and re-emitted in the contract format.
  (umask 077; cat >"$WORK/cmds.clp" <<EOF
$CONNECT@
EXPORT TO $DEL OF DEL MODIFIED BY NOCHARDEL COLDEL| MESSAGES $WORK/export.msg $SQL@
CONNECT RESET@
TERMINATE@
EOF
  )
  set +e
  db2 -s -td@ -f "$WORK/cmds.clp" >"$WORK/clp.out" 2>&1
  rc=$?
  set -e
  if (( rc >= 4 )); then
    db2 -o- TERMINATE >/dev/null 2>&1 || true
    # CLP wraps messages, so the SQLSTATE usually sits on the line after the SQLCODE: flatten first.
    text="$(cat "$WORK/clp.out" "$WORK/export.msg" 2>/dev/null | tr '\n' ' ' | tr -s ' ' || true)"
    msg="$(grep -oE 'SQL[0-9]+[NC] .*' <<<"$text" | head -c 300 || true)"
    sqlcode="$(grep -oE 'SQL[0-9]+[NC]' <<<"$text" | head -1 | sed -E 's/SQL0*([0-9]+)[NC]/-\1/' || true)"
    sqlstate="$(grep -oE 'SQLSTATE=[0-9A-Z]{5}' <<<"$text" | head -1 | cut -d= -f2 || true)"
    echo "SQLCODE=${sqlcode:-?} SQLSTATE=${sqlstate:-?????}: ${msg:-db2 CLP rc=$rc}" >&2
    exit 8
  fi
  [[ -f "$DEL" ]] || : >"$DEL"   # zero selected rows: EXPORT still creates the file, guard anyway
fi

set +e
UNLOAD_TABLE="$TABLE" UNLOAD_IN="$DEL" UNLOAD_OUT="$OUT" "$BIN" >"$WORK/unload01.out"
rc=$?
set -e
cat "$WORK/unload01.out"
(( rc == 0 )) || exit 12

rows="$(sed -nE 's/^UNLOAD01 ROWS=([0-9]+)$/\1/p' "$WORK/unload01.out" | tail -1)"
[[ -n "$rows" ]] || die_io "UNLOAD01 produced no ROWS= line"
bytes="$(stat -c %s "$OUT")"
(( bytes == rows * LRECL )) || die_io "$OUT is $bytes bytes, expected $rows x $LRECL"
sha="$(sha256sum "$OUT" | cut -d' ' -f1)"
printf '%s\n' "$rows" >"$OUT.cnt"
printf '%s  %s\n' "$sha" "$(basename "$OUT")" >"$OUT.sha256"
echo "UNLOAD01 ROWS=$rows BYTES=$bytes SHA256=$sha"
