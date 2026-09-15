#!/usr/bin/env python3
"""Generate .migration/waves/wave-<N>.json for pipeline 1.

The manifests are what `run_workflow` (migration-fanout) reads. Everything a child needs is
in its batch brief: the workflow passes the brief verbatim and a child that has to guess
reports BLOCKED instead. Regenerate with:

    python3 databricks/migration/tools/gen_wave_manifests.py

Capability contract is copied from .migration/09_capabilities.json (never hand-edited);
cost_estimate is summed from .migration/units/<unit>/cost_estimate.json, which
gen_recon_estimates.py writes from `dbx-recon estimate`.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WAVES = ROOT / ".migration/waves"
UNITS = ROOT / ".migration/units"
CAPS_FILE = ROOT / ".migration/09_capabilities.json"
ALLOWED_FILE = ROOT / ".migration/allowed_targets.json"
PARENT_BRANCH = "mig-p1-w0"

REPO = "github.com/Cognition-Partner-Workshops/otterworks"
BASE_BRANCH = "tp-run/databricks-20260915T045714Z"
CHILD_MACRO = "!dbx_unit_migration"
VERIFY_MACRO = "!dbx_data_reconciliation"
SOURCE = {"family": "databricks", "secret": "OW_BILLING_RO_DSN",
          "params": {"source_schema": "OW_BILLING"}}
CANON = "databricks/migration/recon/canonicalization.oracle.json"
# Concurrent live reads the Oracle source may see across a whole wave. Every batch takes one
# at its gate, so the fan-out width IS that concurrency: width can never exceed the cap.
SOURCE_QUERY_CAP = 4
TOL = ".migration/03_recon_tolerances.json"

# unit -> (title, track, depth, targets, source objects)
# track: "lakebase" (operational) | "delta" (analytical)
UNIT = {
    "p1-pkg-ow-util":        ("U-20 pkg_ow_util (shared) + wave-0 scaffolding", "lakebase", "full"),
    "p1-cdc-transport":      ("U-27 CDC transport (Debezium -> Kinesis -> Lakeflow AUTO CDC)", "delta", "threshold"),
    "p1-tenants":            ("U-01 TENANTS", "lakebase", "full"),
    "p1-plans":              ("U-02 PLANS", "lakebase", "full"),
    "p1-codes":              ("U-11 CODES", "lakebase", "full"),
    "p1-usage-events":       ("U-18 USAGE_EVENTS", "delta", "full"),
    "p1-usage-events-oltp":  ("U-28 USAGE_EVENTS (operational copy)", "lakebase", "full"),
    "p1-invoice-header":     ("U-16 INVOICE_HEADER (legacy)", "delta", "full"),
    "p1-invoice-line":       ("U-17 INVOICE_LINE (legacy)", "delta", "full"),
    "p1-subscriptions":      ("U-03 SUBSCRIPTIONS", "lakebase", "full"),
    "p1-pkg-plans":          ("U-21 pkg_plans", "lakebase", "full"),
    "p1-customer-master":    ("U-12 CUSTOMER_MASTER (155 cols)", "lakebase", "full"),
    "p1-entity-attr-value":  ("U-13 ENTITY_ATTR_VALUE (EAV)", "lakebase", "full"),
    "p1-customer-master-hist": ("U-14 CUSTOMER_MASTER_HIST (empty)", "delta", "full"),
    "p1-subscriptions-hist": ("U-15 SUBSCRIPTIONS_HIST (empty)", "delta", "full"),
    "p1-billing-audit-log":  ("U-19 BILLING_AUDIT_LOG (empty)", "delta", "full"),
    "p1-job-purge-audit-log": ("U-26 JOB_PURGE_AUDIT_LOG", "delta", "sampled"),
    "p1-rating-periods":     ("U-04 RATING_PERIODS", "lakebase", "full"),
    "p1-rating-results":     ("U-05 RATING_RESULTS", "lakebase", "full"),
    "p1-pkg-rating":         ("U-22 pkg_rating", "lakebase", "full"),
    "p1-credit-notes":       ("U-08 CREDIT_NOTES", "lakebase", "full"),
    "p1-invoices":           ("U-06 INVOICES (modern)", "lakebase", "full"),
    "p1-invoice-lines":      ("U-07 INVOICE_LINES (modern)", "lakebase", "full"),
    "p1-pkg-invoicing":      ("U-23 pkg_invoicing", "lakebase", "full"),
    "p1-dunning-attempts":   ("U-09 DUNNING_ATTEMPTS", "lakebase", "full"),
    "p1-notifications":      ("U-10 NOTIFICATIONS", "lakebase", "full"),
    "p1-pkg-dunning":        ("U-24 pkg_dunning", "lakebase", "full"),
    "p1-job-nightly-dunning": ("U-25 JOB_NIGHTLY_DUNNING (created PAUSED)", "lakebase", "sampled"),
}

COMMON = f"""
REPO AND BRANCH
  Repo {REPO}; base branch for your PR: {BASE_BRANCH}.
  Never target `main` or `tech-partnerships`. One PR per unit, child branch
  `migrate/p1/<wave>-<unit>`. Run `mise trust` after cloning.
  Pre-PR: the repo's `tp-pre-pr-self-check` skill and `make tp-smoke`.

READ FIRST (committed on the base branch, parent-owned, do not edit)
  .migration/00_context.md, 01_conventions.md, 03_recon_tolerances.{{md,json}},
  04_dependency_register.md, 06_decisions.md, allowed_targets.json
  docs/migration/Pipeline1_invoicing_analysis.md  (the approved analysis: your unit's row)
  docs/migration/Pipeline1_invoicing_plan.md      (this plan: dictionary, gate, decisions)
  docs/migration/OtterWorks_target_state.md       (target layout and conventions)

SOURCE (read-only, no exceptions)
  Oracle AI DB 26ai Free 23.26.3.0.0, 52.201.36.9:1521/FREEPDB1, schema OW_BILLING.
  Secret name only: ow-tp/oracle/ow_billing_ro (AWS Secrets Manager us-east-1; JSON keys
  user/password/host/port/service - `user`, not `username`). Never print a value.
  No DDL, no DML, no CDC enablement on Oracle. Develop against the fixture
  (`make oracle-billing-up`, repo skill `oracle-billing-estate`); take exactly ONE live read
  per unit inside the source query cap (4 concurrent source queries for the whole wave).

TARGETS (the only writable places)
  Unity Catalog `ow_tp` (bronze/silver/gold), volume /Volumes/ow_tp/bronze/landing,
  jobs and pipelines named ow_tp_*, secret scope `ow_tp`.
  Lakebase project ow-tp-billing, database ow_tp, schema billing, on YOUR wave branch
  (below). Never the `production` branch, never project loan-servicing-migration.
  Warehouse 565cd2fd713738c4. Never create a cluster.
  The guard (hooks/dbx_guard.py) blocks anything outside .migration/allowed_targets.json.
  A block is a finding: report status=BLOCKED, never route around it.

CONVERSION RULES THAT ARE NOT NEGOTIABLE (from the approved analysis)
  - Money is numeric(p,s)/DECIMAL(p,s), never float. Status codes stay magic numbers.
  - The 37 `DD-MON-YY` string-date columns are migrated RAW (varchar/STRING, byte-exact)
    plus a parsed date column for consumers. `f_str2dt` returns NULL on a bad date; that
    NULL is the legacy behaviour and belongs in the declared anomaly set, not a fix.
  - Oracle DATE keeps its time part (timestamp(0)/TIMESTAMP). Source has no zone; UTC is
    assumed and declared (plan decision P1-D3) - if parity breaks, report it, do not retune.
  - CHAR(1) Y/N stays char(1). Comma-separated id lists stay verbatim text.
  - Orphan rows and malformed strings are reproduced, not cleaned (D8-01).
  - Swallowed exceptions (`WHEN OTHERS THEN NULL`) are reproduced as observable behaviour
    (plan decision P1-D2). Do not "fix" them.
  - Package-global state becomes an explicit parameter or state row, never an implicit
    session global (plan decision P1-D4).
  - Every mapping names which invoice generation it covers (D9-01): modern
    INVOICES/INVOICE_LINES (Lakebase) are NOT legacy INVOICE_HEADER/INVOICE_LINE (Delta).
  - Every schedule you create lands PAUSED.

RECON GATE (the only merge authority, and it is DEGRADED on this run)
  D10-01 was DENIED: the security group stays shut, so there is no Lakehouse Federation and
  no `--family databricks` read of Oracle. The owner directed the JDBC route instead
  (plan decision P1-D10). `dbx-recon run --family oracle` still refuses at the CLI - do not
  try to make it accept - so the gate runs the harness ENGINE with a repo-local Oracle
  source adapter: databricks/migration/recon/run_degraded_recon.py. Every tier, tolerance
  and canonicalization rule is the harness's own; only the source connector is outside the
  tested matrix.
  Consequence, and you must carry it verbatim: every pipeline-1 verdict is graded DEGRADED
  with official_verdict=false and reason=d10_01_denied. Never call it an official harness
  verdict - not in summary.md, not in result.json, not in your PR body, not in your report.
  Everything else is computed in full: money exact, row counts exact, 1e-9 relative on other
  floats, ISO-canonicalised dates, declared anomaly sets compared as sets, idempotency proven
  by rerun, unverified paths listed explicitly. Recompute from the target platform - never
  from CDC output this unit produced.
  Source-side op SQL is ORACLE dialect (it runs on Oracle, not Databricks) and its result
  columns carry quoted lowercase aliases so they match the target side by name.
  Fixture first (mode=fixture, never merge evidence), then exactly one merge-evidence run.
  Cap: 3 full recon runs; on the third failure stop and report status=FAIL with a short
  failure_class. Evidence goes to .migration/recon/<unit_id>/ (summary.md + result.json,
  plus DEGRADED.md) and into the PR body. The exact command for each unit is below.
  Never invent a hand-written comparison and never call a fixture PASS a merge verdict.
""".rstrip()


def gate_cmd(unit: str) -> str:
    track = UNIT[unit][1]
    depth = UNIT[unit][2]
    if track == "lakebase":
        mode, kind, secret, schema = "transactional", "lakebase", "OW_TP_LAKEBASE_DSN", "billing"
    else:
        # Delta units land curated tables in silver; the transport unit is the raw landing
        # itself, so its own recon reads ow_tp.bronze, where it writes.
        schema = "bronze" if unit == "p1-cdc-transport" else "silver"
        mode, kind, secret = "live", "databricks", "DATABRICKS_MIGRATION_SQL"
    # The Databricks target adapter wants a JSON credential in an env var. No stored secret
    # holds one and the guard blocks creating it, so the wrapper mints a short-lived token
    # from the migration service principal and hands it to the child process only.
    token = ("  python3 databricks/migration/recon/with_databricks_sql_token.py "
             f"{secret} -- \\\n" if kind == "databricks" else "")
    ops = (f"    --ops .migration/units/{unit}/ops.json \\\n"
           if (UNITS / unit / "ops.json").exists() else "")
    return (f"  python3 databricks/migration/recon/with_oracle_secret.py "
            f"OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \\\n"
            f"{token}"
            f"  python3 databricks/migration/recon/run_degraded_recon.py --unit {unit} \\\n"
            f"    --mapping .migration/units/{unit}/mapping_spec.json \\\n"
            f"{ops}"
            f"    --tolerances {TOL} \\\n"
            f"    --canonicalization {CANON} \\\n"
            f"    --mode {mode} --source-dsn-secret OW_TP_ORACLE_RO \\\n"
            f"    --target-kind {kind} --target-secret {secret} \\\n"
            f"    --target-catalog ow_tp --target-schema {schema} \\\n"
            f"    --allowed-targets-file .migration/allowed_targets.json \\\n"
            f"    --seed 0 --depth {depth} --out .migration/recon/{unit}/")


def brief(wave: int, batch_id: str, units: list[str], targets: list[str],
          runtime_writes: list[str], lakebase_branch: str | None, parent_branch: str | None,
          body: str) -> str:
    unit_lines = "\n".join(f"  - {u}: {UNIT[u][0]} (track {UNIT[u][1]}, depth {UNIT[u][2]})"
                           for u in units)
    gates = "\n".join(gate_cmd(u) for u in units)
    origin = (f"off `{parent_branch}` BEFORE this wave launched" if parent_branch else
              "before this wave launched and carried it over from the previous wave")
    lb = (f"  Lakebase: the orchestrator created branch `{lakebase_branch}` {origin},\n"
          f"  so it already carries every object earlier waves merged.\n"
          f"  Use it as it is: do NOT create, reset, re-branch or drop it - concurrent batches in\n"
          f"  this wave share it, and creating it again races them. If it is missing, report\n"
          f"  status=BLOCKED with `wave_branch_missing`; do not improvise one.\n"
          f"  Batches stay out of each other's way by write target, not by branch: write only the\n"
          f"  objects declared below.\n"
          f"  DSN at runtime: `databricks postgres generate-database-credential \\\n"
          f"    projects/ow-tp-billing/branches/{lakebase_branch}/endpoints/primary` -> export as\n"
          f"  OW_TP_LAKEBASE_DSN. 1-hour token, never stored, never printed.\n"
          if lakebase_branch else
          "  No Lakebase branch: this batch writes Delta only.\n")
    return (f"BATCH {batch_id} - wave {wave} of the OtterWorks pipeline-1 migration "
            f"(Oracle OW_BILLING -> Lakebase Postgres + Delta).\n\n"
            f"UNITS\n{unit_lines}\n\n"
            f"WHAT THIS BATCH IS\n{body.strip()}\n\n"
            f"ISOLATION\n{lb}"
            f"  Declared write targets (write nowhere else): {', '.join(targets)}\n"
            + (f"  Runtime writes into tables another unit owns the DDL for: "
               f"{', '.join(runtime_writes)}.\n"
               f"  Every one of those tables is merged by an EARLIER wave, so no batch running\n"
               f"  beside you writes them; you issue DML only, never DDL, and you declare it in\n"
               f"  your PR. If one is missing on the branch, report status=BLOCKED with\n"
               f"  `runtime_write_target_missing`.\n" if runtime_writes else "")
            + f"  Evidence you may write under .migration/: only .migration/recon/<your unit>/\n"
            f"{COMMON}\n\n"
            f"YOUR RECON GATE COMMANDS\n{gates}\n")


def check_estimates_fresh() -> None:
    """Refuse to build manifests from cost estimates that predate a unit's ops file.

    The estimate is generated from the mapping AND the ops file, so an ops file written
    afterwards leaves a committed estimate that silently understates every Tier-4 comparison
    and every wave total built from it. Regenerate with gen_recon_estimates.py."""
    stale = []
    for d in sorted(p for p in UNITS.iterdir() if p.is_dir()):
        est_file = d / "cost_estimate.json"
        if not est_file.exists():
            continue
        ops_file = d / "ops.json"
        ops = len(json.loads(ops_file.read_text())) if ops_file.exists() else 0
        if json.loads(est_file.read_text()).get("ops", 0) != ops:
            stale.append(d.name)
    if stale:
        raise SystemExit(
            f"cost estimates are stale for {', '.join(stale)}: the recorded op count does not "
            "match ops.json. Run databricks/migration/tools/gen_recon_estimates.py first.")


def cost(units: list[str]) -> dict:
    agg = {"source_statements": 0, "target_statements": 0,
           "source_rows_fetched": 0, "target_rows_fetched": 0}
    for u in units:
        f = UNITS / u / "cost_estimate.json"
        if not f.exists():
            continue
        est = json.loads(f.read_text())["estimate"]
        agg["source_statements"] += est["source_statements"]["total"]
        agg["target_statements"] += est["target_statements"]["total"]
        agg["source_rows_fetched"] += int(est.get("source_rows_fetched") or 0)
        agg["target_rows_fetched"] += int(est.get("target_rows_fetched") or 0)
    return agg


def wave_branches(waves: list[int]) -> dict[int, tuple[str, str | None]]:
    """wave -> (branch it converts on, branch that branch was cut from).

    One Lakebase branch per WAVE, not per batch: the orchestrator creates it once off the
    previous wave's branch before fan-out, so it carries every object earlier waves merged and
    concurrent batches in the wave cannot race each other creating it. Batches are isolated by
    disjoint write targets instead. Branch names must be in allowed_targets.json (the guard
    blocks anything else, and that file is parent-owned); a wave with no allowed branch of its
    own continues on the latest allowed one, which is safe because waves run in sequence."""
    allowed = set(json.loads(ALLOWED_FILE.read_text())["lakebase_branches"])
    out: dict[int, tuple[str, str | None]] = {}
    current = PARENT_BRANCH
    if current not in allowed:
        raise SystemExit(f"parent branch {PARENT_BRANCH} is not in allowed_targets.json")
    for wave in sorted(waves):
        wanted = f"mig-p1-w{wave}"
        if wanted in allowed and wanted != current:
            out[wave] = (wanted, current)
            current = wanted
        else:
            out[wave] = (current, None)
    return out


# Runtime writes are part of the isolation contract, not a footnote in a PR body: a batch that
# UPDATEs a table another unit owns still races anything writing it at the same time. Every
# runtime write below is therefore declared, and the checker requires the table's DDL owner to
# sit in a STRICTLY EARLIER wave so no concurrent batch can touch it. That is why credit notes
# moved out of wave 3 and into wave 2: invoicing burns them down while it runs.
PLAN = [
    # wave, width, [(batch_id, units, write_targets, runtime_writes, body)]
    (0, 1, [
        ("w0-a", ["p1-pkg-ow-util"],
         ["billing.f_md5_uuid", "billing.f_str2dt", "billing.f_code_desc", "billing.log_msg",
          "billing.rating_state", "billing.billing_audit_log", "billing.md5_parity_input",
          "ow_tp.silver.ow_util_fn"],
         [],
         """
Wave 0 is serial and everything else waits on it. Deliver, in this order:
 1. Shared scaffolding: Lakebase schema `billing` conventions on branch mig-p1-w0 (the
    parent branch already exists; do not recreate it), Unity Catalog bronze/silver/gold
    conventions and the /Volumes/ow_tp/bronze/landing path, secret-scope `ow_tp` references
    by name, the DAB skeleton for ow_tp_p1_* jobs and pipelines (no schedules enabled, no
    clusters), and the recon wiring: the pinned canonicalization profile at
    databricks/migration/recon/canonicalization.oracle.json is the one every unit passes.
 2. Apply the approved Lakebase grants from
    databricks/migration/governance/p1_grants_approved.sql (the commented Lakebase block).
    APPROVED rows only; never a PROPOSED or GAP row.
 3. Convert pkg_ow_util (services/legacy-billing/db/oracle/packages/01_pkg_util.sql) to
    PL/pgSQL in schema `billing` plus the Delta-side equivalents:
      - f_md5_uuid: deterministic MD5-derived id. THE PARITY PROOF IS THIS UNIT'S REASON TO
        EXIST (D2-01). Prove byte-for-byte equality on both targets over a fixed input
        vector that includes every call shape in the estate (rating period, rating result,
        invoice, invoice line, dunning) plus NULL, empty-string, and non-ASCII inputs.
        Record the vector and both outputs in .migration/recon/p1-pkg-ow-util/summary.md.
        If MD5 parity fails, STOP: every downstream primary key depends on it.
      - f_str2dt: returns NULL on any unparseable date, silently. Reproduce exactly.
      - f_code_desc: EXECUTE IMMEDIATE over a static lookup; convert to a plain query.
      - log_msg: PRAGMA AUTONOMOUS_TRANSACTION, commits even when the caller rolls back and
        swallows its own failures. Implement per plan decision P1-D1 (separate best-effort
        writer that cannot fail the caller and is not enrolled in the caller's transaction).
 4. Recon source wiring, NOT Federation: D10-01 was denied, so `ow_billing_fed` is never
    created and nothing may read Oracle from Databricks. Wire and smoke the JDBC route
    instead - databricks/migration/recon/{oracle_jdbc_adapter,run_degraded_recon,
    with_oracle_secret}.py - with one read-only Oracle query, and record in summary.md that
    every pipeline-1 verdict from here on is DEGRADED, official_verdict=false,
    reason=d10_01_denied. Do not ask for the security-group change.
 5. billing.rating_state: the explicit pkg_rating -> pkg_invoicing hand-off (plan decision
    P1-D4), keyed (tenant_id, period_id), holding the overage amount and the finalisation
    marker that Oracle kept in g_overage_amount. Pin the exact shape here, with a comment
    saying wave 3 codes against it: w3-a writes it and w3-b reads it, concurrently.
 6. billing.md5_parity_input(vector, input): the seed table the MD5 ops compare against.
    Seed it over the same read-only JDBC path, with the exact inputs Oracle used for the ids
    it already holds - `rating_result` = rating_results.period_id (pkg_rating:197), `invoice` =
    invoices.period_id || 'invoice' (pkg_invoicing:130-132), `invoice_line` =
    invoice_lines.invoice_id || line_no (pkg_invoicing:160). The ops then put Oracle's own
    ids next to billing.f_md5_uuid recomputed from the same inputs, which is the parity
    proof. Neither side calls an Oracle package: calling one would need an Oracle view over
    it, which is source DDL and forbidden.
 7. Data recon for this unit is the billing_audit_log schema-parity check only (the table is
    empty; the operational copy billing.billing_audit_log is this unit's, the silver copy is
    U-19's): record it as NOT DATA-PROVEN. The merge evidence is the three MD5 ops.
    f_code_desc is graded at the wave-1 CODES gate (it needs billing.codes) and f_str2dt at
    each string-date unit's `str_date_parse` op - do not invent an Oracle-side call here.
Do not convert any business table here. Do not enable any schedule.
"""),
        ("w0-b", ["p1-cdc-transport"],
         # The D-002 fallback lands one bronze table per captured source table through the
         # landing volume, so those tables are write targets of this batch exactly as the
         # stream's own table is. Declaring only the stream table would make the sanctioned
         # fallback an undeclared write and halt the wave.
         ["ow_tp.bronze.cdc_ow_billing", "ow_tp_p1_cdc_ingest",
          "ow_tp.bronze.customer_master", "ow_tp.bronze.invoice_header",
          "ow_tp.bronze.invoice_line", "ow_tp.bronze.codes",
          "/Volumes/ow_tp/bronze/landing"],
         [],
         """
The CDC transport, serial after w0-a: Debezium Server on the existing EKS cluster
otterworks-dev -> Kinesis on-demand -> a Lakeflow pipeline `ow_tp_p1_cdc_ingest` with AUTO
CDC into ow_tp.bronze. Capture user secret name: ow-tp/oracle/dbzuser. Supplemental logging
is already on the 19 business tables (D-001); do not touch Oracle again for any reason.
Debezium LogMiner against Oracle 26ai Free is outside the tested matrix and D10-03 (Kinesis
stream + Debezium deployment) is PENDING with the parent. If first boot fails or D10-03 is
not delivered: fall back to JDBC + watermark batch ingest for the correctness path (D-002),
say so plainly in your report, and keep the CDC leg as follow-up work. Do not let this unit
block the rest of the pipeline and do not fake a stream.
Recon: stream-vs-batch convergence - the CDC-applied bronze state must equal a JDBC snapshot
taken after the stream is caught up. On the fallback path, the convergence check is the
watermark batch vs the snapshot, recorded as DEGRADED CDC evidence.
"""),
    ]),
    (1, 3, [
        ("w1-a", ["p1-tenants", "p1-plans", "p1-codes"],
         ["billing.tenants", "billing.plans", "billing.codes"],
         [],
         """
Pilot batch: three tiny operational reference tables (69 / 3 / 32 rows) into Lakebase.
Small on purpose - this batch calibrates the dialect rules for the whole run, so write down
every rule you had to derive in skill_feedback.
 - TENANTS: status magic numbers 10/20 stay as smallint values.
 - PLANS: NUMBER(12,2) money -> numeric(12,2), exact-equality recon.
 - CODES: composite primary key (code_type, code_val); read by dynamic SQL in
   pkg_ow_util.f_code_desc, so the lookup shape must survive.
Each table's indexes and constraints are part of its unit; Lakebase gets the equivalents.
"""),
        ("w1-b", ["p1-usage-events"],
         ["ow_tp.silver.usage_events"],
         [],
         """
USAGE_EVENTS (814 rows) into Delta. Analytical track: this table is read by rating and later
by a build session, and the application does not write it transactionally.
TRG_USAGE_EVENTS_CHECK rejects non-positive usage and unknown usage kinds; convert it as a
Delta constraint/expectation with the same rule, and record where the enforcement now lives.
Recon: full diff, plus `units` summed per tenant/period so pkg_rating's cursor arithmetic has
a baseline before wave 3 converts it.
"""),
        ("w1-c", ["p1-invoice-header", "p1-invoice-line"],
         ["ow_tp.silver.invoice_header", "ow_tp.silver.invoice_line"],
         [],
         """
The legacy reporting pair into Delta: INVOICE_HEADER (18,750) and INVOICE_LINE (150,000).
THIS IS THE LEGACY GENERATION (D9-01). It is not modern INVOICES/INVOICE_LINES, which are
Lakebase units in wave 4. State the generation in both mapping specs and in your PR.
 - Denormalized, no foreign keys, string dates. Orphan INVOICE_LINE rows exist by design:
   reproducing them exactly is the pass condition, and they are compared as a set (D8-01).
 - 150,000 rows is the largest unit in the pipeline: use the backfill planner's chunking and
   expect the size-tiered recon path. Full row-level diff still applies (below 5,000,000).
"""),
    ]),
    # Width 4, not 5: this wave has five batches and every one of them takes a live Oracle
    # read at its gate, so a width of 5 can put five concurrent queries on a source whose cap
    # is four. The five batches still run; at most four are in flight. Recorded as a
    # deviation from "width 5 for waves 2-4" in the plan.
    (2, 4, [
        ("w2-a", ["p1-subscriptions", "p1-pkg-plans"],
         ["billing.subscriptions", "billing.fn_plan_entitlements", "billing.sp_assign_plan"],
         # sp_assign_plan logs through wave 0's log_msg, so it writes the audit table (D-009).
         ["billing.billing_audit_log"],
         """
SUBSCRIPTIONS (69 rows) plus pkg_plans, together because the package writes the table.
 - TRG_SUB_NO_UNCANCEL: a cancelled subscription can never be un-cancelled. The rule must
   survive as a Postgres trigger with the same observable error behaviour.
 - pkg_plans (packages/02_pkg_plans.sql): package-state entitlement cache that is never
   invalidated - make the state explicit (P1-D4), and keep the never-invalidated behaviour
   unless a recorded decision says otherwise. `(+)` outer joins become ANSI joins. Dynamic
   SQL wrapping a static INSERT becomes a plain INSERT. `SELECT ... FOR UPDATE` keeps its
   locking semantics in Postgres.
Behavioural recon for pkg_plans is the Tier-4 op diff over its entrypoints plus the rows it
writes into billing.subscriptions after a controlled fixture run.
"""),
        ("w2-b", ["p1-customer-master"],
         ["billing.customer_master"],
         [],
         """
CUSTOMER_MASTER: 25,000 rows x 155 columns, alone in its batch because it is the single most
likely unit to produce a wide diff and its child needs room to iterate.
 - 15 of the 37 `DD-MON-YY` string-date columns live here: keep the raw string byte-exact AND
   add the parsed date column. Recon compares the raw columns byte-exact and the canonicalized
   ones separately; they may disagree only on rows in the declared unparseable set.
 - 10 UDF money slots and repeating groups (ADDR1..ADDR5 style): no normalization in
   pipeline 1. Same shape, same names.
 - seq_customer_master + trg_customer_master_seq convert with this unit (the history trigger
   belongs to p1-customer-master-hist in w2-d; coordinate the shared trigger text but write
   only your target).
"""),
        ("w2-c", ["p1-entity-attr-value"],
         ["billing.entity_attr_value"],
         [],
         """
ENTITY_ATTR_VALUE (8,333 rows): entity-attribute-value, everything typed as string. No type
promotion in pipeline 1 - attr_value stays text. seq_entity_attr_value and
trg_entity_attr_value_seq convert with the table. Duplicate-attribute rows are compared as a
set, not deduplicated.
"""),
        ("w2-d", ["p1-customer-master-hist", "p1-subscriptions-hist"],
         ["ow_tp.silver.customer_master_hist", "ow_tp.silver.subscriptions_hist"],
         [],
         """
The two history tables into Delta: CUSTOMER_MASTER_HIST (158 cols) and SUBSCRIPTIONS_HIST.
Both are EMPTY today, so recon proves schema parity and an empty-set assertion only. Record
the verdict as NOT DATA-PROVEN in summary.md and in the PR - nobody may later mistake it for
data evidence. The trigger-maintained full-row-copy behaviour still has to be converted
(seq_customer_master_hist, seq_subscriptions_hist and their triggers) and described.
"""),
        ("w2-e", ["p1-billing-audit-log", "p1-job-purge-audit-log"],
         ["ow_tp.silver.billing_audit_log", "ow_tp_p1_purge_audit_log"],
         [],
         """
BILLING_AUDIT_LOG (empty) into Delta plus its retention job.
 - The table is written by pkg_ow_util.log_msg's autonomous transaction (converted in wave 0
   under P1-D1); this unit owns the table, sequence seq_billing_audit_log and trigger
   trg_billing_audit_log_id.
 - JOB_PURGE_AUDIT_LOG (schema/04_jobs.sql:21-31): 90-day retention hardcoded in the job
   text, and `WHEN OTHERS THEN NULL`. Convert to a Lakeflow job `ow_tp_p1_purge_audit_log`,
   schedule CREATED PAUSED, keep the retention constant visible as a parameter with the same
   default, and reproduce the swallowed error behaviour (P1-D2).
 - Empty table: schema parity + empty-set assertion, recorded NOT DATA-PROVEN. The job has no
   live run to compare against (the Oracle jobs are DISABLED) - state that gap plainly.
"""),
        ("w2-f", ["p1-credit-notes"],
         ["billing.credit_notes"],
         [],
         """
CREDIT_NOTES (5 rows). Small but load-bearing: wave 3's invoicing burn-down (w3-b) UPDATEs
these rows in `issued_on, id` order, and that order is part of the contract. It sits in wave
2 rather than beside invoicing so that nothing writes the table while invoicing does: the
DDL lands and merges a whole wave earlier. Convert the table, its constraints and indexes,
and state the ordering guarantee in the unit README. Do not implement the burn-down, and do
not write billing.invoices or billing.invoice_lines.
It depends only on billing.tenants (fk_cn_tenant), which merged in wave 1.
"""),
    ]),
    # Same cap reason as wave 2. Three batches now: credit notes moved to wave 2 so invoicing
    # is the only writer of that table while it runs.
    (3, 3, [
        ("w3-a", ["p1-rating-periods", "p1-rating-results"],
         ["billing.rating_periods", "billing.rating_results"],
         [],
         """
The rating tables: RATING_PERIODS (3) and RATING_RESULTS (3).
pkg_rating itself is NOT in this batch. It ran here first, found no billing.usage_events to
read on the operational track, and reported BLOCKED; D-011 re-placed it in wave 4 as w4-d,
behind the unit that lands that table. Deliver the tables and their constraints only.
Ids are f_md5_uuid outputs from wave 0 - if the parity proof did not land, stop here.
 - Reproduce every Oracle constraint, not just the data: a foreign key missing in the
   target still passes a row-level diff, so read ALL_CONSTRAINTS and match it.
 - Oracle TIMESTAMP is zoneless -> Postgres timestamp, never timestamptz (D-010).
 - The rating_state hand-off row belongs to w4-d, which writes it. Do not populate it here.
"""),
        ("w3-b", ["p1-invoices", "p1-invoice-lines"],
         ["billing.invoices", "billing.invoice_lines"],
         # Data-only since pkg_invoicing left for w4-b: the credit-note burn-down and the
         # log_msg audit write went with it, so this batch declares no runtime writes and a
         # write to either table while it runs is a real undeclared write, not batch noise.
         [],
         """
Modern INVOICES (3) + INVOICE_LINES (2). pkg_invoicing left this batch for wave-4 w4-b
under D-009: sp_issue_invoice calls sp_finalize_rating, so it writes w3-a's rating tables,
and a runtime write is only safe once its owner merged in an earlier wave.
THIS IS THE MODERN GENERATION (D9-01), not legacy INVOICE_HEADER/INVOICE_LINE from wave 1.
You run CONCURRENTLY with w3-a (rating), whose hand-off you consume:
 - rating hand-off: read `billing.rating_state` per the shape pinned in the plan (P1-D4).
   Code against that contract, not against w3-a's working tree, and stub it in your fixture.
 - credit notes: billing.credit_notes merged in wave 2 (w2-f) and nothing else writes it
   now, so the burn-down's UPDATEs are yours alone. Consume them in `issued_on, id` order.
   You own DML on that table, never its DDL.
Never convert or write another batch's objects. At the wave gate the orchestrator re-runs
your Tier-4 op diff after w3-a merges; a contract mismatch surfaces there and is a
wave-level finding, not something you route around mid-flight.
Traps:
 - tax rate hardcoded 0.0825 at :26 - keep the value, make it a named constant;
 - reads pkg_rating's globals (g_overage_amount): consume the explicit hand-off w3-a defined;
 - EXECUTE IMMEDIATE delete of invoice lines -> plain DELETE, same rows;
 - the credit burn-down decrements a running counter in a quirk the source says to preserve
   verbatim (:180-190). Preserve it, in `issued_on, id` order;
 - rounding is applied per line AND again on the total. Both roundings stay.
Money is exact in recon: a one-cent difference is a FAIL, not a tolerance.
Runtime writes: billing.credit_notes rows are UPDATEd by the burn-down (DDL ownership stays
with w2-f, merged in wave 2); it is a declared runtime write on this batch, and it goes in
your PR body too.
"""),
        ("w3-d", ["p1-dunning-attempts", "p1-notifications", "p1-pkg-dunning"],
         ["billing.dunning_attempts", "billing.notifications", "billing.sp_schedule_dunning",
          "billing.sp_suspend_overdue", "billing.fn_overdue_accounts"],
         # runtime writes; owners w1-a/w2-a, and wave 0 for the audit log (D-009)
         ["billing.tenants", "billing.subscriptions", "billing.billing_audit_log"],
         """
The dunning chain: DUNNING_ATTEMPTS (1), NOTIFICATIONS (1) and pkg_dunning
(packages/05_pkg_dunning.sql). One batch, not three, because sp_suspend_overdue writes both
tables and splitting it would create a write-target collision. The Lakeflow job that calls
it is U-25, deliberately held back to wave 4.
You read invoices produced by w3-b, which runs concurrently: develop and reconcile against
the FIXTURE invoice state, never against w3-b's in-flight branch. The wave gate re-runs your
op diff after w3-b merges.
Traps:
 - `WHEN OTHERS THEN NULL` swallows every scheduling error (:63-66). Reproduce the observable
   behaviour (P1-D2): a legacy run can silently schedule fewer attempts than expected, so the
   recon baseline is the rows it actually wrote, not the rows it should have written;
 - weekend shift by DECODE on TO_CHAR(...,'DY') with English NLS - pin the locale explicitly,
   Postgres will not inherit Oracle's NLS;
 - `(+)` outer join -> ANSI join;
 - the suspension sweep also UPDATEs billing.tenants and billing.subscriptions (:81-84). DDL
   for those tables stays with w1-a/w2-a (merged); declare the runtime writes in your PR;
 - DUNNING_ATTEMPTS has a unique key that is implied and never declared - declare it, and say
   so in the mapping;
 - NOTIFICATIONS dedupe is a NOT EXISTS on (tenant, kind, sent_at): same semantics, same
   result set;
 - fn_overdue_accounts and sp_schedule_dunning order by `issued_at, id`: keep them
   deterministic or recon will cry wolf.
Do not create the nightly job here; that is U-25 in wave 4.
"""),
    ]),
    # Width 1: w4-c -> w4-d -> w4-b is a dependency chain (usage_events, then pkg_rating,
    # then invoicing), and the manifest schema has no way to express batch dependencies, so
    # the wave is dispatched one batch at a time in manifest order. A wider wave would start
    # w4-d before its table exists and turn a timing race into a BLOCKED result.
    (4, 1, [
        ("w4-c", ["p1-usage-events-oltp"],
         ["billing.usage_events"],
         [],
         """
U-28 USAGE_EVENTS onto the OPERATIONAL track, and the unblocker for the rest of this wave.
The same source table already landed in Delta as U-18 in wave 1; that copy stays and is the
analytical one. This unit is the Lakebase copy pkg_rating actually reads (D-011).
Why it exists: pkg_rating reads usage_events row-at-a-time in compute_rating and
fn_usage_summary. Wave 3's p1-pkg-rating had nothing to read and reported BLOCKED rather
than materialising a copy inside a package unit, which would have been an undeclared write
over data nobody reconciled. This unit is that decision made properly, with a declared
write target and its own recon.
 - Same source rows, same keys as U-18. Reconcile against Oracle, not against the Delta
   copy: two targets of one source, never one target of another.
 - Oracle TIMESTAMP is zoneless -> Postgres timestamp, never timestamptz (D-010).
 - Write ONLY billing.usage_events. The rating tables belong to wave 3 and are merged.
w4-d and w4-b are serialized behind you: report the moment the table is loaded.
"""),
        ("w4-d", ["p1-pkg-rating"],
         ["billing.sp_finalize_rating", "billing.fn_usage_rating",
          "billing.fn_usage_summary"],
         ["billing.rating_periods", "billing.rating_results", "billing.rating_state",
          "billing.billing_audit_log"],
         """
U-22 pkg_rating, retried here after wave 3 reported it BLOCKED (D-011). Run only once w4-c
has loaded billing.usage_events; if the table is absent, report BLOCKED again rather than
creating it.
The rating tables it writes (rating_periods, rating_results) are wave-3 units and are
already delivered: call them, do not re-convert or re-load them, and declare the writes as
runtime writes, which the manifest does for you.
 - billing.rating_state carries the g_overage_amount hand-off to pkg_invoicing. It is
   package-global state: make it explicit, and keep updated_at zoneless (D-010).
 - billing.billing_audit_log, through the converted log_msg. Keep the logging; declaring it
   is the fix, never dropping the call (D-009).
 - compute_rating's per-row rounding stays exactly where the source puts it.
w4-b is serialized behind you because sp_issue_invoice calls sp_finalize_rating.
"""),
        ("w4-a", ["p1-job-nightly-dunning"],
         ["ow_tp_p1_nightly_dunning"],
         [],
         """
U-25 JOB_NIGHTLY_DUNNING, serial and last, because it is the only unit that orchestrates the
whole converted chain: it calls pkg_dunning (w3-d), which reads invoices (w3-b) and rating
(w3-a). Everything it calls is merged before you start; read it, do not re-convert it.
Deliver the Lakeflow job `ow_tp_p1_nightly_dunning`, daily 02:00, **CREATED PAUSED**. Devin
never enables a schedule; enabling it is part of the user's STOP E cutover decision.
The Oracle scheduler jobs are DISABLED, so there is no live run to compare against: verify by
run-history equivalence on the fixture (one fixture run of the legacy job vs one run of the
converted job, same input state, same rows written) and state that gap plainly in summary.md
and the PR. The data recon on billing.dunning_attempts is threshold/sampled only - the row
contract belongs to w3-d, and you must not re-write its tables.
"""),
        ("w4-b", ["p1-pkg-invoicing"],
         ["billing.sp_issue_invoice", "billing.fn_invoice_preview",
          "billing.fn_invoice_lines"],
         ["billing.credit_notes", "billing.billing_audit_log",
          # rating_state as well: the same sp_finalize_rating call writes the hand-off row.
          "billing.rating_periods", "billing.rating_results", "billing.rating_state",
          # sp_issue_invoice inserts the header and rebuilds its lines (source :137-160),
          # and those two tables are w3-b's, so the DML is a runtime write here.
          "billing.invoices", "billing.invoice_lines"],
         """
pkg_invoicing (packages/04_pkg_invoicing.sql) -> sp_issue_invoice, fn_invoice_preview,
fn_invoice_lines. THIS IS THE MODERN GENERATION (D9-01), not legacy INVOICE_HEADER/
INVOICE_LINE. It ran in wave 3 inside w3-b and halted on `undeclared_write_target`; D-009
declared the writes and moved the unit here, because a runtime write is only safe once the
owning unit merged in an earlier wave and wave 3 owns the rating tables.
What it writes, all declared and all real legacy behaviour to preserve:
 - billing.billing_audit_log, through the converted pkg_ow_util.log_msg. Keep the logging.
 - billing.rating_periods and billing.rating_results, because sp_issue_invoice calls
   pkg_rating.sp_finalize_rating. Call the converted procedure; do not re-convert it.
 - billing.credit_notes, the burn-down's UPDATEs, in `issued_on, id` order. DML only.
 - billing.invoices and billing.invoice_lines: sp_issue_invoice inserts the header, flips
   status_cd to 20, and deletes-then-reinserts the lines. w3-b owns those tables and has
   delivered them - DML only, no DDL, no reload.
Read billing.rating_state for the package-global hand-off from pkg_rating
(g_overage_amount): it is state, so make it explicit rather than incidental.
Traps:
 - tax rate hardcoded 0.0825 at :26 - keep the value, make it a named constant;
 - EXECUTE IMMEDIATE delete of invoice lines -> plain DELETE, same rows;
 - the credit burn-down decrements a running counter in a quirk the source says to preserve
   verbatim (:180-190);
 - rounding is applied per line AND again on the total. Both roundings stay.
Money is exact in recon: a one-cent difference is a FAIL, not a tolerance. Oracle TIMESTAMP
is zoneless -> Postgres timestamp, never timestamptz (D-010).
"""),
    ]),
]


def main() -> int:
    caps_doc = json.loads(CAPS_FILE.read_text())
    rows = {c["id"]: (c.get("data") or {}) for c in caps_doc["checks"]}
    caps = {
        "identity": caps_doc["identity"]["userName"],
        "host": caps_doc["identity"]["host"],
        "catalogs": rows["allowed_targets"]["catalogs"],
        "guard_mode": rows["allowed_targets"]["guard_mode"],
        "stop_mode": rows["stop_mode"]["stop_mode"],
        "ready": True,
    }
    if caps["stop_mode"] != "soft":
        raise SystemExit(f"00_context.md records stop_mode={caps['stop_mode']!r}; auto_merge below "
                         "assumes the recorded mode. Re-derive it before generating manifests.")
    check_estimates_fresh()
    WAVES.mkdir(parents=True, exist_ok=True)
    branches = wave_branches([w for w, _, _ in PLAN])
    for wave, width, batches in PLAN:
        if width > SOURCE_QUERY_CAP:
            raise SystemExit(
                f"wave {wave}: width {width} exceeds source_query_cap {SOURCE_QUERY_CAP}; "
                "every batch takes a live source read at its gate, so the fan-out width is "
                "the concurrency the source sees")
        lb_branch, cut_from = branches[wave]
        units = [u for _, us, _, _, _ in batches for u in us]
        manifest = {
            "wave": wave,
            "repo": REPO,
            "child_macro": CHILD_MACRO,
            "verify_macro": VERIFY_MACRO,
            "width": width,
            "breaker_threshold": 3,
            # 00_context.md records stop_mode=soft AND auto_merge=false: a human reviews every
            # unit PR and the recon verdict is the merge authority, so never true here.
            "auto_merge": False,
            "child_minutes": 90,
            "verify_depth": "sampled",
            "cost_estimate": cost(units),
            "capabilities": caps,
            "source": SOURCE,
            "base_branch": BASE_BRANCH,
            "controls": {
                "source_query_cap": SOURCE_QUERY_CAP,
                "recon_rerun_cap": 3,
                "review_round_cap": 3,
                "breaker_class": "3 same-class failures halts the wave and escalates",
                "lakebase_branch": lb_branch,
                "lakebase_branch_cut_from": cut_from,
                "lakebase_branch_lifecycle": (
                    (f"the orchestrator creates {lb_branch} off {cut_from} ONCE, before fan-out, "
                     f"so it carries everything waves up to {wave - 1} merged"
                     if cut_from else
                     f"this wave continues on {lb_branch} (no separate branch is allowlisted for "
                     f"wave {wave}; waves are sequential, so the state is still the previous "
                     f"wave's output)")
                    + ". Children never create, reset or drop a branch - concurrent batches share "
                    "it and are isolated by disjoint write targets. The orchestrator keeps each "
                    "branch until the next wave has been cut from it, then drops it at pipeline "
                    "close; never the production branch"),
                "idempotency": (
                    "every converted load is re-runnable: truncate-and-load or MERGE on the "
                    "declared key, no append-only inserts; recon reruns must not change target "
                    "row counts"),
                "namespace_isolation": (
                    "a batch writes only its declared write_targets plus its declared "
                    "runtime_writes; DDL for a table belongs to exactly one unit, and a "
                    "runtime write is only allowed where that owner merged in an earlier wave"),
                "fixture_vs_live": (
                    "children own fixture runs (make oracle-billing-up) and take exactly one live "
                    "source read per unit; only a live/snapshot/transactional PASS is merge "
                    "evidence, a fixture PASS never is"),
                "source_volume_assertions": {
                    u: json.loads((UNITS / u / "cost_estimate.json").read_text())["row_counts"]
                    for u in units if (UNITS / u / "cost_estimate.json").exists()
                },
            },
            "batches": [
                {
                    "id": bid,
                    "units": us,
                    "write_targets": tg,
                    # DML into tables whose DDL a unit in an EARLIER wave owns. Declared, not
                    # left to a PR body: the checker proves nothing running beside this batch
                    # writes them, which is the only thing that makes the write safe.
                    "runtime_writes": rw,
                    "verify_depth": "full" if any(UNIT[u][2] == "full" for u in us) else "sampled",
                    "lakebase_branch": (lb_branch if any(UNIT[u][1] == "lakebase" for u in us)
                                        else None),
                    "brief": brief(wave, bid, us, tg, rw,
                                   lb_branch if any(UNIT[u][1] == "lakebase" for u in us) else None,
                                   cut_from, body),
                }
                for bid, us, tg, rw, body in batches
            ],
        }
        out = WAVES / f"wave-{wave}.json"
        out.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{out.relative_to(ROOT)}: width {width}, {len(manifest['batches'])} batches, "
              f"{len(units)} units, cost {manifest['cost_estimate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
