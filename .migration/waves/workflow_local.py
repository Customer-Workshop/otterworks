"""LOCAL backend of the migration-fanout skill (derived from the plugin workflow.py: same guards,
result and brief shape). Children are shared-VM subagents because the Oracle source is
reachable only from this machine (localhost:52521); separate-VM children cannot read it.

Original: Cloud backend of the migration-fanout skill: run one wave of unit-migration children,
then one independent verifier, and write <manifest>.result.json and <manifest>.brief.md.

Run with the `run_workflow` tool (Devin Cloud). Env: WAVE_MANIFEST (the wave file the plan
wrote), WAVE_RUN_ID (the run_workflow run_id, first run and every resume), WAVE_RESUME=1
to continue a halted run, WAVE_RERUN=1 to redo a wave. Guards are listed in SKILL.md.

Manifest shape (written by the plan playbook):
{
  "wave": 2,
  "repo": "github.com/acme/mongo-target",
  "child_macro": "!mongo_unit_migration",
  "verify_macro": "!mongo_reconciliation",
  "width": 20,
  "breaker_threshold": 3,
  "auto_merge": true,
  "source_access": "live",                    # live | snapshot | ddl_only (from 08_connectivity.json)
  "target_access": "migration_cluster",       # migration_cluster | local; local waves never auto_merge
  "child_minutes": 45,                        # soft time limit per child
  "batches": [
    {"id": "w2-b01", "units": ["orders", "order_items"],
     "write_targets": ["app_migration.orders", "app_migration.order_items"],
     "fixture_manifest": ".migration/fixtures/w2-b01.json",
     "brief": "...complete hand-off text for this batch..."}
  ]
}
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

WAVES_DIR = Path("/home/ubuntu/repos/otterworks/.migration/waves").resolve()
_ACTIVE = WAVES_DIR / "ACTIVE_MANIFEST"  # run_workflow passes no env; the orchestrator writes the manifest path here
MANIFEST_PATH = Path(os.environ.get("WAVE_MANIFEST")
                     or (_ACTIVE.read_text().strip() if _ACTIVE.exists() else str(WAVES_DIR / "wave-1.json"))).resolve()
if MANIFEST_PATH.suffix != ".json" or not MANIFEST_PATH.is_relative_to(WAVES_DIR):
    raise SystemExit(f"WAVE_MANIFEST must be a .json file inside {WAVES_DIR}")
if not MANIFEST_PATH.exists():
    raise SystemExit(f"no wave manifest at {MANIFEST_PATH}. Set WAVE_MANIFEST to the file the "
                     "plan playbook wrote, then re-run.")
MANIFEST_TEXT = MANIFEST_PATH.read_text()
MANIFEST = json.loads(MANIFEST_TEXT)
REPO_ROOT = MANIFEST_PATH.parents[2]
MANIFEST_SHA = hashlib.sha256(MANIFEST_TEXT.encode()).hexdigest()[:12]
RESULT_PATH = MANIFEST_PATH.with_suffix(".result.json")
BRIEF_PATH = MANIFEST_PATH.with_suffix(".brief.md")
RUN_ID_PATH = MANIFEST_PATH.with_suffix(".run_id")
_RESUME_FLAG = WAVES_DIR / "ACTIVE_RESUME"  # run_workflow passes no env; the orchestrator touches this file to resume
resume = os.environ.get("WAVE_RESUME") == "1" or _RESUME_FLAG.exists()
prior = None

if RESULT_PATH.exists() and os.environ.get("WAVE_RERUN") != "1":
    try:
        prior = json.loads(RESULT_PATH.read_text())
        if not isinstance(prior, dict):
            raise ValueError("result is not a JSON object")
    except ValueError:
        if not resume:
            raise SystemExit(f"{RESULT_PATH} is not valid JSON (interrupted write?). Inspect it; to resume "
                             "the same run set WAVE_RESUME=1 with the recorded run_id, or set WAVE_RERUN=1 "
                             "to redo the wave.") from None
    else:
        if prior.get("closed"):
            raise SystemExit(f"{RESULT_PATH} says wave {prior.get('wave')} closed clean. To redo it on "
                             "purpose, set WAVE_RERUN=1.")
        if not resume:
            raise SystemExit(f"{RESULT_PATH} records a halted or failed run. To continue it, re-run with the "
                             "recorded run_id AND WAVE_RESUME=1 (finished children replay). To redo the wave "
                             "from scratch, set WAVE_RERUN=1.")
if resume:
    run_id = os.environ.get("WAVE_RUN_ID") or (RUN_ID_PATH.read_text().strip() if RUN_ID_PATH.exists() else None)
    if not run_id:
        raise SystemExit("WAVE_RESUME=1 requires WAVE_RUN_ID; pass the recorded run_id")
    if not RUN_ID_PATH.exists():
        raise SystemExit(f"no run record at {RUN_ID_PATH}; cannot verify WAVE_RUN_ID belongs to this wave "
                         "— use WAVE_RERUN=1 for a fresh run")
    if RUN_ID_PATH.read_text().strip() != run_id:
        raise SystemExit(f"WAVE_RUN_ID does not match {RUN_ID_PATH}; pass the recorded run_id to "
                         "run_workflow and WAVE_RUN_ID, or WAVE_RERUN=1 for a fresh run")
    if isinstance(prior, dict) and prior.get("run_id") and prior["run_id"] != run_id:
        raise SystemExit(f"WAVE_RUN_ID does not match prior result at {RESULT_PATH}; pass the recorded "
                         "run_id to run_workflow and WAVE_RUN_ID, or WAVE_RERUN=1 for a fresh run")

REPLAYED = {
    b["id"]: b["status"] for b in (prior or {}).get("batches", [])
    if b.get("status") in ("PASS", "FAIL", "BLOCKED")
} if resume and isinstance(prior, dict) else {}
PRIOR_RESULTS = {b["id"]: b for b in (prior or {}).get("batches", [])} if resume and isinstance(prior, dict) else {}
RETRY_NOTE = ("\n\nRESUME: a previous attempt of this batch ended BLOCKED/FAIL; the orchestrator has since fixed the "
              "blocking input on the run branch (see .migration/05_decisions.md, latest rows). Start from the current "
              "run branch tip. If a branch/PR from the earlier attempt exists for this batch, reuse it (rebase onto the "
              "run branch) instead of opening a second PR.")


def validate_fixture_manifest(batch_id, path: str, root: Path) -> None:
    if (not isinstance(path, str) or not path
            or not path.startswith(".migration/fixtures/")
            or not path.endswith(".json")):
        raise SystemExit(
            f"batch {batch_id} fixture_manifest must be a path under "
            ".migration/fixtures/*.json")
    resolved = (root / path).resolve()
    fixture_root = (root / ".migration/fixtures").resolve()
    if not resolved.is_relative_to(fixture_root):
        raise SystemExit(f"batch {batch_id} fixture_manifest escapes .migration/fixtures/")
    try:
        fixture = json.loads(resolved.read_text())
    except (OSError, TypeError, json.JSONDecodeError):
        raise SystemExit(f"batch {batch_id} fixture manifest {path} is not readable") from None
    if not isinstance(fixture, dict):
        raise SystemExit(f"batch {batch_id} fixture manifest {path} is not readable")
    required = ("source", "method", "masked_columns", "produced_at", "produced_by", "row_counts")
    for key in required:
        valid = key in fixture
        if key == "method":
            valid = valid and fixture[key] in ("synthetic", "masked_export")
        elif key == "masked_columns":
            valid = valid and isinstance(fixture[key], list)
        elif key == "row_counts":
            valid = valid and isinstance(fixture[key], dict)
        elif key in ("source", "produced_at", "produced_by"):
            valid = valid and isinstance(fixture[key], str) and bool(fixture[key])
        if not valid:
            raise SystemExit(f"batch {batch_id} fixture manifest {path} is missing '{key}'")
    if fixture["method"] == "masked_export" and (
            not isinstance(fixture.get("masking_verified"), str)
            or not fixture["masking_verified"]):
        raise SystemExit(
            f"batch {batch_id} fixture manifest {path} is a masked export without masking_verified")


def validate_manifest(m):
    for key in ("wave", "repo", "child_macro", "verify_macro", "batches"):
        if key not in m:
            raise SystemExit(f"manifest is missing '{key}'")
    if not m["batches"]:
        raise SystemExit("manifest has no batches")
    for key in ("width", "breaker_threshold", "child_minutes"):
        if key in m and (isinstance(m[key], bool) or not isinstance(m[key], int) or m[key] <= 0):
            raise SystemExit(f"manifest key '{key}' must be a positive integer")
    access = {"source_access": ("live", "snapshot", "ddl_only"),
              "target_access": ("migration_cluster", "local")}
    for key, allowed in access.items():
        if key in m and m[key] not in allowed:
            raise SystemExit(f"manifest key '{key}' must be one of {allowed}")
    if m.get("auto_merge") and (m.get("source_access") == "ddl_only"
                                or m.get("target_access", "migration_cluster") != "migration_cluster"):
        raise SystemExit("auto_merge requires source_access live|snapshot and target_access "
                         "migration_cluster: a DDL-only source or local target never produces merge evidence")
    ids = Counter(b.get("id") for b in m["batches"])
    dupes = [i for i, c in ids.items() if c > 1 or not i]
    if dupes:
        raise SystemExit(f"batch ids must be unique and non-empty: {dupes}")
    for b in m["batches"]:
        for key in ("units", "write_targets", "brief"):
            if not b.get(key):
                raise SystemExit(f"batch {b['id']} is missing '{key}' (a child with no brief or "
                                 "no declared write targets cannot be launched safely)")
        if not isinstance(b.get("fixture_manifest"), str) or not b["fixture_manifest"]:
            raise SystemExit(f"batch {b['id']} is missing 'fixture_manifest'")
        validate_fixture_manifest(b["id"], b["fixture_manifest"], REPO_ROOT)


validate_manifest(MANIFEST)


def report_headers_match(text: str, run_id: str, manifest_sha: str) -> bool:
    lines = text.splitlines()
    return lines[:2] == [f"run_id: {run_id}", f"manifest_sha: {manifest_sha}"]


def report_is_current(branch: str, path: str, run_id: str, manifest_sha: str) -> bool:
    try:
        fetched = subprocess.run(["git", "-C", str(REPO_ROOT), "fetch", "origin", branch], capture_output=True)
        if fetched.returncode != 0:
            return False
        checked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"origin/{branch}:{path}"],
            capture_output=True)
        if checked.returncode != 0:
            return False
        return report_headers_match(checked.stdout.decode(), run_id, manifest_sha)
    except OSError:
        return False


def verify_schema(passed: list[dict], wave) -> dict:
    ids = sorted(p["batch"] for p in passed)
    escaped_wave = re.escape(str(wave))
    return {
        "type": "object",
        "properties": {
            "wave_verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "unit_verdicts": {
                "type": "object",
                "properties": {
                    i: {"type": "string", "enum": ["PASS", "FAIL"]} for i in ids
                },
                "required": ids,
                "additionalProperties": False,
            },
            "findings": {"type": "array", "items": {"type": "string"}},
            "report_path": {
                "type": "string",
                "pattern": f"^recon/wave-{escaped_wave}:"
                           f"\\.migration/recon/wave-{escaped_wave}/report\\.md$",
            },
        },
        "required": ["wave_verdict", "unit_verdicts", "findings", "report_path"],
        "additionalProperties": False,
    }


def validate_verify(verify, passed, wave, *, run_id, manifest_sha,
                    exists=report_is_current) -> list[str]:
    problems = []
    if not isinstance(verify, dict):
        return ["verifier output invalid: expected an object"]
    expected = {p.get("batch") for p in passed}
    if None in expected:
        problems.append("verifier output invalid: passed batch is missing its id")
        expected.discard(None)
    verdicts = verify.get("unit_verdicts")
    if not isinstance(verdicts, dict):
        problems.append("verifier output invalid: unit_verdicts must be a dict")
        verdicts = {}
    missing = sorted(expected - set(verdicts))
    extra = sorted(set(verdicts) - expected)
    units = {u for p in passed for u in p.get("units", [])}
    unit_keyed = sorted(k for k in extra if k in units)
    if unit_keyed:
        problems.append("verifier output invalid: unit_verdicts keyed by unit/collection names ("
                        + ", ".join(unit_keyed) + "); keys must be batch ids: "
                        + ", ".join(sorted(expected)))
        extra = [k for k in extra if k not in units]
    if missing:
        problems.append("verifier output invalid: missing verdicts for " + ", ".join(missing))
    if extra:
        problems.append("verifier output invalid: unexpected verdicts for " + ", ".join(extra))
    wave_verdict = verify.get("wave_verdict")
    if wave_verdict not in ("PASS", "FAIL"):
        problems.append("verifier output invalid: wave_verdict must be PASS or FAIL")
    for batch in sorted(expected):
        verdict = verdicts.get(batch)
        if verdict not in ("PASS", "FAIL"):
            problems.append(f"verifier output invalid: verdict for {batch} is {verdict!r}")
        elif wave_verdict == "PASS" and verdict != "PASS":
            problems.append(f"verifier output invalid: wave PASS contradicts {batch}={verdict}")
    if wave_verdict == "FAIL" and expected and all(verdicts.get(b) == "PASS" for b in expected):
        problems.append("verifier output invalid: wave FAIL contradicts all unit verdicts PASS")
    if not isinstance(verify.get("findings"), list):
        problems.append("verifier output invalid: findings must be a list")
    expected_report = (
        f"recon/wave-{wave}:.migration/recon/wave-{wave}/report.md")
    report_path = verify.get("report_path")
    if report_path != expected_report:
        problems.append(
            f"verifier output invalid: report_path must be exactly '{expected_report}'")
    else:
        branch, path = report_path.split(":", 1)
        if not exists(branch, path, run_id, manifest_sha):
            problems.append(
                f"verifier output invalid: report {path} on branch {branch} is missing or "
                f"does not reference run_id {run_id} / manifest_sha {manifest_sha}")
    return problems


def validate_merge(merged, urls) -> list[str]:
    if not isinstance(merged, dict) or not isinstance(merged.get("merged_prs"), list):
        return ["merge output invalid: merged_prs must be a list"]
    merged_prs = merged["merged_prs"]
    problems = [f"merge output invalid: merged_prs is missing {url}" for url in urls
                if url not in merged_prs]
    problems += [f"merge output invalid: merged_prs includes unverified {url}"
                 for url in dict.fromkeys(merged_prs) if url not in urls]
    problems += [f"merge output invalid: merged_prs lists {url} more than once"
                 for url in dict.fromkeys(merged_prs) if merged_prs.count(url) > 1]
    return problems


def merge_schema() -> dict:
    return {
        "type": "object",
        "required": ["merged_prs"],
        "additionalProperties": False,
        "properties": {"merged_prs": {"type": "array", "items": {"type": "string"}}},
    }


def merge_prompt(urls, run_id) -> str:
    return (
        f"Merge phase for run {run_id}. Merge exactly these PRs (squash), nothing else: "
        f"{json.dumps(urls, sort_keys=True)}. Do not edit any file. Return merged_prs. "
        "LOCAL BACKEND: run `gh pr merge <url> --squash` from /home/ubuntu/repos/otterworks "
        "(do not change its branch or files); a PR that is already MERGED (a prior resume pass) counts as merged, do not fail on it; confirm with `gh pr view <url> --json state,mergedAt`. Report via provide_structured_output."
    )


WAVE = MANIFEST["wave"]
REPO = MANIFEST["repo"]
BATCHES = sorted(MANIFEST["batches"], key=lambda b: b["id"])
WIDTH = int(MANIFEST.get("width", 20))
BREAKER = int(MANIFEST.get("breaker_threshold", 3))
AUTO_MERGE = bool(MANIFEST.get("auto_merge", True))
CHILD_MINUTES = int(MANIFEST.get("child_minutes", 45))

META = {
    "name": f"migration-wave-{WAVE}",
    "description": f"Wave {WAVE}: {len(BATCHES)} unit batches in parallel, then one independent verifier",
    "phases": [
        {"title": "migrate", "detail": "one child per batch: convert, load, recon, open PR",
         "labels": [b["id"] for b in BATCHES], "soft_time_limit_minutes": CHILD_MINUTES},
        {"title": "verify", "detail": "independent recon over the wave",
         "count": 1, "soft_time_limit_minutes": 60},
        {"title": "merge", "detail": "merge exactly the PRs validated by verify",
         "count": 1, "soft_time_limit_minutes": 15},
    ],
}

CHILD_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
        "pr_url": {"type": "string"},
        "branch": {"type": "string"},
        "recon_verdict": {"type": "string", "enum": ["PASS", "FAIL", "NOT_RUN"]},
        "recon_mode": {"type": "string"},
        "target_class": {"type": "string", "enum": ["migration_cluster", "local"]},
        "failure_class": {"type": "string"},
        "write_targets": {"type": "array", "items": {"type": "string"}},
        "skill_feedback": {"type": "array", "items": {"type": "string"}},
        "one_line_summary": {"type": "string"},
    },
    "required": ["status", "recon_verdict", "recon_mode", "write_targets", "one_line_summary"],
}

def check_write_targets(batches):
    owners = {}
    for b in batches:
        for t in b.get("write_targets", []):
            if t in owners:
                raise SystemExit(f"write-target collision before launch: '{t}' is claimed by "
                                 f"{owners[t]} and {b['id']}. Fix the wave plan, then re-run.")
            owners[t] = b["id"]


def child_prompt(batch):
    return (
        f"You are one fan-out child in wave {WAVE} of a migration. Repo: {REPO}.\n"
        f"Run the playbook {MANIFEST['child_macro']} for batch {batch['id']} exactly as written.\n\n"
        f"BATCH BRIEF (your complete hand-off; if anything is missing, report status=BLOCKED "
        f"with the missing item in one_line_summary, do not improvise):\n"
        f"{batch['brief']}\n\n"
        f"Units: {json.dumps(batch['units'], sort_keys=True)}\n"
        f"Write targets you own (never write anywhere else): "
        f"{json.dumps(batch.get('write_targets', []), sort_keys=True)}\n\n"
        f"Fixture manifest (synthetic/masked only; refuse to start if missing): "
        f"{batch['fixture_manifest']}\n\n"
        f"Access: source_access={MANIFEST.get('source_access', 'live')} "
        f"target_access={MANIFEST.get('target_access', 'migration_cluster')}; pass the target as "
        "`recon run --target-class` and report it as target_class.\n\n"
        "Rules that override anything else:\n"
        "- Do not edit files under .migration/. The workflow writes the ledger from your report.\n"
        "- Do not merge your own PR.\n"
        "- status=PASS requires a live or snapshot recon PASS against the migration cluster "
        "(result.json merge_eligible=true). Fixture or local-target evidence is never PASS.\n"
        "- If the recon harness fails 3 full runs, stop and report status=FAIL with a short "
        "failure_class (for example 'timestamp_precision', 'decimal_rounding', 'missing_rule').\n"
        "- Report every rule you had to derive yourself in skill_feedback.\n"
        "- one_line_summary is for a human skimming 20 of these: what landed, or why not."
        "\n\nLOCAL BACKEND: you are a shared-VM subagent on the orchestrator's machine. The playbook body "
        "is the file /opt/.devin/plugins/cache/github.com_Cognition-Partner-Workshops_mongo-migration-plugin-6d021e15/0.3.0/skills/install-mongo-kit/playbooks/3-unit_migration.md; read it and follow it. "
        "Source profile: /opt/.devin/plugins/cache/github.com_Cognition-Partner-Workshops_mongo-migration-plugin-6d021e15/0.3.0/skills/mongo-migration/profiles/oracle.md. Secrets are environment variables "
        "ORACLE_BILLING_RO_DSN and MONGODB_MMP_RT_TARGET_URI (names only; never print values); run `source ~/.config/ow_billing_env.sh` in every shell first (Oracle DSN env + RECON_REDACT_SALT). "
        "Wave 0 already landed on the run branch: reuse services/legacy-billing/migration/common.py (row_to_doc, load_collection, reset_collection; extend it for embedded arrays rather than duplicating) and add your unit module under services/legacy-billing/app/backends/mongo/. Fixture recon = same instance, --mode fixture; then exactly one --mode live run. Work ONLY in your own git worktree named in the brief; never edit /home/ubuntu/repos/otterworks, "
        "never switch its branch, never kill other processes or shells. Open your PR with `gh pr create` from the worktree. "
        "Do not read, fetch or check out any branch other than tp-run/mongodb-20260926T164927Z-rt-live and your own. "
        "Report via provide_structured_output when done."
    )


def verify_prompt(passed, run_id, manifest_sha):
    return (
        f"You are the independent verifier for wave {WAVE}. Repo: {REPO}. You did not write "
        f"any of this code.\nRun the playbook {MANIFEST['verify_macro']} exactly as written over "
        f"these batches:\n{json.dumps(passed, sort_keys=True, indent=1)}\n\n"
        f"unit_verdicts must have exactly these keys, one per batch id (not per collection or unit): "
        f"{json.dumps(sorted(p['batch'] for p in passed))}. "
        "Re-run the recon harness yourself. Do not trust the PR's pasted evidence. "
        "Mark a unit PASS only if you re-ran the harness in live or snapshot mode and result.json says "
        "merge_eligible=true. Do not merge anything; return per-unit verdicts. "
        f"Write the wave recon report to .migration/recon/wave-{WAVE}/report.md, "
        f"commit it on branch recon/wave-{WAVE}, push, and set report_path to exactly "
        f"'recon/wave-{WAVE}:.migration/recon/wave-{WAVE}/report.md'. "
        f"The report's first lines must be `run_id: {run_id}` and "
        f"`manifest_sha: {manifest_sha}` (values given here: {run_id} / {manifest_sha}). "
        "Do not edit any other file under .migration/. Each finding is one plain "
        "sentence a lead can read without opening anything."
        "\n\nLOCAL BACKEND: shared-VM subagent. Playbook body: /opt/.devin/plugins/cache/github.com_Cognition-Partner-Workshops_mongo-migration-plugin-6d021e15/0.3.0/skills/install-mongo-kit/playbooks/4-reconciliation_and_parallel_run.md. "
        "Harness: ~/.venvs/recon/bin/recon, run from a worktree root containing .migration/; `source ~/.config/ow_billing_env.sh` in every shell first (Oracle DSN env + RECON_REDACT_SALT). Use your own worktree: "
        f"`git -C /home/ubuntu/repos/otterworks worktree add /home/ubuntu/wt/verify-wave-{WAVE} -b recon/wave-{WAVE} tp-run/mongodb-20260926T164927Z-rt-live`. "
        "For each PASS batch, re-run recon yourself in --mode live --target-class migration_cluster with --mapping .migration/mapping/<unit>.json, "
        "--source-dsn-secret ORACLE_BILLING_RO_DSN --target-uri-secret MONGODB_MMP_RT_TARGET_URI --target-db mmp_rt_billing "
        f"--allowed-targets-file .migration/allowed_targets.json --out .migration/recon/wave-{WAVE}/<batch>/<unit>/ against the ALREADY LOADED "
        "target collections (do not reload, never write to the cluster, never touch Oracle beyond SELECT). "
        "Never edit /home/ubuntu/repos/otterworks; never merge; read no branch other than tp-run/mongodb-20260926T164927Z-rt-live, the PR branches listed, and your own. "
        "Report via provide_structured_output when done."
    )


class Breaker:
    def __init__(self, threshold):
        self.threshold = threshold
        self.classes = Counter()
        self.tripped_on = None

    def record(self, failure_class):
        if not failure_class:
            return
        self.classes[failure_class] += 1
        if self.classes[failure_class] >= self.threshold and not self.tripped_on:
            self.tripped_on = failure_class
            log(f"CIRCUIT BREAKER: {self.threshold} children failed with '{failure_class}'. "
                "No new children will launch this run.")


async def run_batch(batch, sem, breaker):
    async with sem:
        if breaker.tripped_on:
            return {"status": "NOT_LAUNCHED", "recon_verdict": "NOT_RUN",
                    "one_line_summary": f"held back: breaker tripped on '{breaker.tripped_on}'"}
        try:
            if REPLAYED.get(batch["id"]) == "PASS":
                log(f"replay {batch['id']}: PASS from prior run")
                out = {k: v for k, v in PRIOR_RESULTS[batch["id"]].items() if k != "id"}
            elif batch.get("inline_result"):
                # single-session path (1-2 batches): the orchestrator ran !mongo_unit_migration
                # itself; the independent verifier and the merge phase still run here
                log(f"inline {batch['id']}: orchestrator-run batch, verifier still independent")
                out = dict(batch["inline_result"])
            else:
                log(f"launch {batch['id']} ({len(batch['units'])} units)")
                # vm_mode="shared": the Oracle source (localhost:52521) exists only on this machine
                prompt = child_prompt(batch) + (RETRY_NOTE if batch["id"] in REPLAYED else "")
                out = await agent(prompt, phase="migrate", schema=CHILD_SCHEMA,
                                  label=batch["id"], vm_mode="shared")
        except WorkflowAgentError as e:
            out = {"status": "FAIL", "recon_verdict": "NOT_RUN", "failure_class": "session_died",
                   "one_line_summary": f"child session died: {e}"}
        if (out["status"] == "PASS"
                and (out["recon_verdict"] != "PASS"
                     or out.get("recon_mode") not in ("live", "snapshot")
                     or out.get("target_class", "migration_cluster") != "migration_cluster")):
            out["status"] = "FAIL"
            out["failure_class"] = "non_merge_evidence"
            out["one_line_summary"] = (
                f"PASS downgraded: recon evidence was {out.get('recon_mode')}/"
                f"{out.get('target_class', 'migration_cluster')}/"
                f"{out.get('recon_verdict')}; " + out["one_line_summary"])
        if (out["status"] == "PASS"
                and (not out.get("pr_url") or not out.get("branch"))):
            out["status"] = "FAIL"
            out["failure_class"] = "missing_pr"
            out["one_line_summary"] = (
                "PASS downgraded: no PR URL/branch reported; " + out["one_line_summary"])
        if out["status"] != "PASS" and batch["id"] not in REPLAYED:
            breaker.record(out.get("failure_class") or "unclassified")
        log(f"done   {batch['id']}: {out['status']} / recon {out['recon_verdict']}: "
            f"{out['one_line_summary']}")
        return out


def write_brief(results, verify, surprises, undeclared, unreported, auto_merge, merged_prs):
    n = len(BATCHES)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = [b["id"] for b, r in zip(BATCHES, results) if r["status"] == "FAIL"]
    blocked = [b["id"] for b, r in zip(BATCHES, results) if r["status"] == "BLOCKED"]
    held = [b["id"] for b, r in zip(BATCHES, results) if r["status"] == "NOT_LAUNCHED"]
    feedback = sorted({s for r in results for s in r.get("skill_feedback", [])})
    lines = [
        f"# Wave {WAVE} close",
        "",
        f"Landed: {passed} of {n} batches passed their own recon.",
        f"Independent verify: {verify['wave_verdict'] if verify else 'NOT RUN'}"
        + (f", {len(merged_prs)} PRs merged." if verify and auto_merge else "."),
        f"Failed: {', '.join(failed) or 'none'}.",
        f"Blocked on missing inputs: {', '.join(blocked) or 'none'}.",
        f"Held back by circuit breaker: {', '.join(held) or 'none'}.",
    ]
    if surprises:
        lines.append(f"Merges held: two children reported the same write target "
                     f"({', '.join(surprises)}). A human decides which PR lands.")
    if undeclared:
        lines.append("Merges held: children wrote outside their declared targets: "
                     + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(undeclared.items()))
                     + ". A human decides which PR lands.")
    if unreported:
        lines.append(f"Merges held: {', '.join(unreported)} passed but reported no write targets; "
                     "a human confirms what they wrote before any PR lands.")
    if not auto_merge:
        urls = [r["pr_url"] for r in results
                if r["status"] == "PASS" and r.get("pr_url")]
        lines.append("Awaiting manual merge: " + (", ".join(urls) or "none reported"))
    lines += [
        "",
        "Verifier findings:" if verify and verify["findings"] else "Verifier findings: none.",
    ]
    lines += [f"- {f}" for f in (verify or {}).get("findings", [])]
    lines += ["", "Skill feedback to fold in before the next wave:" if feedback
              else "Skill feedback: none."]
    lines += [f"- {s}" for s in feedback]
    lines += ["", "Per batch:"]
    lines += [f"- {b['id']}: {r['status']}. {r['one_line_summary']}"
              + (f" {r['pr_url']}" if r.get("pr_url") else "")
              for b, r in zip(BATCHES, results)]
    brief_tmp = BRIEF_PATH.with_suffix(".brief.md.tmp")
    brief_tmp.write_text("\n".join(lines) + "\n")
    os.replace(brief_tmp, BRIEF_PATH)


async def main():
    run_id = (RUN_ID_PATH.read_text().strip() if (resume or RUN_ID_PATH.exists())
              else os.environ.get("WAVE_RUN_ID") or f"local-wave{WAVE}-{int(time.time())}")
    if not resume:
        run_id_tmp = RUN_ID_PATH.with_suffix(".run_id.tmp")
        run_id_tmp.write_text(run_id + "\n")
        os.replace(run_id_tmp, RUN_ID_PATH)
    await register_workflow(META)
    check_write_targets(BATCHES)
    log(f"wave {WAVE}: {len(BATCHES)} batches, width {WIDTH}, breaker at {BREAKER}")

    sem = asyncio.Semaphore(WIDTH)
    breaker = Breaker(BREAKER)
    results = await asyncio.gather(*(run_batch(b, sem, breaker) for b in BATCHES))

    reported = Counter(t for r in results for t in r.get("write_targets", []))
    surprises = [t for t, c in reported.items() if c > 1]
    undeclared = {}
    for b, r in zip(BATCHES, results):
        extra = sorted(set(r.get("write_targets", [])) - set(b["write_targets"]))
        if extra:
            undeclared[b["id"]] = extra
    unreported = [b["id"] for b, r in zip(BATCHES, results)
                  if r["status"] == "PASS" and not r.get("write_targets")]
    auto_merge = AUTO_MERGE
    if surprises:
        auto_merge = False
        log(f"WARNING: children reported overlapping write targets after the fact: {surprises}. "
            "Auto-merge is off for this wave; a human decides at wave close.")
    if undeclared:
        auto_merge = False
        log(f"HALT: children wrote outside their declared targets: {undeclared}. "
            "Auto-merge is off for this wave; a human decides at wave close.")
    if unreported:
        auto_merge = False
        log(f"HALT: PASS children did not report write targets: {unreported}. "
            "Auto-merge is off for this wave; a human decides at wave close.")

    passed = [{"batch": b["id"], "units": b["units"], "pr_url": r.get("pr_url", ""),
               "branch": r.get("branch", "")}
              for b, r in zip(BATCHES, results) if r["status"] == "PASS"]
    verify = None
    if passed:
        log(f"verify: {len(passed)} batches to an independent session")
        try:
            verify = await agent(verify_prompt(passed, run_id, MANIFEST_SHA),
                                 phase="verify",
                                 schema=verify_schema(passed, WAVE),
                                 label=f"verify-wave-{WAVE}", vm_mode="shared")  # shared: live recon needs the local Oracle source
        except WorkflowAgentError as e:
            verify = {"wave_verdict": "FAIL", "unit_verdicts": {},
                      "findings": [f"verifier session died: {e}"]}
    else:
        log("verify: skipped, no batch passed")

    verify_problems = (validate_verify(verify, passed, WAVE,
                                       run_id=run_id, manifest_sha=MANIFEST_SHA)
                       if verify is not None else [])
    if verify_problems:
        if not isinstance(verify, dict):
            verify = {"wave_verdict": "FAIL", "unit_verdicts": {}, "findings": []}
        verify["wave_verdict"] = "FAIL"
        if not isinstance(verify.get("findings"), list):
            verify["findings"] = []
        verify["findings"].extend(verify_problems)
    merged_prs = []
    merge_problems = []
    if auto_merge and not verify_problems and verify is not None:
        urls = [batch["pr_url"] for batch in passed
                if verify["unit_verdicts"].get(batch["batch"]) == "PASS" and batch.get("pr_url")]
        if urls:
            log(f"merge: {len(urls)} verified PASS PRs")
            try:
                merged = await agent(merge_prompt(urls, run_id), phase="merge",
                                     schema=merge_schema(), label=f"merge-wave-{WAVE}",
                                     vm_mode="shared")  # shared: uses this machine's gh auth
            except WorkflowAgentError as e:
                merged = {"merged_prs": []}
                merge_problems = [f"merge session died: {e}"]
            else:
                merge_problems = validate_merge(merged, urls)
            if isinstance(merged, dict) and isinstance(merged.get("merged_prs"), list):
                merged_prs = merged["merged_prs"]
            if merge_problems:
                verify["wave_verdict"] = "FAIL"
                if not isinstance(verify.get("findings"), list):
                    verify["findings"] = []
                verify["findings"].extend(merge_problems)
    closed = (breaker.tripped_on is None and not surprises and not undeclared and not unreported
              and not verify_problems and not merge_problems
              and verify is not None and verify["wave_verdict"] == "PASS"
              and all(r["status"] == "PASS" for r in results))
    result_tmp = RESULT_PATH.with_suffix(".result.json.tmp")
    result_tmp.write_text(json.dumps({
        "wave": WAVE, "manifest_sha": MANIFEST_SHA, "width": WIDTH,
        "run_id": run_id,
        "breaker_tripped_on": breaker.tripped_on, "auto_merge": auto_merge,
        "merged_prs": merged_prs,
        "closed": closed,
        "write_target_overlaps": surprises,
        "undeclared_write_targets": undeclared,
        "unreported_write_targets": unreported,
        "batches": [{"id": b["id"], **r} for b, r in zip(BATCHES, results)],
        "verify": verify,
    }, indent=2, sort_keys=True) + "\n")
    os.replace(result_tmp, RESULT_PATH)
    write_brief(results, verify, surprises, undeclared, unreported, auto_merge, merged_prs)
    log(f"wrote {RESULT_PATH} and {BRIEF_PATH}")
    log(f"wave {WAVE} verdict: {verify['wave_verdict'] if verify else 'NO PASSING BATCHES'}")


asyncio.run(main())
