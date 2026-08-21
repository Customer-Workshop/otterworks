# Legacy Billing Estate & Stored-Procedure Migration / Parity

Internal engineering documentation for the `procs/` parity harness, the legacy
billing estate it records (`services/legacy-billing/`), the extraction target it
grades (`services/billing-service/`), and the adjacent legacy batch chain
(`etl/`).

Everything below was verified by reading the sources on `main` at the time of
writing, and by running the cheap commands noted in
[§5 Operational runbook](#5-operational-runbook). Statements that are inference
rather than observed behavior are marked **(inference)**.

---

## 1. Purpose & scope

### What this subsystem does

1. **Holds the legacy before-state.** `services/legacy-billing/` is a
   database-centric billing application: a thin Flask layer
   (`services/legacy-billing/app/app.py`) binds request values and calls
   PostgreSQL entrypoints; all billing behavior lives in SQL/PL-pgSQL under
   the `billing` schema (`services/legacy-billing/db/procs/*.sql`).
2. **Captures that behavior as immutable evidence.** `procs/harness/record.py`
   resets the legacy database to the checked-in schema + procedures + seed,
   invokes one declared entrypoint per scenario, and writes a JSON transcript
   under `procs/transcripts/<module>/<SCENARIO-ID>.json`.
3. **Gates human sign-off on the extracted rules.**
   `procs/harness/rules_gate.py` validates `procs/rules/<module>.rules.yaml`:
   every rule must have an approved decision, cite scenarios, point at a line
   range inside its own procedure file, and be claimed by a
   `@pytest.mark.rule("<id>")` marker in the target's test suite.
4. **Grades the extracted service against the transcripts.**
   `procs/harness/replay.py` replays each transcript against the HTTP contract
   in `procs/routes.yaml`, comparing recorded business fields and state probes
   with the target's JSON response, and writes `procs/reports/parity.{md,json}`.
5. **Invalidates stale evidence.** `procs/harness/fingerprints.py` hashes the
   procedure sources and the fixture (schema + seed); a mismatch between those
   digests and the ones stored in the transcripts hard-fails both recording and
   replay.

`etl/` is a second, independent legacy artifact in scope for this document: the
cron-driven Python batch chain plus its documented Airflow migration target
(`etl/ETL_UPGRADE_GUIDE.md`). It is *not* wired into the parity harness — there
is no reference to `billing` anywhere under `etl/`, no Makefile target, and no
Compose service for it (verified by grep over `etl/`, `Makefile`, and
`docker-compose*.yml`).

### What this subsystem is NOT

- **Not a deployed service path.** `docker-compose.procs.yml` is a standalone
  local stack, explicitly separate from the Helm/EKS deployment path
  (comment at the top of the file). Neither `legacy-billing` nor
  `billing-service` appears in the main `docker-compose.yml` app stack.
- **Not authenticated.** Neither the legacy Flask app nor the extracted FastAPI
  service performs authentication or tenant scoping; `services/billing-service/README.md`
  states an extraction that ships for real must add both at the edge.
- **Not a full extraction.** Only the `plans` module is `status: extracted` in
  `procs/routes.yaml`. `rating`, `invoicing`, and `dunning` are `pending`: they
  have recorded transcripts but no target endpoints, no rule ledger, and are
  reported as `SKIP` by replay — never as a pass.
- **Not the Oracle billing estate.** `.agents/skills/oracle-billing-estate`
  documents `services/legacy-billing/db/oracle/` and `oracle-billing-*` Make
  targets that exist only on the `tech-partnerships` branch. They are absent on
  `main` (verified: no `services/legacy-billing/db/oracle/` directory, no
  `oracle-billing-*` target in `Makefile`).
- **Not the polyglot CUSTBILL batch chain.** `.agents/skills/legacy-etl-demo`
  documents `etl/legacy-extra/` (ksh/Perl/SFTP). That directory does not exist
  on `main`; only the five Python cron scripts under `etl/scripts/` do.
- **Not a general test harness.** The harness grades *semantic* field and probe
  equality for declared entrypoints only. It does not test the legacy Flask
  HTTP layer, does not diff SQL, and does not measure coverage of unrecorded
  procedure branches.

---

## 2. Component map

| Path | Language / runtime | Entrypoint | One-liner |
|---|---|---|---|
| `procs/harness/record.py` | Python 3.12 (`psycopg`, `pyyaml`) | `procs/harness/record.py` (`main()`) | Resets the legacy DB per scenario, calls the entrypoint, writes immutable transcripts. |
| `procs/harness/replay.py` | Python 3.12 (stdlib `http.client`, `pyyaml`) | `procs/harness/replay.py` (`main()`) | Replays transcripts against the target HTTP contract and writes the parity report. |
| `procs/harness/rules_gate.py` | Python 3.12 (`pyyaml`) | `procs/harness/rules_gate.py` (`main()`) | Validates the human-approved rule ledger for a module (or all modules). |
| `procs/harness/fingerprints.py` | Python 3.12 (stdlib) | library (`source_sha()`, `fixture_sha()`) | SHA-256 digests over `db/procs/*.sql` and over `schema.sql` + `seed.sql`. |
| `procs/harness/ledger.py` | Python 3.12 (`pyyaml`) | library (`scenario_rule_map()`) | Builds scenario → rule-id map from `procs/rules/*.rules.yaml`. |
| `procs/harness/status.py` | Python 3.12 (stdlib) | library (`status_for()`) | Module status constants: `pending` / `extracted`; missing module ⇒ `pending`. |
| `procs/harness/list.py` | Python 3.12 (`pyyaml`) | `procs/harness/list.py` (`main()`) | Prints module status, scenario counts, and rule claims. |
| `procs/harness/tests/` | pytest 8 | `pytest procs/harness/tests` | 37 unit tests over grading, immutability, gate, and scenario hygiene. |
| `procs/scenarios/<module>/*.yaml` | YAML (data) | — | 24 declarative scenarios (plans 5, rating 8, invoicing 6, dunning 5). |
| `procs/transcripts/` | JSON (data) | `procs/transcripts/index.json` | Immutable recordings + `SOURCE_SHA` / `FIXTURE_SHA` fingerprint files. |
| `procs/rules/plans.rules.yaml` | YAML (data) | — | The only rule ledger on `main`: `PLANS-001`…`PLANS-004`, all approved. |
| `procs/routes.yaml` | YAML (data) | — | Module status + legacy-entrypoint → HTTP-endpoint parity contract. |
| `services/legacy-billing/app/` | Python 3.12, Flask + gunicorn | `services/legacy-billing/app/app.py` (`app`) | Thin HTTP/Jinja layer over the `billing` schema; port 8096. |
| `services/legacy-billing/db/` | PostgreSQL 16 SQL / PL-pgSQL | `schema.sql`, `procs/*.sql`, `seed.sql` | 11 tables, 12 entrypoints across 4 modules, deterministic seed (9 tenants, 3 plans). |
| `services/billing-service/` | Python 3.12, FastAPI + uvicorn (`uv`) | `services/billing-service/app/main.py` (`app`) | Extraction target for `plans`; owns the `billing_svc` schema; port 8097. |
| `frontend/client-app/src/features/billing/` | TypeScript / React (Vite) | `frontend/client-app/src/App.tsx` (route registration) | Local-only fixture UI that talks to the target through the `/billing-api` dev proxy. |
| `etl/scripts/*.py` | Python 3 (`boto3` 1.26, `pandas` 1.3.5, `psycopg2` 2.9.3) | `etl/run.sh <script>` | Five cron batch jobs (analytics, audit archive, search reindex, storage cleanup, user activity). |
| `etl/crontab`, `etl/run.sh`, `etl/config.ini` | cron / bash / INI | `/opt/etl/run.sh` | Schedule, runner shim, and plaintext configuration for the batch chain. |
| `etl/ETL_UPGRADE_GUIDE.md` | Markdown | — | Documented cron → Airflow 2.8 target state and script-to-DAG mapping. |
| `docker-compose.procs.yml` | Compose | `docker compose -f docker-compose.procs.yml` | 4 services: legacy app + legacy Postgres, target app + target Postgres. |
| `Makefile` (`procs-*` targets) | GNU Make / bash | `make procs-<verb> NS=<ns>` | Namespace port derivation and the driver for every harness command. |
| `.github/workflows/procs-parity.yml` | GitHub Actions | — | Lint, unit tests, client tests, then `procs-up` → `rules-gate ALL=1` → `procs-parity` on `NS=ci`. |

---

## 3. Architecture & data/control flow

### 3.1 The two loops

There are two distinct executions that share one artifact (the transcript):

- **Record** talks *only* to the legacy PostgreSQL database (not to the Flask
  app). `record.py` connects with psycopg and calls `SELECT * FROM <fn>(…)` or
  `CALL <proc>(…)` directly.
- **Replay** talks *only* to the extracted service over HTTP. It never touches
  the legacy database; the transcript is the sole representation of legacy
  behavior.

```mermaid
flowchart TB
  subgraph Legacy["Legacy estate (docker-compose.procs.yml)"]
    LDB[("legacy-billing-db<br/>postgres:16, schema billing<br/>host 55432+offset")]
    LAPP["legacy-billing<br/>Flask/gunicorn :8096<br/>app/app.py"]
    LAPP -->|SELECT/CALL| LDB
  end

  subgraph Sources["Checked-in SQL"]
    SCHEMA["db/schema.sql"]
    PROCS["db/procs/{plans,rating,invoicing,dunning}.sql"]
    SEED["db/seed.sql"]
  end

  SCEN["procs/scenarios/&lt;module&gt;/*.yaml"]
  REC["procs/harness/record.py"]
  TR[("procs/transcripts/&lt;module&gt;/*.json<br/>+ index.json, SOURCE_SHA, FIXTURE_SHA")]
  LEDGER["procs/rules/&lt;module&gt;.rules.yaml"]
  GATE["procs/harness/rules_gate.py"]
  MARKERS["services/billing-service/tests<br/>@pytest.mark.rule(...)"]
  ROUTES["procs/routes.yaml"]
  REP["procs/harness/replay.py"]

  subgraph Target["Extraction target"]
    TAPP["billing-service<br/>FastAPI/uvicorn :8097<br/>app/main.py"]
    TDB[("billing-service-db<br/>schema billing_svc<br/>host 56432+offset")]
    TAPP -->|psycopg| TDB
  end

  Sources -->|DROP SCHEMA billing CASCADE + replay DDL per scenario| LDB
  SCEN --> REC
  REC -->|"psycopg: SELECT * FROM fn(...) / CALL proc(...)"| LDB
  PROCS -.->|source_sha| REC
  SCHEMA -.->|fixture_sha| REC
  SEED -.-> REC
  REC --> TR
  LEDGER --> GATE
  MARKERS --> GATE
  SCEN --> GATE
  GATE -->|"must exit 0 for extracted modules"| REP
  TR --> REP
  ROUTES --> REP
  REP -->|"POST /internal/reset, then method+path per contract"| TAPP
  REP --> RPT["procs/reports/parity.{md,json}<br/>(gitignored; CI artifact)"]
```

### 3.2 Record — one scenario, end to end

`procs/harness/record.py`:

1. `load_scenarios(module)` reads `procs/scenarios/<module>/*.yaml` (all modules
   when `--module` is omitted).
2. `source_sha()` digests `services/legacy-billing/db/procs/*.sql`;
   `fixture_sha()` digests `schema.sql` + `seed.sql`
   (`procs/harness/fingerprints.py`; both digests mix the relative path and the
   file bytes, NUL-separated, in sorted order).
3. `check_immutability()` refuses to overwrite existing transcripts — see
   [§3.5](#35-immutability-and-fingerprints).
4. `connection()` connects using `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` /
   `DB_PASSWORD` (defaults `localhost:55432`, `billing_$NS`, `billing`/`billing`).
   A `psycopg.Error` here exits `3` (`STACK_UNREACHABLE`).
5. Per scenario: `reset_database()` runs `DROP SCHEMA IF EXISTS billing CASCADE`
   and re-executes the six files in `DB_FILES` (schema, four procedure files,
   seed), then `run_scenario()`:
   - binds `inputs` through `typed()` (`uuid` / `date` / `integer` / `decimal` /
     `boolean`, otherwise passthrough) positionally, in file order;
   - `kind: function` ⇒ `SELECT * FROM <schema>.<fn>(%s, …)`, rows kept;
     `kind: procedure` ⇒ `CALL <schema>.<proc>(%s, …)`, no rows;
   - optional `after_sql` runs next (used by `procs/scenarios/dunning/005.yaml`
     to invoke the same procedure a second time and prove idempotence);
   - optional `capture_query` replaces the result rows with an explicit SELECT —
     this is how side-effecting procedures are observed;
   - `fields` are projected by `capture_fields()`: scalar, `first`/`last`,
     `collect: true` (list of one column) or `collect_rows: true` (list of typed
     row objects);
   - `probes` each run a stable SQL query; `collect_rows: true` stores all rows,
     otherwise the first column of the first row (or `null` for no rows).
   - Any exception rolls back and exits `4` (`SCENARIO_FAILED`).
6. `normalized()` canonicalizes values before they are written: decimals are
   quantized to 2 dp `ROUND_HALF_UP` when `type: decimal`, other `Decimal`s
   become plain strings, `datetime` is converted to UTC and rendered
   `…isoformat(timespec="seconds")` with `+00:00` → `Z`, `date` → ISO, `UUID` →
   string, dicts are key-sorted.
7. Rules are attached from the ledger (`ledger.scenario_rule_map()`), the
   `--rerecord-reason` (if any) is stamped on each record, and
   `write_transcripts()` writes each transcript, merges `index.json` by
   `(module, scenario)`, and rewrites `SOURCE_SHA` / `FIXTURE_SHA`.
   An empty record set returns before touching the index or fingerprints.

Transcript shape (real example, `procs/transcripts/plans/PLANS-004.json`,
trimmed):

```json
{
  "business_fields": { "subscriptions": [ { "ends_on": "2026-02-28", "plan_id": "1000…0001", "starts_on": "2026-01-01", "status": "active" }, … ] },
  "entrypoint": "billing.sp_change_plan",
  "fixture_sha": "53b308f5…",
  "inputs": { "effective_on": "2026-03-01", "plan_id": "1000…0002", "tenant_id": "0000…0001" },
  "module": "plans",
  "probes": { "subscription_rows": [ … ] },
  "rerecord_reason": "scenario-redesign",
  "rules": ["PLANS-003"],
  "scenario": "PLANS-004",
  "source_sha": "2b98f8dc…"
}
```

### 3.3 Replay — grading

`procs/harness/replay.py main()` in order:

```mermaid
sequenceDiagram
  participant M as make procs-parity
  participant R as replay.py
  participant G as rules_gate.py
  participant T as billing-service
  M->>R: BILLING_SVC_URL=http://localhost:12096+offset
  R->>R: SOURCE_SHA / FIXTURE_SHA file vs live digest (exit 7 on mismatch)
  R->>R: select transcripts (--module / --scenario; exit 9 if empty)
  R->>R: per-transcript source_sha + fixture_sha check (exit 7)
  R->>R: module status must be pending|extracted (exit 6)
  R->>G: subprocess rules_gate.py --module <extracted module>
  G-->>R: exit 0 required, else exit 6
  R->>T: POST /internal/reset (204 required; exit 8 refused, exit 3 unreachable)
  loop each transcript
    alt module status == pending
      R->>R: record SKIP
    else extracted
      R->>T: POST /internal/reset
      R->>T: <method> <path> from routes.yaml, path/query/body from transcript inputs
      T-->>R: status + JSON
      R->>R: grade_response(): status != 200 ⇒ status failure, no field comparison
      R->>R: compare business_fields and probes via json_path
    end
  end
  R->>R: write procs/reports/parity.{md,json}
```

Grading rules, from `compare()` / `grade_response()`:

- Iteration is driven by the **transcript**, not the contract: every recorded
  `business_fields` key and every recorded `probes` key must have a mapping in
  `routes.yaml`. An unmapped key is a *contract error* (exit `6`), not a
  parity failure.
- The mapped value is pulled from the target's JSON body with a small JSONPath
  subset supporting `$`, `.field`, `[n]`, and `[*]` (`json_path()`); an
  unresolvable path is rendered as `<unresolvable $.x: missing field x>` and
  reported as a **failure**, not a crash.
- Normalization on the target side mirrors the recorder for `decimal`
  (2 dp, half-up), `integer`, `date`, lists, and dicts, so `"149.00"` from the
  service compares equal to the recorded `"149.00"`.
- `type: rows` requires a list of objects and compares them **in order** —
  ordering drift is a graded failure
  (`test_structured_rows_wrong_order_is_a_failure`).
- Any non-200 response is a single `status` failure; the error body is never
  compared (`test_non_200_response_is_reported_without_comparing_error_body`).
- The report is written on **every** exit path after grading begins, including
  a mid-loop target failure (`test_mid_loop_target_failure_writes_partial_report`).

Result classification (`classify_transcript()`): `pending` ⇒ `SKIP`,
`extracted` ⇒ graded, anything else ⇒ contract error.

### 3.4 Rules gate — human approval

`rules_gate.py validate_module()` fails a module (first failing class wins, and
the class determines the exit code) when:

| Check | Exit |
|---|---|
| No `procs/rules/<module>.rules.yaml` | `2` |
| `rules` not a list, or a rule missing `id`/`statement`/`source`/`outputs`/`confidence` | `7` |
| `decision` missing, `status` pending/absent, no `reviewer`, no `date`, or a `question` without an `answer` | `3` |
| Rule cites no scenario, cites an unknown scenario, or a module scenario is unclaimed | `4` |
| `source.file` is not `services/legacy-billing/db/procs/<module>.sql`, or the two-element `lines` range is out of bounds | `5` |
| A ledger rule has no `@pytest.mark.rule("<id>")` in `services/billing-service/tests/**.py`, or a discovered marker matches no rule in *any* ledger | `6` |

The gate is a hard precondition for grading: `replay.py` shells out to it for
every extracted module before it sends a single request.

### 3.5 Immutability and fingerprints

Two digests protect the evidence:

| Digest | Covers | Stored in |
|---|---|---|
| `source_sha()` | `services/legacy-billing/db/procs/*.sql` (glob) | each transcript + `procs/transcripts/SOURCE_SHA` |
| `fixture_sha()` | `services/legacy-billing/db/schema.sql`, `db/seed.sql` | each transcript + `procs/transcripts/FIXTURE_SHA` |

`check_immutability()` raises (exit `2`, `WOULD_OVERWRITE`) when transcripts
already exist and **either**:

- `--allow-rerecord` was not passed; or
- it was passed, but the procedure digest is unchanged **and** the fixture
  digest is unchanged **and** `--rerecord-reason` is not `harness-change` or
  `scenario-redesign`.

So: a procedure change (or a schema/seed change) authorizes a re-record with
`--allow-rerecord` alone; a harness-only or scenario-only change needs the
explicit audited reason, which is then written into every regenerated
transcript as `rerecord_reason`.

On the replay side, a stale digest is fatal before any request is sent — both
the global `SOURCE_SHA`/`FIXTURE_SHA` files and each selected transcript's own
`source_sha`/`fixture_sha` are compared to freshly computed digests (exit `7`).
This is the mechanism that prevents grading a modified legacy procedure against
evidence recorded from the previous version.

### 3.6 Legacy → target behavioral mapping (plans)

| Legacy entrypoint (`db/procs/plans.sql`) | Target (`app/main.py`) | Domain logic |
|---|---|---|
| `billing.fn_list_plans()` — SQL, `WHERE active ORDER BY monthly_fee, code` | `GET /api/plans` | `domain.catalog()` filters `active` and sorts by `(monthly_fee, code)` in Python. |
| `billing.fn_entitlement(p_tenant_id, p_on)` — picks the row with `starts_on <= on` and `ends_on IS NULL OR >= on`, `ORDER BY starts_on DESC LIMIT 1`, returning `GREATEST(s.starts_on, p_on)` as `effective_on` | `GET /api/tenants/{tenant_id}/entitlement?on=…` | `domain.entitlement()` applies the same predicate and `max(…, key=starts_on)`; the route emits `max(row.starts_on, on)`. 404 when nothing is eligible. |
| `billing.sp_change_plan(...)` — closes open prior subscriptions at `effective_on - 1` (keeping `cancelled`), inserts a new `active` row keyed `md5(tenant||plan||date)::uuid` | `POST /api/tenants/{tenant_id}/plan-change` | `domain.change_plan()` performs the same close/insert, but keys the new row `uuid5(PLAN_CHANGE_NAMESPACE, tenant+plan+date)`. |

The two implementations therefore produce **different subscription UUIDs**.
Parity still holds because the scenarios capture `plan_id`, `starts_on`,
`ends_on`, and `status` — never the subscription id (see
`procs/scenarios/plans/004.yaml` and `005.yaml`).

The target adds behavior the legacy procedure does not have, documented in
`services/billing-service/README.md` as target-side error handling rather than
a parity rule: a repeated identical plan change raises a unique violation in
the legacy procedure, whereas `main.py` maps it to HTTP 409 (and a FK violation
to 400).

---

## 4. Key interfaces & contracts

### 4.1 `procs/routes.yaml` — the parity contract

```yaml
modules:
  <module>:
    status: extracted | pending          # status.py VALID_STATUSES; missing module ⇒ pending
    entrypoints:
      <schema>.<function_or_proc>:
        method: GET | POST
        path: /api/tenants/{tenant_id}/entitlement
        inputs:                          # maps contract placeholders → transcript input names
          path:  { tenant_id: tenant_id }
          query: { "on": as_of }         # note: contract name "on", transcript input name "as_of"
          body:  { plan_id: plan_id, effective_on: effective_on }
        response:
          business_fields:
            codes: { json_path: "$[*].code", type: text, collect: true }
            subscriptions: { json_path: "$.subscriptions", type: rows }
          probes:
            subscription_rows: { json_path: "$.subscriptions" }
```

Key consequence: **probes are graded against the target's HTTP response**, not
against the target database. A recorded state probe can only be satisfied if
the extracted endpoint surfaces that state in its payload — which is why
`POST /api/tenants/{tenant_id}/plan-change` returns the full `subscriptions`
list.

Current contents on `main`: `plans` is `extracted` with three entrypoints;
`rating`, `invoicing`, `dunning` are `pending` with `entrypoints: {}`.

### 4.2 Scenario file — `procs/scenarios/<module>/NNN.yaml`

```yaml
id: PLANS-004                     # transcript filename and ledger citation key
module: plans                     # must match the directory
description: Change tenant 1 to plan 2 effective 2026-03-01.
entrypoint: billing.sp_change_plan
kind: function | procedure
inputs:                           # positional; typed by record.typed()
  - {name: tenant_id, type: uuid, value: 00000000-0000-0000-0000-000000000001}
capture_query: "SELECT …"         # replaces result rows (required for procedures)
after_sql: "CALL billing.sp_suspend_overdue('2026-02-28')"   # optional second call
fields:
  - {name: codes, from: code, type: text, collect: true}
  - {name: subscriptions, collect_rows: true, columns: {plan_id: text, starts_on: date, …}}
probes:
  - {id: subscription_rows, collect_rows: true, query: "SELECT …"}
```

Hygiene enforced by `procs/harness/tests/test_scenarios.py`:

- `setup_sql`, `before_sql`, and `rules` keys are rejected (rules come from the
  ledger, not the scenario);
- probe queries may not use `string_agg` or string concatenation of columns
  (probes must return typed columns, not pre-joined strings);
- all scenarios for the same entrypoint must declare the **same probe shape**
  (same probe ids, same `collect_rows` flags).

### 4.3 Rule ledger — `procs/rules/<module>.rules.yaml`

```yaml
module: plans
rules:
  - id: PLANS-003
    statement: A plan change closes the open prior subscription on the preceding date.
    source: {file: services/legacy-billing/db/procs/plans.sql, lines: [42, 64]}
    inputs: [tenant_id, plan_id, effective_on]
    outputs: [subscriptions]
    confidence: high
    scenarios: [PLANS-004]
    decision: {status: approved, reviewer: product-owner, date: "2026-08-11", note: …}
```

`ledger.scenario_rule_map()` inverts this into scenario → rule ids, which is
what lands in each transcript's `rules` array and in
`procs/transcripts/index.json`. Pending modules have `rules: []` there.

### 4.4 Legacy database contract

- Schema: `services/legacy-billing/db/schema.sql` — 11 tables in schema
  `billing` (`tenants`, `plans`, `subscriptions`, `usage_events`,
  `rating_periods`, `rating_results`, `invoices`, `invoice_lines`,
  `credit_notes`, `dunning_attempts`, `notifications`), with `CHECK`
  constraints on every status/enum-like column.
- Entrypoints (12), grouped by file:
  - `procs/plans.sql`: `fn_list_plans`, `fn_entitlement`, `sp_change_plan`
  - `procs/rating.sql`: `fn_usage_rating`, `fn_usage_summary`, `sp_finalize_rating`
  - `procs/invoicing.sql`: `fn_invoice_preview`, `fn_invoice_lines`, `sp_issue_invoice`
  - `procs/dunning.sql`: `fn_overdue_accounts`, `sp_schedule_dunning`, `sp_suspend_overdue`
- Seed: `services/legacy-billing/db/seed.sql` — 9 tenants
  (`0000…0001`–`0000…0009`; tenant 2 suspended, tenant 3 `tax_exempt`), 3 plans
  (`STARTER` 49.00/100/0.055, `GROWTH` 149.00/500/0.035, `SCALE` 499.00/2000/0.020),
  one subscription per tenant from `2026-01-01`, 10 usage events in Feb 2026,
  three prior rating periods for tenant 1, three invoices (two `overdue`), five
  credit notes, one prior dunning attempt and notification.
- Legacy HTTP surface (`services/legacy-billing/app/app.py`), all
  unauthenticated: `GET /health`, `GET /`, `GET /plans`,
  `GET /plans/<tenant_id>/entitlement?on=`, `POST /plans/<tenant_id>/change`
  (form-encoded), `POST /api/rating/preview|finalize` (JSON),
  `GET /api/invoices/<tenant>/preview`, `POST /api/invoices/<tenant>/issue`,
  `GET /api/invoices/<invoice>/lines`, `GET /api/dunning/overdue`,
  `POST /api/dunning/schedule|suspend`.

### 4.5 Target service contract

- Endpoints (`services/billing-service/app/main.py`): `GET /health` (503 when
  the DB is down), `POST /internal/reset` (204; 404 when disabled),
  `GET /api/plans`, `GET /api/tenants/{tenant_id}/entitlement?on=`,
  `POST /api/tenants/{tenant_id}/plan-change`.
- Settings (`app/config.py`, `pydantic-settings`, env prefix `BILLING_SVC_`,
  `.env` supported): `BILLING_SVC_DATABASE_URL` (**required**, no default),
  `BILLING_SVC_APP_NAME`, `BILLING_SVC_SCHEMA_NAME` (`billing_svc`),
  `BILLING_SVC_CORS_ORIGINS` (default `["http://localhost:3000"]`),
  `BILLING_SVC_ALLOW_INTERNAL_RESET` (default `false`).
- Schema/migration: `db/migrations/001_initial.sql` (idempotent
  `CREATE … IF NOT EXISTS` in schema `billing_svc`), applied on FastAPI
  lifespan startup and again on every reset.
- `POST /internal/reset` = migrate → `TRUNCATE subscriptions, plans, tenants`
  → apply `db/seed.sql` (`app/db.py`). This is what lets the harness isolate
  every scenario.
- The target seed is **generated** from the legacy seed by
  `services/billing-service/scripts/generate_seed.py`, which regex-extracts the
  `tenants`, `plans`, and `subscriptions` INSERT blocks and rewrites the schema
  prefix `billing.` → `billing_svc.`.

### 4.6 Recorder / replay environment variables

| Variable | Used by | Default |
|---|---|---|
| `NS` | Makefile port derivation, Compose DB names | none — required by `procs-validate` |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `record.py connection()` | `localhost` / `55432` / `billing_$NS` / `billing` / `billing` |
| `DB_PASSWORD` | `docker-compose.procs.yml` legacy DB | `billing` |
| `BILLING_SVC_URL` | `replay.py --base-url` default | `http://localhost:8097` (Makefile overrides with the derived port) |
| `PROCS_DB_PORT` / `PROCS_APP_PORT` / `PROCS_TARGET_DB_PORT` / `PROCS_TARGET_PORT` | Compose host port publication | `55432` / `8096` / `56432` / `8097` |
| `BILLING_SERVICE_URL` | Vite `/billing-api` proxy target (`frontend/client-app/vite.config.ts`) | `http://localhost:12109` |
| `VITE_ENABLE_BILLING_FIXTURE` | client billing route registration | dev on; preview build must opt in |

### 4.7 Namespace → port derivation

`Makefile`: `PROCS_PORT_OFFSET = zlib.crc32(NS) % 1000`, then

| Component | Host port |
|---|---|
| legacy Postgres | `55432 + offset` |
| legacy Flask app | `8096 + offset` |
| target Postgres | `56432 + offset` |
| target FastAPI app | `12096 + offset` |

All publications bind `127.0.0.1` only. Verified offsets:
`NS=dev` ⇒ 13 (`55445`, `8109`, `56445`, `12109`), `NS=ci` ⇒ 263.
Note the container-internal target port is `8097`, while the *host* mapping
starts from `12096` — the two are unrelated numbers.

---

## 5. Operational runbook

All commands run from the repository root. `uv` is required (the Make targets
call `uv run --with psycopg[binary]==3.2.9 --with pyyaml==6.0.2`); Docker is
required for anything involving the stack.

### 5.1 Inspect without starting anything

```bash
make procs-list                 # module status, scenario count, rule claims
make procs-list MODULE=plans
make procs-rules-gate MODULE=plans
make procs-rules-gate ALL=1
uv run --with psycopg[binary]==3.2.9 --with pyyaml==6.0.2 --with pytest==8.3.5 \
  pytest procs/harness/tests
```

Verified output while writing this document:

```
$ make procs-list
dunning      pending   scenarios= 5 rule_claims= 0
invoicing    pending   scenarios= 6 rule_claims= 0
plans        extracted scenarios= 5 rule_claims= 4
rating       pending   scenarios= 8 rule_claims= 0

$ make procs-rules-gate ALL=1
Rules gate PASS: plans

$ pytest procs/harness/tests
37 passed
```

### 5.2 Full local loop

```bash
make procs-up NS=dev            # docker compose up -d --build --wait (4 services)
make procs-rules-gate MODULE=plans
make procs-parity NS=dev        # writes procs/reports/parity.{md,json}
make procs-parity NS=dev MODULE=plans SCENARIO=PLANS-001
make procs-down NS=dev          # compose down -v (drops that namespace's volumes)
```

A green full run prints `Parity PASS=5 FAIL=0 SKIP=19` (5 graded plans
scenarios, 19 pending-module transcripts skipped) and exits 0 — verified by
running `make procs-up` + `make procs-parity` on a throwaway namespace while
writing this document.

Health checks while up (`NS=dev` ⇒ offset 13):

```bash
curl http://localhost:8109/health          # {"service":"legacy-billing","status":"UP"}
curl http://localhost:12109/health         # {"status":"healthy","service":"billing-service"}
curl http://localhost:12109/api/plans
psql "postgresql://billing:billing@localhost:55445/billing_dev" -c \
  "SELECT * FROM billing.fn_list_plans()"
```

### 5.3 Recording

```bash
make procs-record NS=dev                                  # refused if transcripts exist
make procs-record NS=dev ALLOW_RERECORD=1                 # after a procedure/fixture change
make procs-record NS=dev ALLOW_RERECORD=1 RERECORD_REASON=harness-change
make procs-record NS=dev ALLOW_RERECORD=1 RERECORD_REASON=scenario-redesign
make procs-record NS=dev MODULE=plans OUTPUT_DIR=/tmp/isolated-transcripts
```

`OUTPUT_DIR` writes an isolated transcript tree (used for namespace-specific
verification runs without touching the checked-in evidence).

### 5.4 Target service on its own

```bash
cd services/billing-service
uv sync
uv run pytest
uv run ruff check app scripts tests
uv run uvicorn app.main:app --reload --port 8097     # needs BILLING_SVC_DATABASE_URL
uv run python scripts/generate_seed.py               # regenerate db/seed.sql from the legacy seed
```

`tests/conftest.py` defaults `BILLING_SVC_DATABASE_URL` to
`postgresql://billing_svc:billing_svc@localhost:56432/billing_svc_dev` — note
this is the *unoffset* port, so it only lines up with a stack whose namespace
hashes to offset 0. The checked-in tests do not open a real connection (they
use fakes/monkeypatching), so this default is inert in practice.

### 5.5 Client fixture

```bash
cd frontend/client-app && npm run dev        # http://localhost:3000/billing/plans
# preview build must opt in:
VITE_ENABLE_BILLING_FIXTURE=true npm run build
npm run start -- --host 127.0.0.1 --port 4173
# non-default namespace:
BILLING_SERVICE_URL=http://localhost:<12096+offset> npm run dev
```

### 5.6 CI

`.github/workflows/procs-parity.yml` runs on pushes/PRs touching `procs/**`,
`services/legacy-billing/**`, `services/billing-service/**`, the client billing
feature, `docker-compose.procs.yml`, or `Makefile`:

1. `ruff check procs/harness`
2. `cd services/billing-service && uv sync --locked && uv run ruff check app scripts tests && uv run pytest`
3. `pytest procs/harness/tests`
4. `cd frontend/client-app && npm ci && npm run lint && npm test`
5. `make procs-up NS=ci` → `make procs-rules-gate ALL=1` → `make procs-parity NS=ci`
6. uploads `procs/reports/parity.*` as the `stored-procedure-parity-report`
   artifact (`if: always()`), then `make procs-down NS=ci`.

`procs/reports/` is gitignored (`.gitignore:93`); the report is a CI artifact,
not a committed file.

### 5.7 Credentials / offline notes

- The parity subsystem needs **no** cloud credentials. It is fully local:
  Postgres 16 images, two locally built images, loopback ports.
- It is not fully offline: `make procs-up` pulls `postgres:16` and builds two
  Python images (`pip install` from PyPI); the Make targets resolve packages
  through `uv`; CI additionally runs `npm ci`.
- `etl/` cannot be run locally as-is. `etl/run.sh` sources `/opt/etl/.env`,
  `cd`s to `/opt/etl/scripts`, and each script reads the absolute path
  `/opt/etl/config.ini`. The scripts target real AWS (SQS, DynamoDB, S3),
  `analytics-db.internal.otterworks.dev`, MeiliSearch, and the
  document/file services. There is no Makefile target, Compose service, or test
  for them, and `etl/config.ini` ships an AWS example key
  (`AKIAIOSFODNN7EXAMPLE`) plus a plaintext database password.

---

## 6. Failure modes & gotchas

### 6.1 Exit codes (memorize these; they are the harness's error contract)

| Code | `record.py` | `replay.py` | `rules_gate.py` |
|---|---|---|---|
| 1 | — | graded parity failure | — |
| 2 | would overwrite immutable transcript | — | missing ledger |
| 3 | legacy stack unreachable | target unreachable | invalid decision |
| 4 | scenario failed / unknown module | — | invalid scenario coverage |
| 5 | — | — | invalid source range |
| 6 | — | contract missing/unmapped, or rules gate not green | invalid marker coverage |
| 7 | — | source/fixture digest mismatch | invalid ledger schema |
| 8 | — | target reset refused/failed | — |
| 9 | — | selection matched no transcripts | — |

### 6.2 Harness gotchas

- **Adding a procedure file requires three edits.** `fingerprints.PROC_DIR.glob("*.sql")`
  picks up a new file automatically, but `record.DB_FILES` is a hardcoded list
  of six paths and `docker-compose.procs.yml` mounts each `.sql` individually
  into `/docker-entrypoint-initdb.d/`. Add a file to only one of the three and
  the digest changes while the database never loads the procedure.
- **`fixture_sha` does not cover the procedures, and `source_sha` does not
  cover the fixture.** Both are checked, but they are separate digests over
  disjoint file sets; neither covers `procs/scenarios/**` or the harness
  itself, which is exactly why the audited `--rerecord-reason` values exist.
- **`--allow-rerecord` alone silently suffices after *any* fixture change.**
  `check_immutability()` treats a changed `schema.sql`/`seed.sql` the same as a
  changed procedure, so a seed tweak can regenerate every transcript without
  the audited reason being recorded.
- **`make procs-record` re-records all modules by default.** Without
  `MODULE=<m>` the recorder loads `*/*.yaml`; combined with `ALLOW_RERECORD=1`
  that rewrites every transcript, not just the module you changed.
- **A missing `NS` is an error, not a default.** `procs-validate` exits 2 if
  `NS` is empty or `python3` is unavailable (the port offset is computed by
  `python3 -c "import zlib; …"` inside `$(shell …)`).
- **Reset is off by default.** `BILLING_SVC_ALLOW_INTERNAL_RESET` is `false` in
  `app/config.py`; `POST /internal/reset` then returns 404 and replay exits `8`
  with a message naming the variable. `docker-compose.procs.yml` sets it to
  `"true"` for the disposable stack only.
- **Probes grade the HTTP response, not the target database.** A recorded probe
  over `billing.notifications` can only be graded if the extracted endpoint
  returns that state in JSON. This constrains target API design: side effects
  under contract must be observable in the response body.
- **Transcript input names and contract input names differ.**
  `procs/scenarios/plans/002.yaml` names its second input `as_of`, while
  `routes.yaml` maps query parameter `"on"` → transcript input `as_of`. The
  mapping is by transcript input name; renaming an input in a scenario breaks
  the contract lookup with a `KeyError` on the input dict.
- **Row comparisons are order-sensitive.** `type: rows` compares lists
  positionally, so the target must reproduce the recorded ordering (for
  `plan-change`, `main.py` sorts by `starts_on`).
- **A pending module can never fail.** `SKIP` counts are not failures; if you
  flip a module to `extracted` without adding entrypoints, the transcripts
  become contract errors (exit 6) rather than skips.
- **`status: draft`-style typos are rejected**, not defaulted:
  `status_for()`/`VALID_STATUSES` allow only `pending`/`extracted`; anything
  else exits 6 from replay and errors out of `procs-list`.

### 6.3 Legacy procedure behaviors worth knowing before extracting

These are observed in the SQL; several look like accidents of the original
implementation but are *load-bearing* for parity because the transcripts record
their output.

- `fn_usage_rating` (`rating.sql`): the first overage tier is capped at a
  literal `101` units (`v_first := LEAST(v_billable, 101)`), with the remainder
  billed at `1.5 ×` the plan rate. Rollover is clamped twice — once inside the
  aggregate (`LEAST(2 * included_units, sum(...))`) and again afterwards — and
  the prior-period lookup window is `>= period_start - interval '3 months'`.
- `fn_usage_rating` proration: when the subscription is `suspended` and
  `suspended_on` falls inside the period, both `billable_units` and
  `overage_amount` are scaled by `(period_end - suspended_on + 1) / (period_end - period_start + 1)`
  — i.e. by the *suspended* tail, not the active head. **(inference: this looks
  inverted relative to the usual intent; the transcripts nevertheless pin the
  current result.)**
- `fn_usage_rating` does not guard `NOT FOUND`: if no subscription matches,
  `v_sub`/`v_plan` stay NULL and the arithmetic yields NULLs rather than an
  error.
- `sp_finalize_rating` stores `rollover_units` as
  `GREATEST(quota_units - used_units, 0)` — a *different* quantity from the
  `rollover_units` that `fn_usage_rating` returns for the same period.
- `fn_invoice_preview` (`invoicing.sql`): tax is `(monthly_fee + overage) * 0.0825`
  for non-exempt tenants, then split across two lines as `v_tax / 2` with **no
  rounding**, so odd cents can produce half-cent line amounts; the `credit` line
  carries its value in `total` (negative) and `credit_applied`, with `amount = 0`.
- `sp_issue_invoice`: line-level rounding happens per line (`round(...)` on plan
  and usage) while the tax lines are summed unrounded; the credit consumption
  loop subtracts the *whole* applied credit from each note it visits
  (`remaining_amount - v_credit`) before decrementing `v_credit` by that note's
  original balance — with several open notes this over-consumes. Invoice and
  line ids are derived with `md5(...)::uuid`, and `ON CONFLICT DO UPDATE` makes
  re-issue idempotent on the header while lines are deleted and re-inserted.
- `sp_schedule_dunning` (`dunning.sql`): schedules on `p_as_of`, shifting
  Saturday (+2) and Sunday (+1) to Monday; the attempt number is
  `max(attempt_no) + 1` per invoice with `ON CONFLICT (invoice_id, attempt_no) DO NOTHING`.
  It ignores `p_as_of` when selecting invoices (all `overdue` invoices, no date
  filter), unlike `fn_overdue_accounts`, which requires `issued_at::date < p_as_of`.
- `sp_suspend_overdue`: suspends tenants with an `overdue` invoice issued
  `<= p_as_of - 14`, sets `suspended_on = p_as_of` on active subscriptions, and
  inserts a `suspension` notification guarded by `NOT EXISTS` — the source of
  the idempotence checked by `procs/scenarios/dunning/005.yaml` via `after_sql`.
- `fn_entitlement` returns `GREATEST(s.starts_on, p_on)` as `effective_on`,
  i.e. the later of the subscription start and the query date. The target
  reproduces this in the route layer (`max(row.starts_on, on)`), not in the
  domain function.
- `sp_change_plan` sets `status = CASE WHEN status = 'cancelled' THEN status ELSE 'active' END`
  when closing the prior row — a suspended subscription is silently reactivated
  as it is closed.
- Deterministic ids everywhere (`md5(...)::uuid`) mean re-running a procedure
  with identical inputs collides on the primary key instead of inserting a
  duplicate; `sp_change_plan` is the one place that has no `ON CONFLICT`, so the
  legacy path surfaces a raw unique violation.

### 6.4 Legacy application / stack gotchas

- `services/legacy-billing/app/app.py` has query-parameter defaults baked in
  (`on` defaults to `2026-02-28`, invoice preview defaults to the
  `2026-02-01`…`2026-02-28` period), matching the seed's Feb-2026 data.
- `app.py` mixes content types: `/plans/<t>/change`, `/api/invoices/<t>/issue`,
  and `/api/dunning/*` read `request.form`, while `/api/rating/*` read JSON.
- The Flask app's `execute()` opens a connection per call and relies on
  psycopg's context-manager commit; there is no explicit transaction spanning
  a request.
- `docker-compose.procs.yml` mounts the SQL files into
  `/docker-entrypoint-initdb.d/`, which only runs on **first** volume
  initialization. After a schema/seed edit, `make procs-down NS=<ns>` (which is
  `down -v`) is required — a plain restart keeps the old volume. In practice the
  recorder papers over this by dropping and recreating the `billing` schema on
  every scenario.
- Compose publishes on `127.0.0.1` only; remote/browser access from another
  host needs an explicit tunnel.

### 6.5 `etl/` gotchas

- Credentials are committed in plaintext (`etl/config.ini`: `[aws] access_key`
  / `secret_key`, `[database] password`, `[services] meilisearch_api_key` —
  values not reproduced here), and `run.sh` sources
  `/opt/etl/.env` if present.
- Silent failure paths: bare `except:` blocks at
  `etl/scripts/analytics_daily.py:78,100,177`,
  `audit_archive_weekly.py:152,164`, `search_reindex_weekly.py:70`, and
  `user_activity_daily.py:173`; the outer handlers `print` and `sys.exit(1)`.
- Hardcoded, non-configurable resources — e.g. the SQS queue URL
  `https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics`
  inline in `analytics_daily.py` (flagged in-file as `TODO ETL-089`).
- Pinned-old dependencies (`etl/requirements.txt`: `boto3==1.26.0`,
  `psycopg2-binary==2.9.3`, `pandas==1.3.5`, `requests==2.27.0`); the analytics
  job aggregates in-memory with pandas.
- Each script is a single monolithic `main()`; there are no tests anywhere
  under `etl/`.
- `etl/crontab` schedules `analytics_daily` at 02:00 and `storage_cleanup_daily`
  at 02:30 on the same host with no dependency ordering or locking.
- `etl/ETL_UPGRADE_GUIDE.md` describes the intended Airflow 2.8 target
  (DAG-per-script, Connections/Variables, provider hooks, PySpark, pytest,
  alerting) — it is a plan document; no Airflow code exists in the repo.

---

## 7. Open questions / gaps

Unresolved from the source alone; listed without invented answers.

1. **Why is the first overage tier capped at `101`?** The literal in
   `fn_usage_rating` has no comment, no ledger rule, and no seed value that
   explains it. The `1.5 ×` second-tier multiplier is likewise undocumented.
2. **Is the suspension proration in `fn_usage_rating` intended?** It scales by
   the suspended tail of the period; no rule ledger covers `rating`, so there is
   no approved statement of intent to compare against.
3. **Is the credit-consumption loop in `sp_issue_invoice` intended?** With more
   than one open credit note the arithmetic appears to over-consume; the
   invoicing scenarios recorded on `main` (`INVOICE-004`) pin the current
   behavior but no rule explains it.
4. **`sp_finalize_rating` persists a different `rollover_units` than
   `fn_usage_rating` returns.** Which definition an extraction must preserve is
   undecided in the repo.
5. **No ledgers for `rating`, `invoicing`, `dunning`.** 19 transcripts exist
   with `rules: []`. `make procs-rules-gate ALL=1` only iterates
   `procs/rules/*.rules.yaml`, so absent ledgers are invisible rather than
   reported as missing coverage.
6. **The legacy HTTP layer is untested and ungraded.** Parity covers database
   entrypoints only; nothing verifies that `app.py`'s routes, defaults, or
   form/JSON handling are preserved by the extraction.
7. **`tests/conftest.py` hardcodes the unoffset target DB port 56432.** Whether
   any integration test is meant to run against a live namespace stack (and if
   so, which one) is unspecified.
8. **Divergent subscription-id derivation** (`md5` vs `uuid5`) is deliberate per
   `services/billing-service/README.md`, but nothing enforces that ids stay out
   of the parity contract; adding an id to a scenario's captured fields would
   make the modules permanently non-parity.
9. **`etl/`'s relationship to this subsystem is undeclared.** No code, config,
   or Makefile target connects the batch chain to billing; the grouping appears
   organizational rather than technical. **(inference)**
10. **`.agents/skills/oracle-billing-estate` and `.agents/skills/legacy-etl-demo`
    describe assets absent from `main`** (`services/legacy-billing/db/oracle/`,
    `etl/legacy-extra/`, and their Make targets). Whether those are intended to
    land on `main` is not stated anywhere in-tree.
11. **No documented rotation/removal plan for the committed `etl/config.ini`
    credentials.** `ETL_UPGRADE_GUIDE.md` lists deleting the file and rotating
    secrets as the final migration step; no ticket or owner exists in-repo
    (the file's own comment points at `ETL-142`, deferred).
12. **Parity reports are gitignored**, so there is no committed historical
    record of parity results; the only evidence is per-run CI artifacts.
