#!/bin/bash
#############################################################
# legacy_pain.sh — the "before" beat for the Databricks demo.
#
# Stages, deterministically and in its own sandbox, the two
# reasons the CUSTBILL estate has to go:
#
#   blast     A one-line business ask ("add a 2% late-fee
#             surcharge to overdue invoices on the finance
#             report") mapped to every place the estate would
#             have to change: ksh + bash + perl + cron.
#   baseline  Run the whole legacy chain end to end. Everything
#             exits 0, warns about stale locks, and finishes
#             "done (probably)" — there is nothing to validate.
#   poison    Drop one malformed CUSTBILL file. The chain
#             swallows it: the finance totals move, nothing
#             errors, exit code is still 0.
#   all       blast + baseline + poison.
#   clean     Remove the sandbox.
#
# Never touches etl/legacy-extra/jobs/ (immutable estate) and
# never touches another harness's legacy root: it works in its
# own sandbox, OTTERWORKS_PAIN_ROOT (default
# /tmp/otterworks-legacy-pain). An inherited OTTERWORKS_LEGACY_ROOT
# is deliberately ignored so a prepared demo root can never be the
# rm -rf target.
#############################################################
set -u

HERE="$(cd "$(dirname "$0")/../.." && pwd)"
ESTATE="$HERE/etl/legacy-extra"
ROOT="${OTTERWORKS_PAIN_ROOT:-/tmp/otterworks-legacy-pain}"
NS="${NS:-pain}"
ACT="${1:-all}"

export OTTERWORKS_LEGACY_ROOT="$ROOT"

rule() { printf '%s\n' "----------------------------------------------------------------------"; }

report_total() {
    # grand total across the newest finance report, cents-exact via awk
    local latest
    latest=$(ls -1t "$ROOT"/reports/finance_billing_*.csv 2>/dev/null | head -1)
    [ -n "$latest" ] || { echo "none"; return; }
    awk -F, 'NR>1 {t+=$4*100} END {printf "%.2f", t/100}' "$latest"
}

report_body() {
    local latest
    latest=$(ls -1t "$ROOT"/reports/finance_billing_*.csv 2>/dev/null | head -1)
    [ -n "$latest" ] && sed 's/^/    /' "$latest"
}

run_chain() {
    ksh "$ESTATE/jobs/sftp_ingest_poll.ksh"
    bash "$ESTATE/jobs/parse_custbill_fixedwidth.sh"
    perl "$ESTATE/jobs/finance_excel_report.pl"
}

act_blast() {
    rule
    echo "THE ASK (one line from finance):"
    echo "  'Add a 2% late-fee surcharge to overdue invoices on the monthly report.'"
    echo
    echo "WHERE THAT ONE RULE HAS TO LAND — the blast radius:"
    echo
    echo "[perl 5.005, no modules] the report of record — amounts are summed here:"
    grep -n 'tot{\$key} += \$amt\|rtname =' "$ESTATE/jobs/finance_excel_report.pl" | sed 's/^/    finance_excel_report.pl:/'
    echo
    echo "[bash + sed/awk/cut] the parser — the only place that knows the amount format:"
    grep -n 'implied decimal\|amt=\$4+0\|pos 49-60\|pos 64-65' "$ESTATE/jobs/parse_custbill_fixedwidth.sh" | sed 's/^/    parse_custbill_fixedwidth.sh:/'
    echo
    echo "[ksh, 1998] the ingest — 'overdue' needs the bill date, which only survives if timing holds:"
    grep -n 'TIMING IS LOAD BEARING\|continuing anyway\|hope the file is complete' "$ESTATE/jobs/sftp_ingest_poll.ksh" | sed 's/^/    sftp_ingest_poll.ksh:/'
    echo
    echo "[cron] when it runs is part of the business logic:"
    grep -n 'CUSTBILL\|run_all\|02:0\|every 15' "$ESTATE/crontab" | sed 's/^/    crontab:/'
    echo
    echo "[bash] orchestration = sleep:"
    grep -n 'sleep \$SLEEP\|done (probably)' "$ESTATE/run_all.sh" | sed 's/^/    run_all.sh:/'
    echo
    echo "SCORECARD: 1 business rule -> 3 languages + cron, 0 tests, 0 validation,"
    echo "           and the only person who understood the chain left in 2020."
    rule
}

act_baseline() {
    rule
    echo "BASELINE RUN — the estate at its best (sandbox: $ROOT, NS=$NS):"
    rm -rf "$ROOT"
    mkdir -p "$ROOT"
    perl "$ESTATE/tools/gen_sample_data.pl" "$NS"
    run_chain
    echo
    echo "Finance report of record ($(ls -1t "$ROOT"/reports/finance_billing_*.xls 2>/dev/null | head -1 | xargs -r basename)) — CSV renamed to .xls:"
    report_body
    echo
    echo "BASELINE grand total: $(report_total)"
    echo "$(report_total)" > "$ROOT/.baseline_total"
    echo "Note every stage above exited 0. That is the entire validation story."
    rule
}

act_poison() {
    rule
    echo "POISON — one malformed CUSTBILL file lands in the drop:"
    [ -f "$ROOT/.baseline_total" ] || { echo "run baseline first (make tp-legacy-pain ACT=baseline)"; return 1; }
    local drop="$ROOT/sftp-drop/upload" f="CUSTBILL_${NS^^}_999.dat"
    mkdir -p "$drop"
    {
        printf 'HDR CUSTBILL EXTRACT NS=%-10s FILE=999%s\n' "${NS^^}" "                    "
        # invalid calendar date (Feb 31) and a non-numeric amount field —
        # exactly what the copybook says cannot happen
        printf 'C999999999%-30.30s%s%s%s%s\n' "LATE N SHADY LLC" "20240231" "0000000ABCDE" "USD" "01"
        printf 'C999999998%-30.30s%s%s%s%s\n' "LATE N SHADY LLC" "20240231" "000099999999" "USD" "02"
        printf 'TRL%010d\n' 2
    } > "$drop/$f"
    echo "  planted $f:"
    sed 's/^/    /' "$drop/$f"
    echo
    run_chain
    echo
    local before after
    before=$(cat "$ROOT/.baseline_total")
    after=$(report_total)
    echo "Finance report after the bad file (still exit 0, still no error anywhere):"
    report_body
    echo
    echo "GRAND TOTAL before: $before"
    echo "GRAND TOTAL after:  $after"
    echo "The malformed records flowed straight into the finance totals:"
    echo "  a Feb-31 'date' and a non-numeric amount were parsed, summed and shipped."
    echo "Nothing failed. Nothing was quarantined. Finance would never know."
    rule
}

act_clean() {
    rm -rf "$ROOT"
    echo "removed $ROOT"
}

case "$ACT" in
    blast)    act_blast ;;
    baseline) act_baseline ;;
    poison)   act_poison ;;
    all)      act_blast; act_baseline; act_poison ;;
    clean)    act_clean ;;
    *) echo "usage: legacy_pain.sh [blast|baseline|poison|all|clean]"; exit 1 ;;
esac
