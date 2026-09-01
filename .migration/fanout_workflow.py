import asyncio
import json

REPO = "Cognition-Partner-Workshops/otterworks"
RUN_BRANCH = "tp-run/mongodb-20260901T032752Z"
TARGET_DB = "ow_tp_mongodb_032752"
QUAR_DB = "ow_tp_mongodb_032752_quarantine"
NS = "mongo_032752"

COMMON = f"""
You are one child of the [MONGO v1] MongoDB migration fan-out for the OtterWorks Oracle
billing estate (schema OW_BILLING). Repo: {REPO}. Check out branch `{RUN_BRANCH}` and work
from it. ALL contracts are durable files on that branch — read them before any work:
- .migration/03_mapping_spec.md + .migration/03_mapping_spec.json (mapping contract v1.0, APPROVED)
- .migration/02_tolerances.md + .migration/02_tolerances.json (tolerances v1.0, APPROVED)
- .migration/recon_canonicalization.json (canonicalization v1.0)
- .migration/census/coverage.md (object coverage, access-pattern citations)
- .migration/01_conventions.md, 00_context.md, 04_progress.md, 05_decisions.md
- .migration/census/raw/* (census evidence incl. plsql_source.txt, access_patterns.txt)

Hard rules (violations halt the engagement):
- NEVER modify the legacy Oracle source, its schema, or its data; all Oracle access is read-only.
- Write ONLY to MongoDB databases `{TARGET_DB}` and `{QUAR_DB}` on the Atlas cluster
  (secret MONGODB_ATLAS_URI — reference secrets by NAME only, never store values anywhere).
- Every migrated document carries the namespace field `ns: "{NS}"`.
- Write only to the collections your unit owns per .migration/04_progress.md; a write-target
  collision with another unit = STOP and report, never proceed.
- The mongo-recon-harness verdict (result.json) is the only merge authority; no other tool
  self-certifies. Never hand-edit verdicts. An UNGRADED embed cannot ship as PASS.
- On recon FAIL: fix MIGRATED code/load only; never source, never tolerances. Re-run cap:
  3 full end-to-end pipeline re-runs; after the third red, stop and report with evidence.
- Never merge anything into `tech-partnerships` or `main`; never target them with a PR.
- Never consult the `tech-partnerships-solutions` branch — it is not a correctness reference.
- PR privacy: never identify the requesting user (no names/emails) in PR titles/bodies/comments.

Oracle source access: provision your OWN local deterministic fixture per the repo runbook
(docker compose service for oracle-billing; seed namespace NS=demo — deterministic seeded
RNG, so your fixture is byte-equivalent to the canonical one). Connect as ow_billing to
service FREEPDB1. Treat it read-only after seeding. Recon runs you perform are
run_mode=fixture (self-check); the parent runs the live gate independently — your fixture
recon must still be green before you open a PR.

Recon harness: `cd harness && pip install -e .` (if the blueprint venv
/home/ubuntu/.venvs/recon is absent on your VM, build a local venv and use it), then per unit:
recon run --unit <unit_id> --mapping .migration/03_mapping_spec.json \
  --tolerances .migration/02_tolerances.json \
  --canonicalization .migration/recon_canonicalization.json \
  --mode live --source-dsn-secret <your fixture DSN secret/env name> \
  --target-uri-secret MONGODB_ATLAS_URI --out .migration/recon/<unit_id>/

Deliverable: ONE pull request into `{RUN_BRANCH}` (never a stack; ordered semantic commits:
contract, code, load, recon evidence, fix rounds). PR body capped ~2000 chars, three parts
in order Decisions -> Code -> Evidence, with "Unverified paths / declared-unexercised" as
the TOP block; harness recon.summary.md rendered in Evidence, raw JSON linked not pasted;
tolerance version (1.0) cited; PROFILE FEEDBACK section (possibly empty); idempotency
proof (loads drop+recreate your unit's collections at start of every run). `make tp-smoke`
must pass locally before opening the PR. Update your unit's row in
.migration/04_progress.md (RECON_GREEN only after the gate passes) in the PR.
Do NOT merge the PR — the wave gate merges on independent evidence.
"""

UNIT_SCHEMA = {
    "type": "object",
    "properties": {
        "unit": {"type": "string"},
        "verdict": {"type": "string", "description": "GREEN | RED | ESCALATE"},
        "pr_url": {"type": "string"},
        "branch": {"type": "string"},
        "failure_class": {"type": "string", "description": "empty if GREEN; else one of types|null_missing|timezone|embed_cardinality|proc_semantics|load|env|other"},
        "escalation": {"type": "string", "description": "what needs a human decision, with evidence paths; empty if none"},
        "profile_feedback": {"type": "string"},
        "cost_notes": {"type": "string"},
    },
    "required": ["unit", "verdict", "pr_url", "branch", "failure_class", "escalation"],
}

WAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "wave": {"type": "string"},
        "wave_verdict": {"type": "string", "description": "PASS | FAIL | DRIFT-EXPLAINED"},
        "unit_verdicts": {"type": "string", "description": "JSON object unit->verdict"},
        "report_path": {"type": "string"},
        "findings": {"type": "string"},
    },
    "required": ["wave", "wave_verdict", "unit_verdicts", "report_path"],
}

MERGE_SCHEMA = {
    "type": "object",
    "properties": {
        "merged": {"type": "string", "description": "JSON list of PR URLs merged into the run branch"},
        "status": {"type": "string", "description": "OK | BLOCKED"},
        "detail": {"type": "string"},
    },
    "required": ["merged", "status"],
}

UNITS = {
    "U0": {
        "title": "U0 shared-reference: codes, tenants, plans, fixture_meta",
        "spec": """Unit U0 (wave 0, shared/reference — serial). Migrate Oracle tables CODES, TENANTS,
PLANS, FIXTURE_META to collections codes, tenants, plans, fixture_meta per the mapping
spec. codes uses loader-composed _id `<code_type>#<code_val>`; recon for codes runs once
per code_type value (the 10 types listed in .migration/census/coverage.md) via the
`${code_type}` root_where parameter. Create the unit's indexes from the spec's index plan
(unique _id on codes). No app-code rewrite in this unit. These are the reference
collections every later unit reads — correctness here is load-bearing.

AMENDMENTS (approved 2026-09-01, recorded in .migration/05_decisions.md — they supersede
the paragraph above where they conflict): (a) the codes gate is a SINGLE whole-table recon
keyed on the composed source expression CODE_TYPE || '#' || CODE_VAL vs _id — no
${code_type} parameterization; code_val is now an explicit mapped field (reload codes,
your loads are drop+recreate idempotent). (b) fixture_meta is graded count-only with
INITIALIZED_AT declared-unexercised. Pull the latest run branch — the mapping spec JSON
already carries both amendments. A previous session partially worked this unit: its data
may exist in the target (your drop+recreate handles it) and a branch/PR for U0 may already
exist — reuse or reset that branch rather than duplicating PRs.""",
    },
    "U1": {
        "title": "U1 customers (XL, wide-embed): CUSTOMER_MASTER + EAV + history",
        "spec": """Unit U1 (wave 1, XL, wide-embed calibration). Migrate CUSTOMER_MASTER (155 cols,
25,000 rows) -> customers with ENTITY_ATTR_VALUE embedded as attributes[] (child_where
ENTITY_TYPE='CUSTOMER', parent_key ENTITY_ID, element key eav_id; 8,333 rows, 0 orphans),
and CUSTOMER_MASTER_HIST -> customer_master_hist (append-only; source currently 0 rows —
recon must still grade the empty collection). Replace trigger TRG_CUSTOMER_MASTER_HIST and
the customer-related sequences per coverage.md (migrated rows keep source numeric keys;
new writes app-generated). Rewrite the BALANCES_SQL aggregation path in
services/legacy-billing/app/reports.py against MongoDB (aggregation pipeline over
customers). String-date VARCHAR2 columns migrate VERBATIM as strings (STOP B decision).
XL protocol: your FIRST commit is the ~100-line decision-first contract excerpt (mapping
rows, key strategy, index plan for this unit, copied from the approved spec) under
.migration/contracts/U1.md — the contract content was already human-approved at STOP B, so
proceed to implementation in the same PR without waiting.

AMENDMENT v1.1 (approved 2026-09-01, recorded in .migration/05_decisions.md): your earlier
Tier-2 FAIL (36 aggregate findings on 19 NULL-bearing numeric CUSTOMER_MASTER columns) is
resolved by mapping spec v1.1 + canonicalization v1.1 already on the run branch — pull the
latest run branch and re-run the gate with them (this consumes re-run 1 of 3). The 19
fields now carry null_missing_equiv (defers their native aggregates to the Tier-3 keyed
diff) and the 17 all-NULL fields have a blank bson_type (skips the SUM check). This is a
RECON-GRADING change only: the loader still writes source NULL as explicit BSON null, and
NULL != missing stays in force everywhere. A previous session already worked this unit:
branch tp-run/mongodb-20260901T032752Z--u1 exists with your loader + evidence — resume it
(rebase onto the latest run branch), reload if needed (drop+recreate idempotent), re-gate,
then open the PR.""",
    },
    "U2": {
        "title": "U2 invoice-feed (bulk): INVOICE_HEADER + INVOICE_LINE + orphan quarantine",
        "spec": """Unit U2 (wave 1, bulk-load calibration). Migrate INVOICE_HEADER (18,750) ->
invoice_feed with INVOICE_LINE embedded as lines[] (149,963 lines; element key line_id).
The 37 orphan INVOICE_LINE rows (no matching header) go to
{quar}.invoice_feed_orphan_lines — quarantined, never silently dropped; recon must show
embedded-line count + quarantine count == 150,000 source rows. Rewrite the STATUS_SQL and
LINE_SQL report paths in services/legacy-billing/app/reports.py against MongoDB (LINE_SQL's
inner join semantics == embedded lines by construction). Indexes per spec (batch_no,
cust_id). Loads are bulk and idempotent.""".replace("{quar}", QUAR_DB),
    },
    "U3": {
        "title": "U3 subscriptions: SUBSCRIPTIONS + history + PKG_PLANS",
        "spec": """Unit U3 (wave 2, proc-heavy calibration). Migrate SUBSCRIPTIONS -> subscriptions and
SUBSCRIPTIONS_HIST -> subscriptions_hist (append-only; replace TRG_SUBSCRIPTIONS_HIST with
app-side history writes). Convert PKG_PLANS (fn_list_plans, entitlement checks, plan
change logic — see .migration/census/raw/plsql_source.txt and access_patterns.txt) to
driver-idiomatic app-side logic; latest-covering-row lookup backed by the
(tenant_id, starts_on) index. Sequence replacement per coverage.md.

AMENDMENT v1.2 (approved 2026-09-01, recorded in .migration/05_decisions.md): your Tier-2
FAIL on subscriptions.ends_on/suspended_on (all-NULL DATE aggregate_distinct_count) is
resolved by mapping spec v1.2 + canonicalization v1.2 already on the run branch — pull the
latest run branch and re-run the gate (consumes re-run 2 of 3). Both fields now carry
null_missing_equiv (Tier-2 aggregate deferral only; bson_type stays date). Grading-only
change: the loader still writes source NULL as explicit BSON null. Your prior work is on
branch tp-run/mongodb-20260901T032752Z--u3 — resume it (rebase onto the latest run
branch), re-gate, then open the PR.""",
    },
    "U4": {
        "title": "U4 rating: USAGE_EVENTS + RATING_PERIODS + RATING_RESULTS + PKG_RATING",
        "spec": """Unit U4 (wave 2, proc-heavy). Migrate USAGE_EVENTS (814) -> usage_events,
RATING_PERIODS (3) -> rating_periods, RATING_RESULTS -> rating_results. Convert PKG_RATING
(usage aggregation per tenant+window, sp_finalize_rating upsert, rollover read joining
results<->periods) to aggregation pipelines / app-side logic. Indexes per spec
((tenant_id, occurred_at, kind_cd); period_id on rating_results). Replace the usage
trigger per coverage.md.""",
    },
    "U7": {
        "title": "U7 audit-util: BILLING_AUDIT_LOG + PKG_OW_UTIL + TTL purge",
        "spec": """Unit U7 (wave 2, utility). Migrate BILLING_AUDIT_LOG -> billing_audit_log (0 rows —
grade the empty collection). Convert PKG_OW_UTIL: f_code_desc -> codes lookup, MD5 helper,
date formatting, and log_msg's AUTONOMOUS TRANSACTION semantics -> unconditional
independent audit write (its own write concern, never inside a caller's transaction).
Replace scheduler job JOB_PURGE_AUDIT_LOG (disabled) with a TTL index on logged_at (90d)
per the spec.""",
    },
    "U5": {
        "title": "U5 invoicing (XL): INVOICES + INVOICE_LINES + CREDIT_NOTES + PKG_INVOICING",
        "spec": """Unit U5 (wave 3, XL, proc-heavy). DEPENDS on merged U3/U4 code on the run branch (pull
latest before starting). Migrate INVOICES (3) -> invoices with INVOICE_LINES (2) embedded
as lines[] (element key line_no), and CREDIT_NOTES -> credit_notes. Convert PKG_INVOICING
(compute_preview, sp_issue_invoice's delete+rebuild of all lines per invoice — that whole
rebuild is ONE transaction boundary, which the single-document embed preserves as
single-doc atomicity; credit-note application decrements) to app-side logic per the
mapping spec. Do NOT create the dunning_attempts[] array content (U6 owns it) but keep the
document model compatible with it. XL protocol: first commit is the decision-first
contract excerpt under .migration/contracts/U5.md (content pre-approved at STOP B);
proceed to implementation in the same PR.""",
    },
    "U6": {
        "title": "U6 dunning: DUNNING_ATTEMPTS embed + NOTIFICATIONS + PKG_DUNNING",
        "spec": """Unit U6 (wave 3, proc-heavy). DEPENDS on merged U5 (pull latest run branch; ow.invoices
exists and you extend its documents). Embed DUNNING_ATTEMPTS into invoices.dunning_attempts[]
(element key attempt_no; unique (invoice_id, attempt_no) preserved by element key — update
the invoices docs you do NOT otherwise own only by adding this array, coordinatedly:
register the embed write in 04_progress.md; the collision is pre-authorized by the wave
plan). Migrate NOTIFICATIONS -> notifications with unique index
(tenant_id, kind_cd, sent_at) preserving the dedup contract. Convert PKG_DUNNING (overdue
scan, attempt scheduling, sp_suspend_overdue conditional notification insert, suspension)
to app-side logic. Replace the disabled nightly dunning scheduler job with a documented
runnable job entrypoint (no schedule activation).""",
    },
}

WAVE_RECON_COMMON = f"""
You are the INDEPENDENT wave reconciliation session ([MONGO v1] Reconciliation & Parallel
Run, Part 1) for the OtterWorks Oracle->MongoDB migration. You converted nothing in this
wave; independence is the point — do not read the children's diagnoses before re-running.
You run ON THE PARENT MACHINE: the canonical Oracle fixture container
(otterworks-oracle-billing-oracle-billing-1, host DSN localhost:52521/FREEPDB1, user
ow_billing) may already be running — check and reuse it; if it is down, start it per the
repo runbook (docker compose) but NEVER reseed or modify its data. Leave it running when
you finish. Do not switch this machine's git branches destructively, restart its shells,
or delete files outside your scope; work in a separate clone dir under ~/wave_recon/ if
you need a different checkout.

Repo {REPO}, run branch {RUN_BRANCH}. Contracts: .migration/03_mapping_spec.json v1.0,
tolerances v1.0, canonicalization v1.0. Target db {TARGET_DB} (quarantine {QUAR_DB}),
Atlas secret MONGODB_ATLAS_URI (names only, never values). Source-load cap is 1: you are
the single live window — run gates serially, never concurrently.

For each unit in the wave: (1) re-run its recon gate VERBATIM from the spec (LIVE mode
against the canonical fixture — this is the authoritative live proof; on mismatch, triage
drift-vs-defect by re-running the source side twice); (2) probe adversarially beyond the
gate: null/missing distributions per field, duplicate keys, min/max boundary docs,
empty-collection behavior, embed-array length distribution vs source child-row
distribution, spot doc-level checks on aggregate-only fields; (3) cross-unit consistency
across the wave's shared references (tenants/plans/codes joins). (4) Replay the wave's
representative app-level queries against both stacks and verify result parity yourself.
Write the wave report AND a one-page wave-close brief to
.migration/recon/wave_reports/<wave>.md on a branch pushed to origin (report the branch),
including per-unit verdict PASS/FAIL/DRIFT-EXPLAINED, probe results, findings, and a
per-unit cost line. Never fix migrated code, never touch legacy, never adjust tolerances.
FAIL routes back to the orchestrator.
"""

MERGE_PROMPT = f"""
You are the merge/ledger agent for the OtterWorks MongoDB migration, running ON THE PARENT
MACHINE (do not disturb its running state; use a separate clone under ~/merge_work/ if
needed). Repo {REPO}. Merge ONLY the PRs listed below into `{RUN_BRANCH}` (never into
tech-partnerships or main), in the given order, using plain git (fetch PR head branches,
merge into {RUN_BRANCH}, push) or the PR merge API if available. Then update
.migration/04_progress.md on {RUN_BRANCH}: set each merged unit's row Status=MERGED,
Parity=GREEN (per the wave report), fill the PR column, and append the wave-report branch
reference; also append a wave-close line to .migration/05_decisions.md
(| <date from the wave report> | Wave <w> closed: <units> merged on independent recon PASS | orchestrator | RECORDED |).
Commit with message 'mongo 032752: wave <w> close — merge + ledger' and push. If any merge
conflicts or a PR is missing/closed, STOP (status BLOCKED) and report; never force-push,
never resolve substantive conflicts yourself.

IDEMPOTENCY (merge-protocol r3): the orchestrator may already have merged some or all of
this wave (e.g. after resolving a conflict or vetting post-gate commits itself). For each
PR, if its head commit is already reachable from {RUN_BRANCH}, treat it as merged and skip
it — if the PR is still marked open on GitHub despite its head being reachable, close/mark
it merged if the API allows, otherwise just report it. Likewise skip ledger/decision/journal lines
that are already present — never duplicate them. If everything is already merged and
ledgered, verify and return status OK with the merged PR list.
"""


async def run_unit(uid):
    u = UNITS[uid]
    return await agent(
        COMMON + "\n## Your batch spec\n" + u["spec"] +
        f"\n\nBranch naming: create your PR branch as `{RUN_BRANCH}--{uid.lower()}`. "
        "Report verdict GREEN only with green fixture recon output on disk; RED if the "
        "re-run cap was hit; ESCALATE if a human decision is needed (tolerance ambiguity, "
        "collision, blocked on an unlanded sibling — STOP rather than inventing a "
        "bootstrap substitute).",
        phase=f"convert-{uid}",
        schema=UNIT_SCHEMA,
        label=u["title"],
        repos=[REPO],
    )


async def wave_recon(wave_name, unit_results):
    prs = json.dumps(
        {r["unit"]: {"pr": r["pr_url"], "branch": r["branch"]} for r in unit_results},
        sort_keys=True,
    )
    return await agent(
        WAVE_RECON_COMMON + f"\n## Wave under review: {wave_name}\nUnit PRs/branches:\n{prs}\n"
        "Fetch each PR branch and run the gates against ITS code+load state.",
        phase=f"recon-{wave_name}",
        schema=WAVE_SCHEMA,
        label=f"independent recon {wave_name}",
        vm_mode="shared",
    )


async def merge_wave(wave_name, unit_results, recon):
    order = json.dumps([r["pr_url"] for r in unit_results], sort_keys=False)
    return await agent(
        MERGE_PROMPT + f"\nWave: {wave_name}\nPRs in merge order: {order}\n"
        f"Wave report branch/path: {recon['report_path']}\n"
        f"Unit verdicts: {recon['unit_verdicts']}",
        phase=f"merge-{wave_name}",
        schema=MERGE_SCHEMA,
        label=f"merge {wave_name}",
        vm_mode="shared",
    )


FAILURE_COUNTS = {}


def check_halt(results):
    for r in results:
        if r["verdict"] != "GREEN":
            raise RuntimeError(f"HALT: unit {r['unit']} verdict={r['verdict']} escalation={r['escalation']}")
        fc = r.get("failure_class") or ""
        if fc:
            FAILURE_COUNTS[fc] = FAILURE_COUNTS.get(fc, 0) + 1
            if FAILURE_COUNTS[fc] >= 3:
                raise RuntimeError(f"HALT: circuit breaker — 3 same-class failures ({fc})")


async def run_wave(wave_name, unit_ids):
    log(f"{wave_name}: launching units {unit_ids}")
    results = await asyncio.gather(*[run_unit(u) for u in unit_ids])
    check_halt(list(results))
    log(f"{wave_name}: all units GREEN (fixture) — starting independent recon")
    recon = await wave_recon(wave_name, list(results))
    if recon["wave_verdict"] == "FAIL":
        raise RuntimeError(f"HALT: {wave_name} independent recon FAIL: {recon['findings']}")
    log(f"{wave_name}: recon {recon['wave_verdict']} — merging")
    merged = await merge_wave(wave_name, list(results), recon)
    if merged["status"] != "OK":
        raise RuntimeError(f"HALT: {wave_name} merge blocked: {merged.get('detail','')}")
    log(f"{wave_name}: CLOSED — merged {merged['merged']}")
    return recon


async def main():
    await register_workflow({
        "name": "mongo-032752-fanout",
        "description": "OtterWorks OW_BILLING Oracle -> MongoDB Atlas migration fan-out: "
                       "waves 0-3, recon-gated, one PR per unit into the run branch.",
        "product": "OtterWorks billing estate (Cognition-Partner-Workshops/otterworks)",
        "phases": (
            [{"title": f"convert-{u}", "detail": UNITS[u]["title"], "count": 1, "labels": [UNITS[u]["title"]]} for u in ["U0", "U1", "U2", "U3", "U4", "U7", "U5", "U6"]]
            + [{"title": f"recon-{w}", "detail": f"independent wave recon {w}", "count": 1} for w in ["wave0", "wave1", "wave2", "wave3a", "wave3b"]]
            + [{"title": f"merge-{w}", "detail": f"merge + ledger {w}", "count": 1} for w in ["wave0", "wave1", "wave2", "wave3a", "wave3b"]]
        ),
    })
    await run_wave("wave0", ["U0"])
    await run_wave("wave1", ["U1", "U2"])
    await run_wave("wave2", ["U3", "U4", "U7"])
    await run_wave("wave3a", ["U5"])
    await run_wave("wave3b", ["U6"])
    log("All waves closed — engagement ready for phase 4 (cutover preparation).")

asyncio.run(main())
