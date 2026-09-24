# Demo run-sheet: dependency verification loop + API self-healing loop

Two runnable demos on the local Docker Compose stack, plus the GitHub/Devin
wiring that makes them event-driven.

| Track | Story | Trigger | Devin does | Proof on screen |
|---|---|---|---|---|
| 1a | A dependency-bump PR is verified, not just built | `pull_request` on a manifest change or bot-authored PR → `renovate-verify.yml` → **deps-verify** automation | checks out the PR, runs `make deps-inventory / deps-tests / deps-gate / deps-transcript`, fixes breakage, comments `✅ Build verified` + evidence | the PR comment |
| 1b | Verified bumps are grouped into one PR | that comment → `group-verified-deps.yml` → **deps-group** automation | enumerates verified PRs, groups by shared version property / module (DeepWiki), builds one combined branch, re-runs the harness, opens ONE combined PR | the combined PR, left for a human to merge |
| 2 | A broken endpoint heals itself | `scripts/api_verify_loop.py` polling the Compose stack; chaos flag flips an endpoint red | gets the failing endpoint, expected-vs-actual and `docker compose logs`; investigates, fixes, opens a PR | poller output goes red → `DEVIN_TRIGGERED` → PR → rebuild → `RECOVERED` |

Everything Devin produces is a PR or a comment. **Devin never merges or approves
its own PRs** — the last click is always a human's.

---

## 0. Prerequisites (both tracks)

### Tools on the laptop

- Docker Desktop / Docker Engine with `docker compose` v2, ~8 GB free RAM for the full stack
- `make`, `curl`, `python3` (3.9+, stdlib only — the poller has no dependencies)
- `gh` CLI logged in to `Cognition-Partner-Workshops` (Track 1 only)
- For running the deps harness by hand (optional, Devin runs it in its own VM): JDK 11 **and** 17, Maven, Gradle 8.6 — see `.agents/skills/dependency-cve-remediation/SKILL.md`

### Secrets and where each one goes

| Variable | Used by | Where to set it | Notes |
|---|---|---|---|
| `DEVIN_API_KEY` | admin-service (`DevinSessionService`), `api_verify_loop.py --trigger devin` | shell env before `make up` / before running the poller | Devin → Settings → API Keys. Service-user key preferred. |
| `DEVIN_ORG_ID` | same | same | `org-…` from the same page |
| `CHAOS_SECRET` | admin-service chaos API (`X-Chaos-Secret` header) | shell env before `make up` | Optional. Unset = chaos API open (dev mode). If set, the admin dashboard cannot send it — use `make chaos` instead. |
| `ALERT_WEBHOOK_SECRET` | admin-service `POST /api/v1/admin/alerts/ingest` (`X-Alert-Secret`) and `--trigger admin` | shell env | Compose default `demo-alert-secret`; the poller uses the same default. |
| `DEVIN_WEBHOOK_SECRET` | GitHub Actions → Devin automation webhooks (`X-Webhook-Secret`) | **GitHub repo secret** | Shared fallback for both new workflows (the SAST workflow already uses it). Per-automation overrides: `DEVIN_DEPS_VERIFY_WEBHOOK_SECRET`, `DEVIN_DEPS_GROUP_WEBHOOK_SECRET`. |
| `DEVIN_DEPS_VERIFY_WEBHOOK_URL` | `renovate-verify.yml` | **GitHub repo variable** | webhook URL of the deps-verify automation (created in §1.2) |
| `DEVIN_DEPS_GROUP_WEBHOOK_URL` | `group-verified-deps.yml` | **GitHub repo variable** | webhook URL of the deps-group automation (created in §1.2) |

```bash
# local shell, once per terminal
export DEVIN_API_KEY=…            # never commit; never paste into a PR
export DEVIN_ORG_ID=org-…
export ALERT_WEBHOOK_SECRET=demo-alert-secret
# export CHAOS_SECRET=…           # leave unset for the dashboard-driven demo

# GitHub (Track 1) — run from the otterworks checkout
gh secret set DEVIN_WEBHOOK_SECRET
gh variable set DEVIN_DEPS_VERIFY_WEBHOOK_URL --body "https://…/api/webhooks/automations/org-…/auto-…"
gh variable set DEVIN_DEPS_GROUP_WEBHOOK_URL  --body "https://…/api/webhooks/automations/org-…/auto-…"
```

### Bring the stack up

```bash
make infra-up          # Postgres, Redis, LocalStack (S3/SQS/DynamoDB), MeiliSearch
make up seed=1         # builds + starts all services, waits for Postgres, seeds demo data
make api-verify        # one pass over every endpoint in scripts/api-verify-endpoints.json
```

Expected after `make api-verify` (first build takes several minutes; re-run until green):

```
2026-09-24T10:00:01Z PASS search-suggest               search-service         HTTP 200     41ms
2026-09-24T10:00:01Z PASS file-upload                  file-service           HTTP 201    118ms
2026-09-24T10:00:01Z PASS documents-list-latency       document-service       HTTP 200     63ms
2026-09-24T10:00:07Z PASS notification-consumer        notification-service   HTTP 200      8ms
2026-09-24T10:00:07Z PASS api-gateway-health           api-gateway            HTTP 200      3ms
… (health checks for auth, file, document, collab, notification, search, admin)
2026-09-24T10:00:07Z SUMMARY    pass=12 fail=0 failed=[]
```

(`notification-consumer` takes ~6 s: it drops a message on the SQS queue and
waits for the consumer before reading the error counter.)

Admin dashboard: <http://localhost:4200> → **Incidents** (chaos panel is at the
top of that page). Web app: <http://localhost:3000>. Admin API: <http://localhost:8089>.

---

## 1. Track 1 — dependency PR → `✅ Build verified` → one combined PR

### 1.1 What exists in the repo after this change

| File | Role |
|---|---|
| `.github/dependabot.yml` | **the detector.** Weekly Dependabot on the four JVM modules + GitHub Actions; minors/patches grouped per module, majors ignored. Mirrors the shape of `uc-api-ehrbase/.github/dependabot.yml`. |
| `.github/workflows/renovate-verify.yml` | `pull_request [opened, synchronize]` on manifest paths **or** bot author → skips `devin-ai-integration[bot]` → counts Devin attempts (`MAX_FIX_ATTEMPTS: 2`) → POSTs to the deps-verify webhook, or opens an escalation issue when attempts are exhausted. Same structure as `sast-auto-remediate.yml`. |
| `.workshop/playbooks/dependency-bump-verify.devin.md` | prompt/playbook for the deps-verify automation |
| `.github/workflows/group-verified-deps.yml` | `issue_comment [created]` → only Devin's comments containing `✅ Build verified` on an open, non-Devin PR → enumerates every open PR with that marker → POSTs to the deps-group webhook |
| `.workshop/playbooks/dependency-bump-group.devin.md` | prompt/playbook for the deps-group automation; includes the coordinator-worker fan-out section (the 65-repo story) |

**Gap, stated plainly: there is no `renovate.json` in otterworks today.** Dependabot is
the detector (config above). The workflow accepts both bots (`dependabot[bot]`,
`renovate[bot]`) and also fires on any human PR that touches a manifest, so the
demo does not depend on waiting for the weekly schedule.

**Second gap: the golden `main` is intentionally vulnerable.** `report-service`,
`notification-service` and (transitively) `legacy-portal` pin `commons-text` 1.9
(CVE-2022-42889, fixed in 1.10.0). `make deps-gate` is red on `main` by design.
The gate is estate-wide, so the verify playbook judges it per module against the
merge-base: the module a PR bumps must drop out of the `GATE FAILED` list, and the
other lines must be unchanged (`pre-existing on main, unchanged; <module> now clean`).
Only the combined PR that bumps the last consumer turns the gate fully green. The
best demo PR is therefore the real bump: `commons-text 1.9 → 1.10.0` in one module,
with the grouping step assembling the rest.

### 1.2 One-time Devin setup (≈10 min, before the audience arrives)

1. Devin → **Settings → Playbooks → Create**. Paste
   `.workshop/playbooks/dependency-bump-verify.devin.md` as `dependency-bump-verify`.
   Repeat for `dependency-bump-group.devin.md` as `dependency-bump-group`.
2. Devin → **Automations → New → Webhook trigger**. Name it `deps-verify`,
   repository `Cognition-Partner-Workshops/otterworks`, prompt = the verify playbook
   text. Copy its webhook URL + secret → `DEVIN_DEPS_VERIFY_WEBHOOK_URL` variable,
   `DEVIN_WEBHOOK_SECRET` secret (or `DEVIN_DEPS_VERIFY_WEBHOOK_SECRET`).
3. Same again: `deps-group`, prompt = the group playbook → `DEVIN_DEPS_GROUP_WEBHOOK_URL`.
4. Enable **DeepWiki** for the repo (Devin → DeepWiki → index
   `Cognition-Partner-Workshops/otterworks`) so the grouping session can ask about
   module/dependency structure.
5. Check the Devin GitHub app is installed on the repo with PR + issue write
   (it is — the SAST loop already comments and opens PRs).

### 1.3 Live sequence

**Step 1 — open the dependency PR (2 min).** Either wait for Dependabot (weekly)
or hand-open the same PR Dependabot would; the workflow fires on the manifest path
either way:

```bash
git checkout -b deps/commons-text-1.10.0 origin/main
sed -i 's#<commons-text.version>1.9</commons-text.version>#<commons-text.version>1.10.0</commons-text.version>#' services/report-service/pom.xml
git commit -am "build(deps): bump org.apache.commons:commons-text from 1.9 to 1.10.0 in /services/report-service"
git push -u origin deps/commons-text-1.10.0
gh pr create --fill --label dependencies
```

For a second PR to group later (open it right after — the grouping PR is the payoff):

```bash
git checkout -b deps/notification-commons-text-1.10.0 origin/main
sed -i 's/commonsTextVersion = "1.9"/commonsTextVersion = "1.10.0"/' services/notification-service/build.gradle.kts
git commit -am "build(deps): bump org.apache.commons:commons-text from 1.9 to 1.10.0 in /services/notification-service"
git push -u origin deps/notification-commons-text-1.10.0
gh pr create --fill --label dependencies
```


*Expected on screen:* PR → **Checks** → `Dependency Bump Verification` runs
(~20 s). Its summary shows the changed manifests, `attempt 0/2`, and
`Devin automation webhook triggered successfully (HTTP 200)`. In Devin →
Automations → deps-verify → **Runs**, a new session appears with the PR number
in its title.

**Step 2 — watch Devin verify (10–20 min, run in the background).** Open the
session. Narrate what it is doing against the playbook: `gh pr checkout`,
`make deps-inventory` (blast-radius table), `make deps-tests MODULE=report-service`,
`make deps-gate`, `make deps-transcript MODULE=report-service`.

*Expected on screen:* one PR comment whose first line is exactly
`✅ Build verified`, followed by evidence lines like:

```
make deps-inventory              exit 0   4 modules measured, 0 unmeasured
make deps-tests MODULE=report-service   exit 0   "TESTS PASSED: 1 modules." (tests=N failures=0 …)
make deps-gate                   exit 1   "GATE FAILED: CVE-2022-42889 still reachable:" notification-service, legacy-portal — pre-existing on main, untouched by this PR; report-service now clean
make deps-transcript MODULE=report-service   exit 0   "TRANSCRIPT PASSED: N cases across 1 modules"
```

If the bump broke compilation (the javax→jakarta story), Devin pushes a fix
commit to the PR branch first; each push re-fires the workflow, which counts it
(`attempt 1/2`). After `MAX_FIX_ATTEMPTS` the workflow opens
`[Deps] Unverified dependency bump on PR #N` instead of calling Devin again —
show the escalation path from `sast-auto-remediate.yml` if asked.

**Step 3 — the grouping automation fires by itself (0 clicks).** The
`✅ Build verified` comment triggers `Group Verified Dependency PRs`.

*Expected on screen:* the workflow run's summary lists every open PR with the
marker, e.g. `#41 report-service commons-text 1.10.0`, `#42 notification-service
commons-text 1.10.0`, then `Devin grouping automation triggered`. A deps-group
session starts.

**Step 4 — watch Devin group (10–20 min).** The session re-derives the verified
set itself (it never trusts the webhook list), asks DeepWiki how the modules
share dependencies, applies *shared version property → one PR*, creates
`deps/combined-<date>`, cherry-picks both bumps, and re-runs the harness
**without** `MODULE=`.

*Expected on screen:* ONE new PR titled like
`deps: combine 2 verified bumps (commons-text 1.10.0 ×2)` with: a grouping table
and the *why* per group; one line per included PR linking to its
`✅ Build verified` comment; the combined evidence — here `make deps-gate` now
reads `GATE FAILED … legacy-portal` only (still pre-existing, transitive via
`commons-configuration2`); `Closes #41, closes #42`; and the closing line
*left open for a human to review and merge; Devin does not merge its own PRs.*
Each original PR gets a one-line `Grouped into <url>` comment.

**Step 5 — the human merge (your click).** Say it out loud: nothing merged
itself. For this demo repo, **do not actually merge** — `main` is the golden
app and keeps the vulnerable pin so the lab repeats (`AGENTS.md`). Close the
PRs after the demo.

### 1.4 Copy-paste prompts (manual fallback if a webhook is not wired)

Start a Devin session by hand and paste, replacing the placeholders:

```
!dependency-bump-verify
Repository: Cognition-Partner-Workshops/otterworks
PR: #<pr_number>  branch: <branch>  head_sha: <sha>
changed_manifests: services/report-service/pom.xml
dependency_summary: org.apache.commons:commons-text 1.9 -> 1.10.0
attempt: 0 of 2
```

```
!dependency-bump-group
Repository: Cognition-Partner-Workshops/otterworks
Triggered by comment on PR #<pr_number>. Enumerate every open PR whose latest devin-ai-integration[bot] comment starts with "✅ Build verified", group them, build one combined branch, re-run make deps-inventory/deps-tests/deps-gate/deps-transcript, and open ONE combined PR. Do not merge or approve.
```

### 1.5 Scale story — coordinator/worker fan-out (talk track, 2 min)

Section *Scale: coordinator-worker fan-out* of `dependency-bump-group.devin.md`
is the script. A single parent session lists repos in the org, finds open
dependency PRs that are unverified or stale (`✅ Build verified` older than the
head commit), and creates **one child session per repo** running the verify
playbook (Devin API `POST /v3/organizations/{org}/sessions`, or the
`managing-child-sessions` skill). Children report back with the PR comment; the
parent re-runs the grouping playbook per repo. 65 repos is 65 children with the
same prompt and a different `repository` field — the playbooks do not change.

---

## 2. Track 2 — API poller → Devin session off the error logs → PR → green

### 2.1 What exists in the repo after this change

| File | Role |
|---|---|
| `scripts/api_verify_loop.py` | the loop. Stdlib Python. `HealthChecker`'s HTTP semantics (short timeouts, per-endpoint status/latency/message) + `ChaosProbeService`'s fire-sleep-repeat loop, run from the host so it can call `docker compose logs`. |
| `scripts/api-verify-endpoints.json` | configurable endpoint set: status + JSON body/type assertions, latency ceilings, metric deltas, the four chaos-scenario probes and all `/health` endpoints |
| `Makefile` targets `api-verify`, `api-verify-loop`, `api-verify-dry-run`, `chaos`, `chaos-reset` | wrappers (see `make help`) |

How the loop closes: every poll emits one structured line per endpoint
(`PASS`/`FAIL`, plus JSON with `--json` or `--report file.jsonl`). After
`--fail-threshold` consecutive red polls for a service (default 2) it captures
`docker compose logs --tail 200 <service>`, writes the prompt it will send to
`.api-verify-prompts/<service>-attempt<N>.md`, and triggers Devin one of three ways:

| `--trigger` | Path | When to use |
|---|---|---|
| `devin` (default) | Devin API `POST /v3/organizations/$DEVIN_ORG_ID/sessions`, then polls `GET …/sessions/{id}` and prints status + PR URL as they appear | the direct demo |
| `admin` | Grafana-shaped alert to admin-service `POST /api/v1/admin/alerts/ingest` → `Incident` → `DevinSessionService.create_session`; on recovery a `resolved` alert pinned with `labels.incident_id` closes only the incident the loop opened | show the existing alert→incident→Devin path and the Incidents page |
| `webhook` | `POST $DEVIN_WEBHOOK_URL` with `X-Webhook-Secret` and the same payload shape as the GitHub workflows | when the audience has already seen automations |
| `none` | dry run: prompt file only | rehearsal without spending a session |

`MAX_FIX_ATTEMPTS` (env, default 2) caps sessions per service. A session that
ends (`finished`/`stopped`/`expired`/`blocked`) without a PR counts as a failed
attempt (`attempt_failed` event) and the next red poll starts another; past the
cap the loop prints `ESCALATED` and stops calling Devin. Recovery = two
consecutive green polls (`--recover-threshold`) → `RECOVERED … loop closed`;
`--until-green` exits 0 at that point.

The endpoints file is the only thing that decides where the loop sends requests,
so hosts are allowlisted: `localhost`/`127.0.0.1`/`::1` by default, overridable
with `defaults.allowed_hosts` in the file or `API_VERIFY_ALLOWED_HOSTS=a,b`. An
off-list host fails at startup (exit 2) before any request is made.

### 2.2 Fault injection — the four scenarios

Chaos flags are Redis keys the services read (`chaos:<service>:<scenario>`, 10-minute TTL).
**Do not use `scripts/inject-bug.sh`** — that is the Kubernetes path (`kubectl exec`).

| Service | Scenario | What breaks | Poller assertion that goes red |
|---|---|---|---|
| `search-service` | `suggest_500` | `GET /api/v1/search/suggest` raises `KeyError: '_rankingScore'` → HTTP 500 | `search-suggest`: status 200, `suggestions` is a list |
| `file-service` | `upload_s3_error` | `POST /api/v1/files/upload` fails on S3 put → 5xx | `file-upload`: status 201, `file.id` present |
| `document-service` | `slow_queries` | list documents sleeps → seconds-long responses | `documents-list`: `max_latency_ms` |
| `notification-service` | `consumer_strict_schema` | SQS consumer rejects epoch-int timestamps → processing errors | `notification-consumer`: `notifications_processing_errors_total` delta must be 0 |

Inject from the dashboard: <http://localhost:4200/incidents> → **Demo Controls**
→ click the scenario card → the badge shows `1 active`. Or from the shell:

```bash
make chaos SERVICE=search-service SCENARIO=suggest_500      # CHAOS_SECRET=… if you set one
make chaos-reset                                            # clears all flags, resolves incidents
```

### 2.3 Live sequence (search-service / suggest_500 as the headline)

**Step 1 — show green (30 s).** Terminal 1:

```bash
make api-verify
```
*Expected:* every line `PASS`, `SUMMARY pass=12 fail=0`, exit 0.

**Step 2 — start the loop (Terminal 1, leave it running).**

```bash
make api-verify-loop ONLY=search-service            # TRIGGER=devin by default
# or the incident path:  make api-verify-loop ONLY=search-service TRIGGER=admin
```
*Expected:* a `PASS search-suggest …` line every 5 s.

**Step 3 — break it (Terminal 2 or the dashboard).**

```bash
make chaos SERVICE=search-service SCENARIO=suggest_500
```
(Inject from the shell, not the dashboard, if you want to keep Terminal 1 in
focus. The Demo Controls page only tracks flags it set itself: a shell-injected
flag does not show an active badge, and a badge set from the UI stays lit after
`make chaos-reset` until you click **Reset All**. Existing UI behaviour, not the
poller.)

*Expected in Terminal 1, within ~10 s:*

```
… FAIL search-suggest  search-service  HTTP 500  12ms  status: expected 200, got 500; body: expected JSON, got '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>…'
… FAIL search-suggest  …
… LOGS_CAPTURED service=search-service lines=200 error_lines=32
… DEVIN_TRIGGERED service=search-service mode=devin attempt=1 max_attempts=2 session_id=devin-… url=https://…/sessions/…
```

Open `.api-verify-prompts/search-service-attempt1.md` on the projector — this is
exactly what Devin received: repo, affected Compose service, the failing
endpoint with expected vs actual, the response body (Flask's HTML 500 page —
the `KeyError: '_rankingScore'` is in the log lines, not the body), the error
lines from the container log, the full log tail, and the rebuild command
`docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build search-service`.

If you used `TRIGGER=admin`, also open <http://localhost:4200/incidents>: a new
incident for `search-service` with the Devin session link, mirrored from
`DevinSessionService`. (`demo-platform/otter-projects/docs/api.md`
`POST /api/devin/poll` is the same status-mirroring pattern; the poller does it
inline with `SESSION … status=running`.)

**Step 4 — watch Devin (5–15 min).** The session reads
`services/search-service/app/…`, finds the suggest handler's `_rankingScore`
access, makes it tolerate a missing score (keeping the chaos flag — the flag is
how the fault reproduces), adds a test, opens a PR against `main`.

*Expected in Terminal 1:* `SESSION service=search-service status=running url=…`,
then `SESSION … pr_url=https://github.com/Cognition-Partner-Workshops/otterworks/pull/N
rebuild=docker compose … up -d --build search-service` (only with `TRIGGER=devin`;
the `admin` path shows the session on the Incidents page instead).

**Step 5 — rebuild with the fix (Terminal 2).**

```bash
gh pr checkout N
docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build search-service
```

*Expected in Terminal 1, within ~15 s:*

```
… PASS search-suggest  search-service  HTTP 200  38ms
… PASS search-suggest  …
… RECOVERED  service=search-service attempts=1 pr_url=https://…/pull/N message=endpoint(s) green again; loop closed
… DONE       message=all endpoints green after fix
```

Exit code 0. Chaos flag still set → the fix is proven against the fault, not
against a reset. Then:

```bash
make chaos-reset
git checkout main            # golden app stays untouched; leave the PR for a human
```

**Step 6 — the max-attempts guard (optional, 2 min).** One Devin session per
service is allowed per red→green→red cycle, up to `MAX_FIX_ATTEMPTS`. With the
cap at 1 and no real session:

```bash
MAX_FIX_ATTEMPTS=1 python3 scripts/api_verify_loop.py --trigger none --only file-service --prompt-dir .api-verify-prompts
```

`make chaos SERVICE=file-service SCENARIO=upload_s3_error` →
`DEVIN_TRIGGERED … attempt=1 max_attempts=1 dry_run=True`; `make chaos-reset` →
`RECOVERED`; inject again → `ESCALATED service=file-service attempts=1
max_attempts=1 message=fix attempts exhausted; needs a human` and no further
prompt is written. Same rule as `renovate-verify.yml`'s attempt counter.

### 2.4 Rehearsal without a Devin session

```bash
make api-verify-dry-run ONLY=search-service POLLS=4      # TRIGGER=none, 4 polls
cat .api-verify-prompts/search-service-attempt1.md
```

### 2.5 Copy-paste prompt (manual fallback)

The file under `.api-verify-prompts/` *is* the prompt. If you need to start a
session by hand, paste that file. Its shape:

```
An API verification loop (scripts/api_verify_loop.py) has been polling the Docker Compose stack
of Cognition-Partner-Workshops/otterworks and one service is now failing its assertions.

Affected service: `search-service` (services/search-service/)
Failing endpoint(s), expected vs actual:
- search-suggest: HTTP 500, 12ms — status: expected 200, got 500; body: expected JSON, got '<!doctype html>…'
  body: <!doctype html><html lang=en><title>500 Internal Server Error</title>…
Recent error lines from `docker compose logs search-service`:
  KeyError: '_rankingScore'  …
Full log tail: …

Investigate the code path that produces the wrong status/body, fix it (keep the chaos flag —
it is how the fault reproduces), add/update a test that fails before and passes after, open a PR
against main. Do not merge or approve. Do not touch the planted Rails logging bug in
services/admin-service/config/environments/production.rb. Rebuild locally with:
docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build search-service
This is fix attempt 1 of 2.
```

---

## 3. Demo gaps — say these out loud

1. **No `renovate.json` exists in otterworks today.** The detector is
   `.github/dependabot.yml` (added here, modelled on uc-api-ehrbase). The
   workflows accept Renovate too; swapping detectors is a config change only.
2. **The grouping automation and the API poller are new in this change.** They
   have been exercised against a mock stack (poller) and by reading the
   workflows' `if:` conditions and payloads (workflows). The first live run of
   each Devin automation is the demo itself — rehearse §1.3 once beforehand.
3. **Devin does not self-merge.** Every artifact is a PR or comment. The
   combined dependency PR and the API-fix PR both stop at "ready for human
   review". In this repo they also should **not** be merged afterwards: `main`
   is the golden app and deliberately keeps the `commons-text` 1.9 pin and the
   planted admin-service bug.
4. **The gate on `main` is red on purpose** (CVE-2022-42889). The gate scans
   every module, so the verify playbook judges it per module against the
   merge-base ("bumped module now clean, remaining paths pre-existing and
   unchanged" vs "made worse"); it turns fully green only once every
   `commons-text` consumer is bumped, normally in the combined PR.
5. **Webhook URLs and secrets are per-Devin-org.** `DEVIN_DEPS_VERIFY_WEBHOOK_URL`
   and `DEVIN_DEPS_GROUP_WEBHOOK_URL` are GitHub variables that must be set for
   the target org (§0); an unset URL fails the workflow with a clear `::error::`.
6. **Running the deps harness locally needs two JDKs.** In the demo, Devin runs
   it in its own VM; only the poller and chaos calls run on the laptop.

## 4. Reset between runs

```bash
make chaos-reset
rm -rf .api-verify-prompts .api-verify-events.jsonl      # gitignored
gh pr close <n> --delete-branch                            # the demo PRs; never merge into main
make down && make infra-down                               # optional full stop
```
