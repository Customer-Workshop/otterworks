#!/usr/bin/env bash
# Capture the pinned CUSTBILL legacy baseline: run the real legacy chain over a fixed
# fixture set and keep its outputs verbatim.
#
#   databricks/migration/p2/baseline/capture_legacy_baseline.sh [OUT_DIR]
#
# The outputs are the SOURCE side of pipeline 2's reconciliation. They are produced by the
# legacy scripts themselves and are never regenerated from the target: the target
# recomputes from the same raw .dat inputs and never reads these files. Nothing here
# modifies a legacy script.
set -eu

REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
OUT=${1:-$REPO/databricks/migration/p2/baseline/captured}
ROOT=${OTTERWORKS_LEGACY_ROOT:-/tmp/ow-p2-baseline}

rm -rf "$ROOT"
# The captured tree is evidence, so it is rebuilt, not added to: a file left behind by an
# earlier fixture set would be read as part of this baseline by anything comparing against it.
rm -rf "$OUT/inputs" "$OUT/parsed" "$OUT/reports" "$OUT/logs"
mkdir -p "$OUT/inputs" "$OUT/parsed" "$OUT/reports" "$OUT/logs"

export OTTERWORKS_LEGACY_ROOT="$ROOT"
export RUN_ALL_SLEEP=0

# 1. the standard fixture set (two well-formed files, 50 records each)
make -C "$REPO" legacy-etl-gen-data NS=dev >/dev/null

# 2. the adversarial probe set: one record per contract clause that the copybook comment
#    does not describe. These are what pin C-1.*, C-3.*, C-4.* and C-5.1.
python3 "$REPO/databricks/migration/p2/baseline/gen_probe_fixture.py" "$ROOT" >/dev/null

cp "$ROOT"/sftp-drop/upload/*.dat "$OUT/inputs/"

# 3. the real legacy chain, stage by stage
# .txt, not .log: the repo ignores *.log, and an uncommitted baseline is not a baseline.
make -C "$REPO" legacy-etl-run JOB=sftp_ingest_poll          >"$OUT/logs/stage1_ingest.txt" 2>&1
make -C "$REPO" legacy-etl-run JOB=parse_custbill_fixedwidth >"$OUT/logs/stage2_parse.txt"  2>&1
make -C "$REPO" legacy-etl-run JOB=finance_excel_report      >"$OUT/logs/stage3_close.txt"  2>&1

cp "$ROOT"/parsed/*.psv "$OUT/parsed/" 2>/dev/null || true
cp "$ROOT"/reports/*.csv "$ROOT"/reports/*.xls "$OUT/reports/" 2>/dev/null || true

# 4. rerun proof: the parser renames its input .done, so a second pass must be a no-op
make -C "$REPO" legacy-etl-run JOB=parse_custbill_fixedwidth >"$OUT/logs/stage2_parse_rerun.txt" 2>&1

# 5. the .xls is a byte copy of the .csv, not a workbook
for csv in "$OUT"/reports/*.csv; do
  xls="${csv%.csv}.xls"
  [ -f "$xls" ] || continue
  cmp -s "$csv" "$xls" && echo "IDENTICAL $(basename "$csv") $(basename "$xls")" \
                       || echo "DIFFERS   $(basename "$csv") $(basename "$xls")"
done >"$OUT/reports/xls_byte_compare.txt"

echo "baseline captured under $OUT"
