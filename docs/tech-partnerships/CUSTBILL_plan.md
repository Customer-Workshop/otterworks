# CUSTBILL (P-B) — migration plan (for STOP C)

**Phase:** `!dbx_migration_plan` · **Input:** `CUSTBILL_analysis.md` (same commit series) ·
**Status:** PROPOSED — nothing here executes until STOP C is approved in `#ow-migrations`.
Tolerances: `.migration/03_recon_tolerances.md` v1 (approved STOP A). Conventions: `.migration/01_conventions.md`.
Target profiles present for every workload type in P-B (PIPELINE, ORCHESTRATION, CONSUMER, DATA/DEPENDENCY, CORE).

## 1. Dependency decisions (decide mode)

Every P-B entry that was UNDECIDED/OPEN in the register gets a decision here. **Lead-time requests** are fired
in the STOP C message itself (the customer proxy for this engagement is the `#ow-migrations` approver);
each is recorded in the register with the STOP C permalink once posted. No entry stays UNDECIDED past STOP C —
customer-owned items get a **default that the run proceeds on** plus an explicit coverage-gap declaration.

| ID | Decision (proposed) | Fired request | Blast radius if the customer answers differently |
|---|---|---|---|
| D1-1, D1-2 | Interfaces fixed by **parent-owned DDL in wave 0** (§4.1–4.4 of the analysis, tables created empty by Terraform/`dbx.py`); children never run DDL. Fixture inputs for U7/U8 are seeded by the parent from the deterministic legacy outputs (`.dat` → fixture bronze, `.psv` → fixture silver) so no child waits on a sibling. | – | none |
| D2-1 | Wave 0 work list (§3). | – | none |
| D2-2 | P-B's four crontab lines are retired only at STOP E; legacy files untouched; the Workflow ships with `pause_status=PAUSED`. | – | none |
| D3-3 | Contract fixes the four ambiguity classes from the fixtures: **encoding** ASCII, `\n` terminator; **malformed record**: any line starting `HDR`/`TRL` dropped wherever it appears (parity with legacy), short (<65 B) records → quarantine `short_record`, non-digit amount → `bad_implied_decimal`, invalid calendar date → `invalid_calendar_date`, trailer≠body count → file-level `trailer_count_mismatch` (rows still loaded, file flagged); **empty input**: a file with HDR+TRL and no body is valid and yields 0 rows and no quarantine; no files = successful no-op run; **batch granularity**: one source file = one batch, natural key `(ns, source_file, line_no)`. Production EBCDIC/`\r\n` is a **declared coverage gap** until the mainframe owner confirms. | R1 to mainframe owner (CB77340): confirm encoding, terminator, HDR/TRL placement | If EBCDIC: U6 gains a code-page translation step; silver logic unchanged. One extra child round. |
| D4-1 | Gold table `ow_tp.gold.finance_billing` + exports under `/Volumes/ow_tp/bronze/landing/reports/<ns>/`: `finance_billing_<YYYYMMDD>.csv` (byte-identical to legacy after T6) **and** a real `finance_billing_<YYYYMMDD>.xlsx` (openpyxl, same 4 columns). Delivery = Workflow e-mail notification on success/failure to a Terraform var `finance_recipients`, default `["finance-reports@otterworks.dev"]`; `jake@` removed. Notification not exercised during the run (schedules PAUSED; manual runs notify the run owner only). | R2 to finance: confirm recipient list and whether `.xlsx` replaces `.xls` | Recipient/format change = Terraform var + one export line; no recon impact (T6 compares the CSV). |
| D4-4 | Shared-drive hand-off is customer-owned at STOP E (copy of the volume export or repoint); not implemented in the run. | R3 to finance/ops: does the shared-drive pickup exist, and where | If it exists: a cutover-checklist item, no code in waves 1–3. |
| D5-1, D5-2, D5-3 | **One Workflow `ow_tp_custbill`** with tasks `ingest → parse → finance`, `max_concurrent_runs=1`, retries 2 with alert on final failure, trigger = **file-arrival on `/Volumes/ow_tp/bronze/landing/<ns>/incoming/`** (if the workspace does not offer file-arrival on a UC volume — verified in wave 0 by `dbx.py` — fallback cron `*/15` matching legacy cadence). Finance recomputes on every run (6-row aggregate; cost negligible) so the 02:10 vs 02:00 overlap and the `sleep 600` both disappear. `run_all.sh` = a manual "Run now" of the same Workflow; **no separate code**. All schedules/triggers `PAUSED` until STOP E. | – | none |
| D7-1, D10-6 | During the run the **parent pushes** seeded drops into `/Volumes/ow_tp/bronze/landing/<ns>/incoming/` via `dbx.py land` (the live producer path). Production landing (mainframe SFTP → S3/Transfer Family → external location, or a customer file gateway writing to the volume) is a **customer decision deferred to STOP E**; AWS Transfer Family is *not* provisioned by this run (hourly-billed endpoint, violates the serverless-only guardrail). | R4 to mainframe/infra owner: name the owner and the preferred landing mechanism | Production path is a cutover item; U6 code reads the volume regardless of who writes it. |
| D8-3 | Secret scope `ow_tp`, keys `sftp_host`, `sftp_user`, `sftp_password` (fixture values, names only in code), seeded by the parent in wave 0. Production credential customer-issued at STOP E. | – | none |
| D4-2, D3-1, D3-2, D6-1, D6-2, D4-3, D5-4, D5-5 | **Out of P-B scope** — remain as registered for pipelines P-A/C/D/E; not decided here. | – | – |

## 2. Fan-out shape (D-012) — recommendation

| | Conservative (lineage order) | **Recommended: pilot + calibrated pair** | Max parallel |
|---|---|---|---|
| Wave 1 | U6 | **U6 (pilot, width 1)** | U6, U7, U8 |
| Wave 2 | U7 | **U7 + U8 (width 2)** | U9 |
| Wave 3 | U8 | **U9 (width 1)** | – |
| Wave 4 | U9 | – | – |
| Serial floor | 4 child hops | **3** | 2 |
| Why | no interface risk | pilot calibrates the dialect notes on the cheapest unit; U7/U8 are different pattern classes (parse vs aggregate/report) and both consume parent-seeded fixtures, so they teach independently | forfeits the pilot rule |

Width confirmation requested at STOP C: **max 2 concurrent children**, pilot width 1. (The D10 facts — one
shared PAT, demo workspace — comfortably allow 2.)

## 3. Scaffolding delta (wave 0, parent-owned, PRs `migrate/w0-<topic>` into the run branch)

| # | Item | Reuse / new | Done when |
|---|---|---|---|
| W0-1 | `infrastructure/terraform-databricks/`: catalog `ow_tp`, schemas `bronze/silver/gold`, volume `bronze.landing`, secret scope `ow_tp` (+ D8-3 keys), **tables** `bronze.custbill_raw`, `silver.custbill_records`, `silver.custbill_quarantine`, `gold.finance_billing` (DDL from analysis §4), Workflow shell `ow_tp_custbill` (3 empty notebook tasks, PAUSED) | new (D10-1/D10-2) | `terraform plan` clean; `make tp-preflight PLATFORM=databricks` 10/10 |
| W0-2 | `scripts/tp_databricks/dbx.py`: `land` (push seeded `.dat` files to the volume for `ns`), `seed-fixture` (bronze/silver fixture rows from legacy outputs for a child `ns`), `run-job`, `recon` helpers, `verify-file-arrival-trigger` | new; wraps the SDK already used by `dbx-showcase` | smoke-tested against NS=demo once |
| W0-3 | Contracts `docs/tech-partnerships/contracts/{sftp_ingest_poll,parse_custbill_fixedwidth,finance_excel_report,custbill_workflow}.contract.json` (schema `unit-contract.schema.json`), encoding the §1 decisions; contracts README §"stacked PR" amended per D-002 | new | `make tp-validate-contracts` PASS |
| W0-4 | Recon harness `scripts/tp_databricks/recon_custbill.py` producing `recon-report.schema.json`-valid JSON for the §5 checks, parameterised by `ns` and `run_mode` | new | `make tp-validate-recon FILE=...` PASS on a fixture run |
| W0-5 | Dialect notes `docs/tech-partnerships/dialect-cron-shell-perl.md` (ksh/bash/awk/Perl → PySpark/SQL idioms: byte-offset slicing, implied decimal, `%.2f`, hash-order sort, `localtime` stamps) | new (D-006) | reviewed by parent |
| W0-6 | Child hand-off template (§4) + `.migration/05_progress.md` write-target registration rows for U6–U9 | new | rows present before any launch |
| W0-7 | Blueprint proposal: `AWS_DEFAULT_REGION=us-east-1`, `ksh` present (D10-4/D10-3) | update | suggestion sent |

Data-load posture: **no backfill** for P-B (file-based estate, no legacy tables; history backfill via
`gen_history_data.pl` is a separate showcase, not a P-B unit). Federation N/A (D-003).

## 4. Execution schedule

Common to every batch: branch `migrate/w<N>-<unit>` off the run branch; **one PR per unit** titled
`[DBX w<N>] <unit>: …`; child namespace `NS=<unit-short>-w<N>` with `OTTERWORKS_LEGACY_ROOT=/home/ubuntu/otterworks-legacy-<ns>`;
children run `run_mode: fixture` only and **never touch NS=demo**; idempotency rule = drop-and-recreate the
child's fixture area on every run; **child live budget = 0**. Hand-off content each child receives (they
share nothing with the parent): the contract JSON path, analysis §4 dictionary, target-state profile
sections, dialect notes, recon harness path + PASS definition, the fixture seed command, the write-target
registration line, the escalation rule ("blocked on an unlanded sibling or a contract gap → STOP and report,
never build a substitute").

| Wave | Batch / unit | Size | Target code | Profiles | Fixture seed | Recon rows (analysis §7) | Window tier |
|---|---|---|---|---|---|---|---|
| 0 | parent | – | W0-1..7 | all | – | harness self-test | – |
| 1 (pilot) | U6 `sftp_ingest_poll` | S | `databricks/sftp_ingest_poll/` notebook: list volume `incoming/`, copy-verify (sha256) into `landing/<ns>/archive/`, load `bronze.custbill_raw`, delete source only after verify | PIPELINE ingest | `make legacy-etl-gen-data NS=<ns>` + `make tp-fixture-land NS=<ns>` | U6 (a)–(d) | short |
| 2 | U7 `parse_custbill_fixedwidth` | M | `databricks/parse_custbill_fixedwidth/` DLT or notebook: substring slicing, typed cast, expectations → quarantine, trailer check, `MERGE` on natural key | PIPELINE parse (DLT expectations) | `dbx.py seed-fixture --layer bronze` from legacy `.dat` | U7 (a)–(f) | full (money path) |
| 2 | U8 `finance_excel_report` | S | `databricks/finance_excel_report/`: Spark SQL aggregate `INSERT OVERWRITE … WHERE ns=?`, CSV + `.xlsx` export to volume, notification hook | PIPELINE aggregate + CONSUMER | `dbx.py seed-fixture --layer silver` from legacy `.psv` | U8 (a)–(d) | full (money path) |
| 3 | U9 `custbill_workflow` | S | Workflow JSON/Asset Bundle: tasks, dependencies, `max_concurrent_runs=1`, trigger, PAUSED, notifications | ORCHESTRATION | none (Jobs API dry-run) | U9 (a)–(d) | standard |

Calibration rule: wave 1 is the pilot (width 1). U7 and U8 are each the first of their pattern class; both
are small enough to *be* their own calibration units, so wave 2 fans out to 2 without a pre-wave. Per-unit
session cost measured in wave 1 re-baselines wave 2/3 (recorded in `05_progress.md`).

Circuit breaker: **3 children reporting the same failure class pauses launches** (T12) — with width ≤2 this
degenerates to "any repeat of a failure class across waves pauses and escalates". Review-round cap **2**
(convention) after the pre-PR self-check; full-re-run cap **3** per unit, then escalate.

Wall-clock projection (parent session time, excluding customer lead time):
wave 0 ≈ 1 session-hour-equivalent (Terraform + dbx.py + 4 contracts + harness); wave 1 ≈ 1 child (~30–45 min)
+ parent live window + review; wave 2 ≈ max(U7, U8) ≈ 45–60 min + one live window (U7 then U8) + review;
wave 3 ≈ 20–30 min. **Serial floor 3, ~3–4 hours end-to-end within one parent session** if reviews turn
inside the session. Lead times that can dominate: R1–R4 (customer answers) — none block waves 1–3 because
each has a default; all four gate STOP E.

## 5. Recon gate spec (mechanical; executable from the plan + `.migration/` alone)

PASS for a unit PR = **all** of: (1) `make tp-smoke` green; (2) `make tp-validate-contracts` green;
(3) `make tp-validate-recon FILE=docs/tech-partnerships/recon/<unit>.recon.json` green with every check
`pass: true`, `run_mode: fixture`, tolerance version `v1`; (4) `idempotency_rerun` present and produced by a run
that wrote rows; (5) `unverified_paths` lists exactly the declared gaps (production encoding, e-mail delivery,
shared drive, prod/UAT hosts) and nothing else; (6) declared source-volume assertion matches the seed
(`NS=<ns>`: 2 files × 50 body rows = 100 records; NS=demo identical). Baseline for every check is the legacy
chain re-run under `scripts/tp-run-deterministic.sh` on the same `ns` — never data the unit produced.

| Unit | Check (population) | Baseline | PASS |
|---|---|---|---|
| U6 | files landed (all `CUSTBILL*.dat` for `ns`); bytes + sha256 per file; `count(*)` `bronze.custbill_raw` per file | seed files; `wc -l` | counts equal, hashes equal, rerun identical |
| U7 | `count(*)` silver (all rows for `ns`) = Σ `wc -l parsed/*.psv`; full row diff on 6 fields keyed `(source_file,line_no)`; quarantine rows = 0 (clean seed); trailer == body per file | legacy `.psv` | 0 mismatched rows, 0 quarantine, rerun identical |
| U7 (anomaly leg) | quarantine reasons vs `gen_history_data.pl` manifest `planted_anomalies` (all planted rows) | manifest | `missing = ∅`, `unexpected = ∅` |
| U8 | gold rows for `ns` vs `finance_billing_*.csv` (all 6 keys): key set, count, total to the cent; exported CSV canonical bytes; independent awk recompute | legacy CSV; awk one-liner | exact on all three legs, rerun identical |
| U9 | Jobs API: task graph, `max_concurrent_runs`, `pause_status`; end-to-end run reproduces U6–U8 verdicts | plan §1 D5 decision; U6–U8 recon | all asserted true |

Parent live proof: one window per wave on NS=demo (`run_mode: live`), committed as
`docs/tech-partnerships/recon/wave<N>/<unit>.live.recon.json`; a wave closes (STOP D notification to
`#ow-tp-status`) only when every unit in it is MERGED and live-green.

Gate posture (for confirmation): **recon-green-required-to-merge per unit**; STOP D = **notify** per wave
(no pause) since width ≤2. Review contract (for confirmation): reviewer = `dhrov.subramanian` (or delegate);
tiering: pilot U6 and money-path U7/U8 get full review; U9 gets the light tier (evidence-format check) if
recon-green.

## 6. Governance mapping (`governance-mapping`)

| Legacy row (`08_governance_inventory.md`) | UC mapping | Status |
|---|---|---|
| No grants/roles/masks exist; access = host file permissions | `ow_tp` owned by the run principal; no additional GRANTs (guardrail) | mapped |
| Fixture SFTP credential (compose placeholder) | secret scope `ow_tp` keys `sftp_*` (D8-3) | mapped |
| Finance recipients (`finance-reports@`, stale `jake@`) | Workflow notification list, Terraform var (D4-1) | mapped, pending R2 |
| `cust_name` (customer legal names) / `cust_id` | no legacy classification exists; **GAP** — PII regime decision is the customer's (D8-4 registered, owner customer, needed before STOP E, not before wave 0) | GAP |
| Cron user unknown; `/opt/etl/.env` unknown | not mappable from export; **GAP**, informational | GAP |
| Lock/temp files in `/tmp` | retired by `max_concurrent_runs=1` | mapped |

## 7. Risk register

| # | Risk | Owner | Handling |
|---|---|---|---|
| R-1 | Production feed encoding/terminator differs from fixtures (D3-3) | customer / U6 | declared gap; contract default; R1 fired |
| R-2 | Silent legacy coercions become quarantines on real data → gold differs from legacy legitimately | U7/U8 | recon reports quarantined rows as a named delta; T7 = 0 only on clean seed |
| R-3 | Incremental gold would diverge from all-time CSV | U8 | contract mandates all-time aggregate per `ns` |
| R-4 | File-arrival trigger unavailable on UC volume | parent (W0-2) | fallback cron `*/15`, decided above |
| R-5 | Copy-then-delete loses files on failure | U6 | verify-then-delete; delete only after hash match |
| R-6 | Float sum vs DECIMAL at scale | U8 | rule in analysis §4.3; any residual reported, never tolerated |
| R-7 | Shared PAT, no service principal (D8-2) | customer | deferred (demo workspace); attribution by `ns`/branch |
| R-8 | Production landing mechanism unnamed (D7-1/D10-6) | customer | volume push during run; R4 fired; gates STOP E only |

## 8. Ledger updates on approval

On STOP C approval: register rows D1-1…D10-6 → DECIDED with the permalink; R1–R4 → FIRED with the permalink;
D-012 → APPROVED with the chosen shape; `05_progress.md` waves rewritten to §4; wave-0 work starts.
