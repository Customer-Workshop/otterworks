"""Ticketing modernization program as one dynamic workflow.

assess (1) -> build (4 at once) -> integrate (1) -> verify (1) -> [fix (per owner) -> verify] x <=2 -> ship (1)

Run from the orchestrator session with run_workflow(script_path=<this file>). The run token,
repo, base branch, fix-round budget and the verification shape are read from run-config.json
next to this file, so every prompt below is deterministic for a given config (resumable).
"""
import asyncio
import json
import os

CONFIG_CANDIDATES = [
    os.environ.get("TICKETING_RUN_CONFIG", ""),
    "/home/ubuntu/repos/otterworks/ticketing/workflow/run-config.json",
]


def load_config():
    for path in CONFIG_CANDIDATES:
        if path and os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise RuntimeError("run-config.json not found; check out the base branch first")


CFG = load_config()
TOKEN = CFG["token"]
REPO = CFG["repo"]
BASE = CFG["base_branch"]
SHAPE = CFG["shape"]
MAX_FIX_ROUNDS = int(CFG["max_fix_rounds"])
REPOS = [REPO]
SLICE = ["orders", "seats", "payments", "confirmations"]
OWNERS = SLICE + ["integration"]
BR_ASSESS = f"tkt/{TOKEN}/assess"
BR_INTEGRATION = f"tkt/{TOKEN}/integration"


def svc_branch(svc):
    return f"tkt/{TOKEN}/svc-{svc}"


def dumps(obj):
    return json.dumps(obj, sort_keys=True, indent=1)


COMMON = f"""WORKFLOW STAGE — you are one child session of the ticketing modernization workflow (run token `{TOKEN}`).
If a playbook is attached to this session, do NOT run its orchestration steps; do only the stage below.

Repository: https://github.com/{REPO} . Base branch: `{BASE}` (NEVER push to `main` or `{BASE}`; never merge anything).
Read `ticketing/CONVENTIONS.md` on your starting branch first and follow it exactly — names, labels, token,
ECR repos, ClusterIP-only, the Kourier routing pattern, metrics. `ticketing/monolith/` is the synthetic Jakarta EE
before-state; `ticketing/scripts/` holds the before-state deploy, reset, status and destroy scripts.
Cluster: EKS `otterworks-dev` in us-east-1 (`aws eks update-kubeconfig --name otterworks-dev --region us-east-1`; if your
default AWS identity is not authorized, export AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY from AWS_DEMO_ACCESS_KEY_ID/
AWS_DEMO_SECRET_ACCESS_KEY). Everything is synthetic: never introduce a real company, person, venue or customer name
into code, data, commits or text. Commit as yourself with clear messages. In your structured output, `session_url` is
this session's own URL. If you are blocked, say so in the structured output rather than claiming success."""

ASSESS_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "branch": {"type": "string"},
        "base_sha": {"type": "string"},
        "note_path": {"type": "string"},
        "deepwiki_used": {"type": "boolean"},
        "contexts": {"type": "array", "items": {"type": "string"}},
        "services": {"type": "array", "items": {"type": "object"}},
        "events": {"type": "array", "items": {"type": "object"}},
        "summary": {"type": "string"},
    },
    "required": ["session_url", "branch", "base_sha", "note_path", "services", "events", "summary"],
}

BUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "service": {"type": "string"},
        "branch": {"type": "string"},
        "commit": {"type": "string"},
        "image": {"type": "string"},
        "unit_tests": {"type": "integer"},
        "contract_tests": {"type": "integer"},
        "tests_passed": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["session_url", "service", "branch", "commit", "image", "tests_passed", "summary"],
}

INTEGRATE_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "branch": {"type": "string"},
        "commit": {"type": "string"},
        "deployed": {"type": "boolean"},
        "before_host": {"type": "string"},
        "after_host": {"type": "string"},
        "grafana_dashboard_url": {"type": "string"},
        "at_rest_replicas": {"type": "string"},
        "reset_seconds": {"type": "integer"},
        "notes": {"type": "string"},
    },
    "required": ["session_url", "branch", "commit", "deployed", "before_host", "after_host", "grafana_dashboard_url", "notes"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "passed": {"type": "boolean"},
        "commit": {"type": "string"},
        "report_path": {"type": "string"},
        "reconciliation": {"type": "object"},
        "measurements": {"type": "object"},
        "captures": {"type": "array", "items": {"type": "string"}},
        "findings": {"type": "array", "items": {"type": "object"}},
        "summary": {"type": "string"},
    },
    "required": ["session_url", "passed", "commit", "report_path", "reconciliation", "measurements", "findings", "summary"],
}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "owner": {"type": "string"},
        "commit": {"type": "string"},
        "redeployed": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["session_url", "owner", "commit", "redeployed", "summary"],
}

SHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "session_url": {"type": "string"},
        "pr_url": {"type": "string"},
        "runbook_path": {"type": "string"},
        "devin_review_commented": {"type": "boolean"},
        "review_summary": {"type": "string"},
    },
    "required": ["session_url", "pr_url", "devin_review_commented", "review_summary"],
}

SHAPE_TEXT = f"""The shape verification checks (variables with these defaults — keep them as variables in the scripts):
- the monolith (one replica, CPU limit {SHAPE['monolith_cpu']}) saturates at the order rate its CPU allows; beyond it p95 latency climbs past a few seconds;
- the services sustain {SHAPE['service_rate_multiplier']}x that rate (peak about {SHAPE['onsale_peak_orders_per_minute']} orders/minute) with p95 < {SHAPE['service_p95_ms']} ms, each service capped at {SHAPE['max_replicas']} replicas;
- the payments consumer pod deleted mid-spike loses nothing: its partitions replay and the idempotency key makes redelivery a no-op (fired = placed = paid = confirmed on the after side);
- every service is back at 0 replicas within {SHAPE['scale_to_zero_seconds']} s after the spike ends."""


def assess_prompt():
    return f"""{COMMON}

STAGE 1 — ASSESS. Start from `{BASE}`. Create branch `{BR_ASSESS}` from it.

Read the monolith in `ticketing/monolith/` (13 session beans, 20 JSPs, 30-table schema in `db/schema.sql`, the `common`
utility package, the nightly settlement timer). Use DeepWiki / the repository Q&A tools your session has for
`{REPO}` to orient yourself, then confirm every claim in the source (DeepWiki may not index this branch; say what it covered).

Write `ticketing/docs/decomposition.md`, the decomposition note:
1. The bounded contexts you found (catalog, inventory/seat allocation, pricing, customer, sales/orders, payment,
   fulfilment/confirmation, settlement, reporting, …) — each with the beans, JSPs and tables that belong to it.
2. Table ownership: all 30 tables, each assigned to exactly one owning context, plus the cross-context joins and
   shared-table writes that make the monolith hard to split (e.g. the single JTA transaction in PurchaseFacadeBean,
   Db/AuditLog in `common`, the reporting and settlement joins).
3. The events between contexts (name, producer, consumers, key, payload fields).
4. The first slice to extract — order placement, seat allocation, payment, confirmation — mapped onto EXACTLY these four
   service dirs: {", ".join(SLICE)} (runtimes per CONVENTIONS.md). For each: tables it takes (and the read-only reference
   data it needs copied/seeded), API endpoints, events published/consumed, how the monolith behavior it must preserve
   is observable (status codes, totals, hold expiry, decline on card 0000, payment timeout), and what stays in the monolith.
   Specify the order-placement outbox and the payment idempotency key.
5. Every claim links to source lines as GitHub permalinks pinned to the base commit:
   `https://github.com/{REPO}/blob/<base_sha>/ticketing/monolith/<path>#L<a>-L<b>` where <base_sha> is
   `git rev-parse origin/{BASE}`. Check a sample of links resolve to the lines you mean.

Also write `ticketing/docs/decomposition.json` with the same `services` and `events` arrays as your structured output.
Push `{BR_ASSESS}` (no PR).

Structured output: `services` = one object per slice service with keys name, dir, runtime, tables (array), reference_tables
(array), publishes (array), consumes (array), api (array of "METHOD /path — meaning"); `events` = objects with name, producer,
consumers, key, payload; `contexts` = context names; `branch`, `base_sha`, `note_path`, `deepwiki_used`, `summary` (3 lines)."""


def build_prompt(assess, svc):
    spec = next((s for s in assess["services"] if str(s.get("dir", s.get("name", ""))).endswith(svc)), None)
    return f"""{COMMON}

STAGE 2 — BUILD the `{svc}` service (one of four built in parallel by separate sessions: {", ".join(SLICE)}).
Start from branch `{assess['branch']}` (it contains the decomposition note `{assess['note_path']}` — the contract).
Create branch `{svc_branch(svc)}` from it and touch ONLY `ticketing/services/{svc}/` so the four branches merge cleanly.

Your service's slice of the note:
{dumps(spec)}
All events in the slice (topic names, keys and payloads are shared contracts — do not rename them):
{dumps(assess['events'])}

Build a Spring Boot 3 / Java 21 / Maven service in `ticketing/services/{svc}/`:
- its own PostgreSQL database (Flyway migrations for the tables it owns; reference data seeded from the same synthetic
  seed as the monolith, `ticketing/monolith/db/seed.sql`, so results are comparable), JDBC or JPA;
- runtime per CONVENTIONS.md: {"a Kafka consumer (KEDA-scaled Deployment, min 0 / max 6) with manual offset commit after the DB commit and a unique idempotency key (order reference) so redelivered records are no-ops" if svc == "payments" else "a request-driven Knative Service (min-scale 0, max-scale 6)"}
  {"; order placement writes the order and an OUTBOX row in one transaction, and a relay publishes outbox rows to Kafka (the relay must drain even when the request path scales to zero — e.g. a small KEDA-scaled relay Deployment using the postgresql scaler on unpublished rows, or equivalent)" if svc == "orders" else ""}
- `GET /actuator/health`, `GET /actuator/prometheus`, `GET /stats` (counts used by reconciliation);
- a `Dockerfile` (multi-stage, non-root, temurin 21 JRE; base images are rate-limited — pull once and reuse);
- `ticketing/services/{svc}/k8s/` manifests for `{TOKEN}-after` rendered with envsubst `${{TOKEN}}`/`${{IMAGE}}` (DB Deployment +
  ClusterIP Service, the workload, ServiceMonitor, NetworkPolicy, Kafka topics it produces as KafkaTopic, KEDA
  ScaledObject if any), following CONVENTIONS.md;
- unit tests, and CONTRACT tests derived from the monolith's behavior on the same seeded data: record the monolith's
  responses for the cases your service takes over (run it with `docker compose up` in `ticketing/monolith`, or call the
  live before state at https://{TOKEN}-before.demo.otterworks.app/api/…) into
  `ticketing/services/{svc}/src/test/resources/contracts/*.json`, and assert your service produces the same outcomes
  (status, totals, seat counts, decline/timeout/expiry behavior) from the same seed. `mvn -B verify` must pass.
Build and push the image `…/otterworks-demo/ticketing/{svc}:{TOKEN}-<shortsha>` to ECR. Do NOT deploy to the cluster —
the integration stage deploys all four together. Push `{svc_branch(svc)}` (no PR).

Structured output: service="{svc}", branch, commit (full sha), image (full URI with tag), unit_tests, contract_tests,
tests_passed, summary (what it owns, its API/events, anything the integrator must know)."""


def integrate_prompt(assess, builds):
    return f"""{COMMON}

STAGE 3 — INTEGRATE AND DEPLOY. The four services were built in parallel on these branches (all based on `{assess['branch']}`):
{dumps(builds)}
Create `{BR_INTEGRATION}` from `{assess['branch']}` and merge the four branches into it (resolve conflicts; each touched only its
own dir). Then write, under `ticketing/`:
- `deploy/before/` — keep/adjust the monolith manifests (one replica, fixed CPU limit) so the before namespace `{TOKEN}-before`
  is part of the same reset;
- `deploy/after/` — the after namespace `{TOKEN}-after`: Namespace/quota/limits/NetworkPolicy, a Strimzi Kafka cluster
  `{TOKEN}-kafka` (KRaft, single ephemeral node pool, sized small), the topics (6 partitions), the four services from their
  `k8s/` dirs, nginx Ingress `{TOKEN}-after.demo.otterworks.app` routing the public API paths to the Knative services via the
  Kourier pattern in CONVENTIONS.md, and an executable `deploy/after/deploy.sh <token>` that applies it all and waits for Ready;
- `load/seed.sh <token>` — deterministic re-seed of both sides from the same synthetic seed;
- `load/onsale.js` + `load/run-onsale.sh <token>` — ONE k6 script run in-cluster as a Job (image `…/ticketing/k6:v1.8.1`)
  that fires the on-sale at both hosts at once through the shared ingress, with ramp/peak/duration as variables, each
  request carrying a unique order key so fired orders can be reconciled; it writes its summary (fired per side, status
  counts, p95) where the verify stage can read it;
- `dashboards/ticketing-onsale.json` + a ConfigMap labelled `grafana_dashboard: "1"` (token in name/labels): top row
  "Before — monolith" (request rate, p50/p95 latency, errors, CPU vs limit, replicas=1), bottom row "After — services"
  (rate, p95 per service, replica count per service stepping 0→6, Kafka consumer lag, outbox backlog, payments pod restarts);
- `scripts/reset.sh` must still rebuild BOTH namespaces and re-seed in one command, and `scripts/destroy.sh` must remove
  everything the after side creates (make `make demo-destroy NS={TOKEN} DRY_RUN=1` list it all; do not run a real destroy).
Deploy to the shared cluster with `ticketing/scripts/reset.sh {TOKEN}` (time it), confirm a purchase works end-to-end on both
hosts, and that the after services sit at 0 replicas at rest. Commit and push `{BR_INTEGRATION}` (no PR).

Structured output: branch, commit, deployed, before_host, after_host, grafana_dashboard_url (https://grafana.otterworks.app/d/…),
at_rest_replicas (the `ticketing/scripts/status.sh {TOKEN}` output, condensed), reset_seconds, notes (anything verify must know)."""


def verify_prompt(integ, attempt, history):
    prior = f"\nPrevious verification rounds and fixes applied since:\n{dumps(history)}\n" if history else ""
    return f"""{COMMON}

STAGE 4 — VERIFY (attempt {attempt}). Check out `{BR_INTEGRATION}` (pull the latest; fixes may have landed). Deployed state:
{dumps({k: integ[k] for k in sorted(integ) if k in ("before_host", "after_host", "grafana_dashboard_url", "at_rest_replicas", "notes")})}
{prior}
{SHAPE_TEXT}

Do, in order, and record timestamps:
1. `ticketing/scripts/reset.sh {TOKEN}` so the run starts from a known seed; record at-rest replica counts.
2. Run the on-sale (`ticketing/load/run-onsale.sh {TOKEN}`) against both namespaces at once.
3. During the spike, once payments has scaled out, delete one payments consumer pod (`kubectl delete pod`) and record the time.
4. After the spike, wait for Kafka consumer lag and the outbox backlog to reach 0; record the drain time. Keep watching until
   every service is at 0 replicas and record how long after the spike that took.
5. Reconcile from the databases and k6 summary: per namespace, orders fired, placed, paid, confirmed/settled, duplicates
   (payments per order > 1), missing (fired-and-accepted but not paid). The after side must read the same number in every column.
6. Capture the Grafana dashboard (both rows, time range covering the run) and the key panels as PNG screenshots in the browser
   (log in with the Grafana admin credentials from the `monitoring/prometheus-grafana` secret if needed) into
   `ticketing/evidence/{TOKEN}/verify-{attempt}/`.
7. Write `ticketing/evidence/{TOKEN}/verify-{attempt}/reconciliation.md` (table + the numbers behind each shape check,
   pass/fail per check, timestamps) and commit it with the captures and the k6 summary to `{BR_INTEGRATION}`
   (`git pull --rebase` before pushing). Leave both namespaces running.

Findings: for every failed check, one finding object {{"owner": one of {OWNERS}, "check": …, "evidence": …, "suggested_fix": …}}.
Structured output: passed (true only if every check passed), commit, report_path, reconciliation (object keyed by namespace),
measurements (monolith_saturation_rpm, services_peak_rpm, services_p95_ms, max_replicas_seen, pod_deleted_at, drain_seconds,
scale_to_zero_seconds), captures (paths), findings, summary."""


def fix_prompt(owner, owner_findings, builds, attempt):
    origin = next((b for b in builds if b.get("service") == owner), None)
    scope = (f"the `{owner}` service (`ticketing/services/{owner}/`), originally built in {origin.get('session_url')} on `{origin.get('branch')}`"
             if origin else "the integration layer (`ticketing/deploy`, `ticketing/load`, `ticketing/dashboards`, `ticketing/scripts`)")
    return f"""{COMMON}

STAGE 5 — FIX (round {attempt}) for {scope}. Verification failed with these findings for you:
{dumps(owner_findings)}
{SHAPE_TEXT}

Check out `{BR_INTEGRATION}` (latest). Fix the root cause in your scope only (other owners may be fixing theirs concurrently);
keep `mvn -B verify` and the contract tests green; rebuild and push the image with a new `{TOKEN}-<shortsha>` tag if code
changed; update the manifests; redeploy just your part to `{TOKEN}-after` and confirm it is healthy and back at rest.
Commit with a message naming the finding, `git pull --rebase`, push `{BR_INTEGRATION}`. Do not run the on-sale or reset.

Structured output: owner="{owner}", commit, redeployed, summary (root cause and fix)."""


def ship_prompt(assess, builds, integ, verifies, fixes, outcome):
    links = {
        "assess": assess["session_url"],
        "build": {b["service"]: b["session_url"] for b in builds},
        "integrate": integ["session_url"],
        "verify": [v["session_url"] for v in verifies],
        "fix": [f"{f['owner']}: {f['session_url']}" for f in fixes],
    }
    last = verifies[-1]
    return f"""{COMMON}

STAGE 6 — SHIP. Outcome of verification: {outcome}. Check out `{BR_INTEGRATION}` (latest).
Session links for every stage of this run:
{dumps(links)}
Final verification: {dumps({k: last[k] for k in ("passed", "report_path", "measurements", "reconciliation", "summary")})}
Integration: {dumps({k: integ[k] for k in ("before_host", "after_host", "grafana_dashboard_url", "at_rest_replicas", "reset_seconds") if k in integ})}

1. Write `ticketing/docs/runbook.md` for a presenter who was not in the loop: preflight (cluster, hosts, Grafana, `make ticketing-status NS={TOKEN}`),
   the one reset command (`make ticketing-reset NS={TOKEN}`) with its measured time, replica counts at rest, the live steps
   (open the workflow run view, the decomposition note beside the bean it came from, the Grafana rows, the pod deletion and drain,
   the reconciliation report, this PR and its Devin Review comment), where each metric lives, the session links above, the
   fallback if the live run misbehaves (the evidence captures), and teardown (`make demo-destroy NS={TOKEN}`). Measured timings only.
2. Open ONE pull request from `{BR_INTEGRATION}` into `{BASE}` (never `main`) titled "Ticketing modernization: first slice extracted ({TOKEN})",
   whose body links the decomposition note, the reconciliation report(s), the Grafana captures, the runbook and every session link above,
   and states the verification outcome honestly. Do not merge it.
3. Wait for the Devin Review bot to comment on the PR (poll up to ~30 minutes). Do not push fixes for its findings; summarize them.

Structured output: pr_url, runbook_path, devin_review_commented, review_summary."""


async def main():
    await register_workflow({
        "name": f"ticketing-modernization-{TOKEN}",
        "description": "Legacy ticketing monolith to event-driven services: assess, build four services at once, integrate and deploy, verify with a killed consumer, fix (<=2 rounds), ship a PR with Devin Review",
        "product": f"{REPO} ticketing/ (run token {TOKEN})",
        "soft_time_limit_minutes": 45,
        "phases": [
            {"title": "assess", "detail": "Decomposition note with source-linked claims", "count": 1, "labels": ["assess"], "soft_time_limit_minutes": 40},
            {"title": "build", "detail": "Four Spring Boot 3 services built at once, one branch each", "count": 4, "labels": [f"build-{s}" for s in SLICE], "soft_time_limit_minutes": 60},
            {"title": "integrate", "detail": "Merge branches, before/after manifests, k6, dashboard, reset/destroy, deploy", "count": 1, "labels": ["integrate"], "soft_time_limit_minutes": 60},
            {"title": "verify", "detail": "On-sale at both namespaces, consumer pod deleted mid-spike, reconciliation + Grafana", "soft_time_limit_minutes": 50},
            {"title": "fix", "detail": "Findings routed to the owning service; at most two rounds", "soft_time_limit_minutes": 45},
            {"title": "ship", "detail": "Runbook + PR with every session link; wait for Devin Review", "count": 1, "labels": ["ship"], "soft_time_limit_minutes": 45},
        ],
    })

    log(f"assess: token={TOKEN} base={BASE}")
    assess = await agent(assess_prompt(), phase="assess", label="assess", schema=ASSESS_SCHEMA, repos=REPOS)
    log(f"assess done: {len(assess['services'])} services, {len(assess['events'])} events on {assess['branch']}")

    async def build(svc):
        try:
            return await agent(build_prompt(assess, svc), phase="build", label=f"build-{svc}", schema=BUILD_SCHEMA, repos=REPOS)
        except WorkflowAgentError as e:
            log(f"build-{svc} failed: {e}")
            return {"service": svc, "branch": "", "session_url": "", "tests_passed": False, "summary": f"FAILED: {e}"}

    builds = await parallel([lambda s=s: build(s) for s in SLICE])
    for b in builds:
        log(f"build-{b['service']}: branch={b.get('branch')} tests_passed={b.get('tests_passed')} image={b.get('image', '')}")
    missing = [b["service"] for b in builds if not b.get("branch")]
    if missing:
        raise RuntimeError(f"build stage produced no branch for {missing}; resume this run after investigating")

    integ = await agent(integrate_prompt(assess, builds), phase="integrate", label="integrate", schema=INTEGRATE_SCHEMA, repos=REPOS)
    log(f"integrate: deployed={integ['deployed']} before={integ['before_host']} after={integ['after_host']}")
    if not integ["deployed"]:
        raise RuntimeError(f"integration did not deploy: {integ['notes']}")

    verifies, fixes, history = [], [], []
    outcome = "not run"
    for attempt in range(1, MAX_FIX_ROUNDS + 2):
        v = await agent(verify_prompt(integ, attempt, history), phase="verify", label=f"verify-{attempt}", schema=VERIFY_SCHEMA, repos=REPOS)
        verifies.append(v)
        log(f"verify-{attempt}: passed={v['passed']} findings={len(v['findings'])} report={v['report_path']}")
        if v["passed"]:
            outcome = f"PASSED on attempt {attempt}"
            break
        if attempt > MAX_FIX_ROUNDS:
            outcome = f"EXHAUSTED: failed after {MAX_FIX_ROUNDS} fix rounds; last findings: {json.dumps(v['findings'], sort_keys=True)}"
            break
        by_owner = {}
        for f in v["findings"]:
            owner = f.get("owner") if f.get("owner") in OWNERS else "integration"
            by_owner.setdefault(owner, []).append(f)
        if not by_owner:
            by_owner["integration"] = [{"check": "verification failed without findings", "evidence": v["summary"]}]
        log(f"fix round {attempt}: owners={sorted(by_owner)}")

        async def fix(owner, fs=None, a=attempt):
            try:
                return await agent(fix_prompt(owner, fs, builds, a), phase="fix", label=f"fix-{owner}-r{a}", schema=FIX_SCHEMA, repos=REPOS)
            except WorkflowAgentError as e:
                return {"owner": owner, "session_url": "", "commit": "", "redeployed": False, "summary": f"FAILED: {e}"}

        round_fixes = await parallel([lambda o=o: fix(o, by_owner[o]) for o in sorted(by_owner)])
        fixes.extend(round_fixes)
        history.append({"verify_attempt": attempt, "findings": v["findings"],
                        "fixes": [{k: f[k] for k in ("owner", "commit", "summary")} for f in round_fixes]})

    log(f"verification outcome: {outcome}")
    ship = await agent(ship_prompt(assess, builds, integ, verifies, fixes, outcome), phase="ship", label="ship", schema=SHIP_SCHEMA, repos=REPOS)
    log(f"ship: pr={ship['pr_url']} devin_review_commented={ship['devin_review_commented']}")
    log("RESULT " + json.dumps({
        "token": TOKEN, "outcome": outcome, "pr_url": ship["pr_url"],
        "sessions": {"assess": assess["session_url"], "build": {b["service"]: b["session_url"] for b in builds},
                     "integrate": integ["session_url"], "verify": [v["session_url"] for v in verifies],
                     "fix": [f["session_url"] for f in fixes], "ship": ship["session_url"]},
        "measurements": verifies[-1]["measurements"], "reconciliation": verifies[-1]["reconciliation"],
    }, sort_keys=True))
    if not verifies[-1]["passed"]:
        raise RuntimeError(outcome)


asyncio.run(main())
