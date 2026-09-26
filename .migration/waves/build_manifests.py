#!/usr/bin/env python3
"""Generate .migration/waves/wave-<N>.json from the unit plan below (playbook 2 step 5).
Re-run after any plan change; do not hand-edit the manifests."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = "ow_billing_migration"
REPO = "github.com/Cognition-Partner-Workshops/otterworks"
BRANCH = "tp-run/mongodb-20260926T164803Z-rt-offline"
FIXTURE = ".migration/fixtures/ow_billing_demo.json"
WIDTH = 3

UNITS = {
    "u-00-codes": dict(cls="reference (bulk-load, tiny)", colls=["codes"], tables=["CODES"], rows=32, xl=False,
        code="loader only; the `codes` reference lookup used by every read path (facade.py:110-119, 213-217, 245-247, 341-344)"),
    "u-01-tenancy": dict(cls="plain collections + history_copy", colls=["tenants", "plans", "subscriptions", "subscriptionsHist"],
        tables=["TENANTS", "PLANS", "SUBSCRIPTIONS", "SUBSCRIPTIONS_HIST"], rows=143, xl=False,
        code="tenant/plan/subscription read paths in services/legacy-billing/app (backends/oracle.py:136-144, facade.py plan/subscription routes)"),
    "u-02-customers": dict(cls="wide-embed (155 cols + attribute-pattern EAV) / bulk-load", colls=["customerMaster", "customerMasterHist"],
        tables=["CUSTOMER_MASTER", "ENTITY_ATTR_VALUE", "CUSTOMER_MASTER_HIST"], rows=33338, xl=True,
        code="customer endpoint facade.py:121-127, 287-298 (customer + attributes); CSV/list and text-date canonicalization per 02_tolerances.md; TRG_CUSTOMER_MASTER_SEQ derived columns computed in the loader"),
    "u-03-invoicing-core": dict(cls="embed 1:few + transactional documents", colls=["invoices", "creditNotes", "ratingPeriods", "ratingResults"],
        tables=["INVOICES", "INVOICE_LINES", "CREDIT_NOTES", "RATING_PERIODS", "RATING_RESULTS"], rows=19, xl=False,
        code="invoice read path facade.py:241-250 (invoice + ordered lines), credit note / rating reads"),
    "u-04-usage-audit": dict(cls="append-only / ttl", colls=["usageEvents", "billingAuditLog"], tables=["USAGE_EVENTS", "BILLING_AUDIT_LOG"], rows=817, xl=False,
        code="/internal/usage/events writer facade.py:381-411 (TRG_USAGE_EVENTS_CHECK validation moves here), usage summary reads facade.py:212-222; TTL index 90d on billingAuditLog (replaces JOB_PURGE_AUDIT_LOG)"),
    "u-05-dunning-data": dict(cls="plain collections", colls=["dunningAttempts", "notifications"], tables=["DUNNING_ATTEMPTS", "NOTIFICATIONS"], rows=2, xl=False,
        code="dunning read path facade.py:337-348"),
    "u-06-invoice-header-bulk": dict(cls="bulk-load embed 1:N with orphan quarantine", colls=["invoiceHeader"], tables=["INVOICE_HEADER", "INVOICE_LINE"], rows=168750, xl=True,
        code="month-end aggregate reports.py:42-88 rebuilt as an aggregation pipeline over invoiceHeader.lines; CUSTBILL extract etl/legacy-extra/tools/oracle_custbill_extract.py:15-28; orphan INVOICE_LINE rows (37 in the fixture) quarantined with reason orphan_line, never dropped silently"),
    "u-07-plsql-util": dict(cls="proc-heavy (calibration)", colls=[], tables=["PKG_OW_UTIL"], rows=0, xl=False,
        code="PKG_OW_UTIL (01_pkg_util.sql:26-77): code lookup, audit write, money rounding helpers -> service module; parity via procs/harness transcripts"),
    "u-08-plsql-plans": dict(cls="proc-heavy", colls=[], tables=["PKG_PLANS", "TRG_SUBSCRIPTIONS_HIST", "TRG_SUB_NO_UNCANCEL"], rows=0, xl=False,
        code="PKG_PLANS (02_pkg_plans.sql:24-104): fn_list_plans, fn_entitlement, sp_change_plan; explicit subscriptionsHist write and the no-uncancel invariant in the service update path"),
    "u-09-plsql-rating": dict(cls="proc-heavy", colls=[], tables=["PKG_RATING"], rows=0, xl=False,
        code="PKG_RATING (03_pkg_rating.sql:32-217): compute_rating, fn_usage_rating, fn_usage_summary, sp_finalize_rating; upserts ratingPeriods/ratingResults"),
    "u-10-plsql-invoicing": dict(cls="proc-heavy", colls=[], tables=["PKG_INVOICING"], rows=0, xl=False,
        code="PKG_INVOICING (04_pkg_invoicing.sql:26-194): compute_preview, fn_invoice_preview, fn_invoice_lines, sp_issue_invoice (single-document replace of invoices with embedded lines), credit-note burn-down"),
    "u-11-plsql-dunning": dict(cls="proc-heavy + scheduled", colls=[], tables=["PKG_DUNNING", "JOB_NIGHTLY_DUNNING"], rows=0, xl=False,
        code="PKG_DUNNING (05_pkg_dunning.sql:17-99): fn_overdue_accounts, sp_schedule_dunning, sp_suspend_overdue; JOB_NIGHTLY_DUNNING becomes a service scheduled task (disabled until cutover)"),
}

# wave -> batches -> units. Data units first (depth 0/1), PL/SQL units after the collections they use exist.
WAVES = {
    0: {"batches": [["u-00-codes"]], "path": "single-session (1 batch)", "cost": "1 child x ~20 min + verify ~15 min"},
    1: {"batches": [["u-01-tenancy"], ["u-02-customers"], ["u-03-invoicing-core"]], "path": "fan-out workflow (3 batches, width 3)",
        "cost": "3 children x ~45 min + verify ~30 min (calibration wave: one unit per pattern class: plain+history, wide-embed XL, embed 1:few)"},
    2: {"batches": [["u-04-usage-audit"], ["u-05-dunning-data"], ["u-06-invoice-header-bulk"]], "path": "fan-out workflow (3 batches, width 3)",
        "cost": "expected 30-50% below wave 1 per unit (patterns calibrated) except u-06 XL bulk-load, which gets a decision-first contract PR"},
    3: {"batches": [["u-07-plsql-util", "u-08-plsql-plans"], ["u-09-plsql-rating", "u-10-plsql-invoicing", "u-11-plsql-dunning"]],
        "path": "single-session (2 batches; proc-heavy class calibrated by u-07 first, then the rest of the batch)",
        "cost": "2 children x ~60 min + verify ~30 min; expected 30-50% below wave 1 per unit once u-07 calibrates the PL/SQL transcript parity path"},
}

RULES = """Rules (AGENTS.md mongo-migration guardrails, all apply):
- Offline engagement: source_access=ddl_only, target_access=local. There is NO live source and NO migration cluster. Every command runs as `env -u MONGODB_ATLAS_URI <command>`. Recon is `--mode fixture --target-class local` only; its PASS is rehearsal evidence and never a merge verdict. auto_merge is false; do not merge your PR; do not ask anyone to.
- Write only to the write_targets listed for your batch, all inside database `ow_billing_migration` on MONGO_LOCAL_URI (mongodb://localhost:27017, container ow-mongo). Drop and recreate only your own collections at the start of every run. Never write to another database or collection; an undeclared target is a halt.
- Never modify the Oracle fixture container, its schema, packages, or data (rule 1). Read it via the DSN named OW_BILLING_FIXTURE_DSN (a demo constant); never paste credential values into files, PRs, or logs.
- Never edit `.migration/` (the orchestrator is the single writer). Read `.migration/03_mapping_spec.json` (version map-draft-2), `02_tolerances.json` (tol-1, exact), `05_decisions.json` (cited decisions incl. quarantine rules), `09_coverage.md`, `07_dependency_register.md`.
- Work on a branch cut from `tp-run/mongodb-20260926T164803Z-rt-offline` named `tp-run/mongodb-20260926T164803Z-rt-offline--<batch id>` and open exactly one PR for your batch against that run branch. Never target `tech-partnerships` or `main`. Do not read, fetch, diff, or search any other branch or PR of this repo.
- Cap yourself at 3 full recon re-runs. Quarantine (with a reason code) rather than drop or silently coerce; report quarantine counts in the PR.
- Follow playbook 3 (`skills/install-mongo-kit/playbooks/3-unit_migration.md`) and the pre-PR checklist `.agents/skills/tp-pre-pr-self-check/SKILL.md` in the repo.
"""


def brief(wave, bid, units):
    lines = [f"Batch {bid} (wave {wave}) of the offline OW_BILLING -> MongoDB migration in {REPO}, run branch {BRANCH}.", ""]
    for u in units:
        d = UNITS[u]
        lines.append(f"Unit {u}{' [XL: decision-first contract PR before code]' if d['xl'] else ''} — pattern class: {d['cls']}.")
        lines.append(f"  Source objects: {', '.join(d['tables'])}. Target collections: {', '.join(DB + '.' + c for c in d['colls']) or 'none (code unit: reads the collections migrated in waves 0-2, writes only your declared parity_<batch> scratch collection)'}.")
        lines.append(f"  Fixture rows (synthetic, demo scale): {d['rows']}.")
        lines.append(f"  Scope: {d['code']}.")
        lines.append("")
    lines.append(f"Fixture: {FIXTURE} (same-engine synthetic Oracle Free, seeded NS=demo; no production data exists). Load fixture first; there is no live run in this engagement (source_access=ddl_only): state 'live recon: not possible (offline)' in the PR.")
    lines.append(f"Recon: `env -u MONGODB_ATLAS_URI ~/.venvs/recon/bin/recon run --family oracle --mapping .migration/03_mapping_spec.json --tolerances .migration/02_tolerances.json --mode fixture --target-class local --collections {','.join(c for u in units for c in UNITS[u]['colls']) or '<none: code unit, run the procs/harness parity transcripts instead>'}` (see the mongo-recon-harness skill for exact flags).")
    lines.append("Done when: loader + code slice implemented, fixture recon PASS (or a documented FAIL with cause), quarantine counts reported, one PR opened against the run branch (unmerged), PR body states target_class=local and 'not merge evidence'.")
    lines.append("")
    lines.append(RULES)
    return "\n".join(lines)


def main():
    for w, plan in WAVES.items():
        batches = []
        for i, units in enumerate(plan["batches"], 1):
            bid = f"w{w}-b{i:02d}"
            targets = [f"{DB}.{c}" for u in units for c in UNITS[u]["colls"]]
            if not targets:  # code-only units: one declared scratch collection for parity transcripts
                targets = [f"{DB}.parity_{bid.replace('-', '_')}"]
            batches.append({"id": bid, "units": units, "write_targets": targets, "fixture_manifest": FIXTURE,
                            "xl_units": [u for u in units if UNITS[u]["xl"]], "brief": brief(w, bid, units)})
        manifest = {
            "wave": w, "repo": REPO, "branch": BRANCH,
            "child_macro": "!mongo_unit_migration", "verify_macro": "!mongo_reconciliation",
            "width": WIDTH, "breaker_threshold": 3,
            "auto_merge": False,
            "auto_merge_reason": "offline engagement: source_access=ddl_only, target_access=local; local evidence never merges (AGENTS.md rule 11; intake). Overrides the soft stop_mode default.",
            "source_access": "ddl_only", "target_access": "local",
            "child_minutes": 60,
            "execution_path": plan["path"], "expected_cost": plan["cost"],
            "batches": batches,
        }
        (HERE / f"wave-{w}.json").write_text(json.dumps(manifest, indent=1) + "\n")
        print(f"wave-{w}.json: {len(batches)} batches, targets={sum(len(b['write_targets']) for b in batches)}")


if __name__ == "__main__":
    main()
