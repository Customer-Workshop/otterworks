# Demo Runbook — Databricks + Devin: billing history, and what happens when recon fails

**Duration:** ~10 minutes on stage. Everything is staged the night before; the
only thing that runs live is the failure loop (drift → Databricks catches it →
Devin fixes it), and even that is *triggered* at the start and *revealed* at the
end so its latency is hidden behind the other beats.
**Story:** OtterWorks' 1998-vintage CUSTBILL chain didn't just run nightly — it
piled up years of monthly billing drops nobody can query. This demo moves that
history onto the lakehouse, proves it matches the legacy estate to the cent,
then breaks reconciliation on purpose so Databricks catches it, Devin fixes it,
and the PR proves it.

This runbook is the platform half of the Databricks track. The conversion
fan-out (one Devin child session per legacy script) is
[`runbook-databricks.md`](runbook-databricks.md); this one assumes those jobs
exist and focuses on history, platform capabilities, and the failure loop.

Everything is namespace-scoped. All numbers are deterministic for a given
namespace, so on-screen output matches this document exactly.

## Playbooks

| Macro | Playbook id | Role |
|---|---|---|
| `!tp_dbx_1_stage` | `playbook-2943e3f2b522444f85c2f61a09743701` | Parent: stages the whole demo, fans out children, leaves it rehearsal-ready |
| `!tp_dbx_2_convert` | `playbook-292f26f986d743d2832c427bd9992e84` | Child: legacy-script conversion fan-out (behaviour unchanged) |
| `!tp_dbx_3_backfill` | `playbook-377124a498024799a93ed571e5612cc0` | Child: multi-year history load + per-year recon + Delta time travel |
| `!tp_dbx_4_platform` | `playbook-eea8d3bfe3f14691a7895c45d2743d99` | Child: declarative pipeline, lineage, dashboard, alert, recon job + failure-to-Devin loop |

## Namespaces

Two namespaces, deliberately:

| Namespace | Role |
|---|---|
| `demo` | The story. Dashboard, lineage, Delta history, Workflow graph. Green, never drifted, never broken on stage. |
| `live<MMDD>` (e.g. `live0819`) | The live beat only. Staged identically, then broken in front of the room. If the loop misbehaves, `demo` is untouched. |

Rehearsal namespaces are a third, throwaway kind — torn down the same night.

## Staged state (`NS=demo`)

| Layer | Object | Content |
|---|---|---|
| Landing | `/Volumes/ow_tp/bronze/landing/demo/history` | 72 monthly CUSTBILL drops, 2019–2024, original file names and periods (the volume stamps upload time, so drop dates come from `source_period`, not file mtimes) |
| Bronze | `ow_tp.bronze.custbill_history_raw_demo` | 3,024 raw lines incl. headers/trailers, with source file/period/year |
| Silver | `ow_tp.silver.custbill_history_demo` | 2,856 valid billing records |
| Silver | `ow_tp.silver.custbill_quarantine_demo` | 30 planted anomalies (bad dates, non-numeric amounts, trailer mismatch) |
| Gold | `ow_tp.gold.custbill_annual_demo` | 36 annual finance rows, 1,439,098,122 cents total |
| Ops | `ow_tp.ops.history_expectations_demo` | 36 legacy-derived expectation rows (the recon source of truth) |
| Ops | `ow_tp.ops.recon_runs_demo` | recon history, one row per run |
| Dashboard | `ow_tp_billing_migration_demo` | published AI/BI dashboard — the backfill beat's screen (page 1 from the harness; the conversion page is added live by the platform child) |
| Pipeline | `ow_tp_custbill_history_dlt_demo` | same shape, quarantine rules as declared expectations |
| Job | `ow_tp_billing_history_recon_demo` | recon SQL + `AT_LEAST_ONE_FAILED` Devin notifier, **schedule PAUSED** |

Row counts are namespace-independent; the cent totals are not — the generator
seeds amounts per namespace, so `live<MMDD>` legitimately reports a different
total with all recon checks green.

## The dashboard is the demo screen

`make dbx-showcase CMD=dashboard NS=<ns>` builds and **publishes**
`ow_tp_billing_migration_<ns>`. Published dashboards render stored results, so
demo-day page loads do not depend on a warm warehouse; refresh only during the
live beat, where recomputation is the point.

Page 1, "Six years of billing history" (from the harness, identical every run):

- counters — years of history, monthly drops loaded, billing records, total
  billed, **recon checks failing now** (the tile that goes red in the live beat)
- billed amount by year — the history nobody could query
- **Legacy vs lakehouse, to the cent** — per-year legacy expectation, lakehouse
  actual, and a Difference column that must be all zeros
- records the legacy parser silently billed wrong (quarantine, by reason), and
  "years off by a cent or more" (must read 0)

Page 2, the conversion page, is built **live by the platform child** during the
run (see `!tp_dbx_4_platform`): the finance report's six currency×type rows
from the converted gold table next to the legacy CSV landed as
`ow_tp.ops.legacy_finance_report_<ns>`, the delivery record that replaced the
silent sendmail pipe, ingest/parse counters, and the legacy-script→PR receipt.
The base branch stays silent about converted outputs, so the child derives the
table names from what its run actually merged and must verify every widget
returns rows before publishing.

## Night before — staging checklist

Stage under a persistent path, not `/tmp` (a fresh VM wipes it):

```bash
export OTTERWORKS_LEGACY_ROOT=$HOME/otterworks-legacy
export DATABRICKS_DEMO_HOST=... DATABRICKS_DEMO_TOKEN=...   # PAT: sql, uc, jobs, secrets, workspace, files
```

1. Full staging for both namespaces (for each of `demo` and `live<MMDD>`):

   ```bash
   make legacy-etl-gen-history NS=<ns>
   make dbx-showcase CMD=provision NS=<ns>
   make dbx-showcase CMD=land NS=<ns>
   make dbx-showcase CMD=expectations NS=<ns>
   make dbx-showcase CMD=backfill NS=<ns>
   make dbx-showcase CMD=recon NS=<ns>          # 49 checks / 0 failed / anomalies 30/30
   make dbx-showcase CMD=recon-job NS=<ns> ARGS="--webhook-url <devin-webhook>"
   make dbx-showcase CMD=dashboard NS=<ns>      # builds + publishes page 1
   ```

   (`demo` usually already exists — the staging commands are idempotent.)

2. Rehearse the live loop end to end on a **throwaway** namespace: drift →
   `run-job` red → webhook spawns the remediation session → audit PR → green
   rerun. Record the red run URL, the session URL and the PR URL — they are the
   fallback if the live loop stalls on stage. Then tear the namespace down and
   check the negative verification output.

3. Confirm nothing is armed to run unattended, then walk away:

   ```bash
   make dbx-showcase CMD=demo-preflight NS=demo
   make dbx-showcase CMD=demo-preflight NS=live<MMDD>
   ```

## Demo morning — one command per namespace

```bash
export OTTERWORKS_LEGACY_ROOT=$HOME/otterworks-legacy
make legacy-etl-gen-history NS=demo              # regenerate the local drops (deterministic)
make legacy-etl-gen-history NS=live<MMDD>
make dbx-showcase CMD=demo-preflight NS=demo
make dbx-showcase CMD=demo-preflight NS=live<MMDD>
```

`demo-preflight` is read-only: it checks the staged tables against the
generator manifest (the shared workspace means another session *can* rewrite a
namespace overnight), re-runs the recon checks without rebuilding or recording
anything, and confirms the job schedule and alert are PAUSED and the dashboard
exists. Any FAIL line means re-stage that namespace before presenting.

Then open the published dashboards once (warms the warehouse for the live
beat) and lay out the tabs: `demo` dashboard, `live` dashboard, the recon job,
Catalog Explorer on `ow_tp.gold.custbill_annual_demo`, and the crontab file.

## Run of show (~10 min)

### T+0:00 — Break it, quietly

On `live<MMDD>`, before saying anything else:

```bash
make dbx-showcase CMD=drift NS=live<MMDD> ARGS="--kind stale"
make dbx-showcase CMD=run-job NS=live<MMDD> ARGS="--no-wait"
```

Say out loud: "a new billing year just arrived and the target hasn't absorbed
it — and nobody has been paged." Leave the job run open in a tab. The webhook
will spawn the remediation session while you tell the rest of the story.

### T+0:30 — Beat 1: the history nobody could query

The legacy side first: `ls $OTTERWORKS_LEGACY_ROOT/sftp-drop/history/2019/` —
fixed-width files, one per month, six years of them, readable only by the Perl
script that produced the finance report. `head -3` one of them.

Then the `demo` dashboard, page 1: six years, 72 drops, 2,856 records, the
by-year bar chart — and the "Legacy vs lakehouse, to the cent" table. The
Difference column is all zeros: the mainframe's own numbers and the lakehouse
agree to the cent, every year. The quarantine table is the second point: the
legacy parser logged trailer mismatches and moved on; those 30 rows are records
the old estate silently billed wrong.

### T+3 — Beat 2: time travel and lineage

Catalog Explorer on `ow_tp.gold.custbill_annual_demo`: the **History** tab is
the answer to "who changed the finance numbers, and what did they look like
before?" (the legacy estate's answer was a `.done` folder), and the **Lineage**
tab resolves landing volume → bronze → silver (+ quarantine) → gold with no
manual annotation. Contrast with
`etl/legacy-extra/ops/RESTART_PROCEDURE.doc.txt`. Terminal equivalents, if the
room is technical:

```bash
make dbx-showcase CMD=timetravel NS=demo ARGS="--table gold"
make dbx-showcase CMD=lineage NS=demo
```

### T+5 — Beat 3: the converted estate

The crontab on one side of the screen (`etl/legacy-extra/crontab` — read the
comments verbatim: "if ingest is still copying when parse starts, parse reads a
half-written file. known issue"; `sleep 600` as dependency management), the
converted Workflow's task graph on the other: explicit `depends_on` edges,
`max_active_runs=1`, retries, a green run.

Then the dashboard's conversion page: the same six currency×type rows the Perl
script mailed to jake@ for twenty years, now produced by a governed job —
legacy CSV and lakehouse side by side, difference zero — plus the delivery
record that replaced the sendmail pipe that silently no-op'd, and the
legacy-script→PR receipt showing who did the conversion work.

### T+7 — Beat 4: Databricks caught it, Devin fixed it

Back to the tabs from T+0. The run is red: `recon_check: FAILED` with a
`raise_error` message naming the failing check ids, and `notify_devin: SUCCESS`
(the run's overall state is `SUCCESS_WITH_FAILURES`, because the notifier task
itself succeeded). The notifier POSTed job id, run id, run URL, namespace and
base branch to the Devin automation webhook, with the shared secret read from
the `ow_tp` Databricks secret scope.

That webhook started *OtterWorks billing-history recon failure —
auto-remediate (Databricks)*, which re-ran recon, diagnosed from the failing
check ids, remediated the smallest correct thing, re-ran the anomaly and
idempotency checks, re-triggered the job to green, and opened one audit PR.
Show the session transcript and the PR side by side — then refresh the `live`
dashboard and watch "Recon checks failing now" go back to 0.

### Fallbacks

| Failure on stage | Answer |
|---|---|
| Webhook didn't spawn a session | Show last night's rehearsal: real red run, real session, merged PR — "here's what it did at 11pm" |
| Remediation still running at T+7 | Narrate the diagnosis live from the transcript; show the rehearsal PR as the finished state |
| `demo-preflight` failed in the morning | Re-stage that namespace (provision → land → expectations → backfill → recon, ~10 min) |
| A widget is slow or errors | The published dashboard renders stored results — don't refresh outside the live beat |

## Cost controls

Leaving the demo staged is cheap; leaving it *scheduled* is what costs money.

- Serverless SQL only. Never create clusters or extra warehouses — the showcase
  tooling refuses to.
- The warehouse auto-stops after 10 minutes; stopped serverless compute bills
  nothing.
- The recon job schedule is created **PAUSED** and the SQL alert is created
  **PAUSED**. Trigger by Run Now for each take. A polling alert or a live
  schedule will start compute on its own, repeatedly, unattended.
- The declarative pipeline uses its own serverless compute — trigger manually,
  never leave it continuous or scheduled.
- Storage is megabytes at demo scale.
- The remediation automation spawns a real Devin session on every red run; it is
  capped at one concurrent run with an ACU limit. Don't arm a schedule against
  it.

`demo-preflight` checks the schedule/alert pause state, so the night-before and
morning gates double as the cost check.

## Teardown

The `demo` namespace is intended to stay staged so history, lineage and the
dashboard stay browsable. `live<MMDD>` and rehearsal namespaces should not
outlive their day:

```bash
make dbx-showcase CMD=teardown NS=live<MMDD>
```

Teardown drops only `ow_tp` objects suffixed with that namespace, then verifies
absence across tables, job, pipeline, alert, dashboard and landed files, exiting
non-zero if anything survived. It never touches unprefixed objects or another
namespace.

## Staged run — 2026-08-18 (run branch `tp-run/databricks-20260818T210550Z`)

Night-before staging for the 2026-08-19 demo. Live-beat namespace: `live0819`.
Rehearsal namespace `reh0818` torn down, negative verification clean.

### Artifacts

| Artifact | URL / value |
|---|---|
| `demo` dashboard (2 pages, published) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/dashboardsv3/01f19b4c3bba14e0ae05b8c9e2c21e70/published> |
| `live0819` dashboard (published) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/dashboardsv3/01f19b49a1801494a53b81a6545d4685/published> |
| `demo` recon job (PAUSED) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/402112166843203> — green run 197477330021785 (`recon_check` SUCCESS, `notify_devin` EXCLUDED) |
| `demo` recon alert (PAUSED) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/sql/alerts/3887578863199005> |
| `live0819` recon job (PAUSED) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/307570744434581> |
| Converted-chain live run (green) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/runs/21546277254446> — `ow_tp_orchestrate_cnvorch` (job 15628905556532), ingest → parse → publish_psv → finance all SUCCESS |
| Lineage (demo) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/explore/data/ow_tp/silver/custbill_history_demo?activeTab=lineage> |

### Failure-loop rehearsal fallback (real, from `reh0818`)

| Beat | URL |
|---|---|
| Red run (`recon_check` FAILED, `notify_devin` SUCCESS) | <https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/runs/86637818958925> |
| Spawned Devin remediation session | <https://partner-workshops.devinenterprise.com/sessions/c7356ab84ae4413aae300383f56fd748> |
| Audit PR (merged into run branch) | <https://github.com/Cognition-Partner-Workshops/otterworks/pull/1193> |
| Green rerun after remediation | <https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/runs/949261426411542> |

### Observed numbers

- Both namespaces: 72 files, 3,024 bronze rows, 2,856 silver, 30 quarantined,
  36 gold rows, recon 49 checks / 0 failed, anomalies 30/30 (0 missing, 0
  unexpected), idempotency rerun pass.
- Gold cents: `demo` 1,439,098,122; `live0819` 1,426,466,253 (namespace-seeded).
- `demo-preflight` passed for both namespaces; every schedule and alert PAUSED.

### Merged PRs (all into the run branch)

- #1192 history backfill (`demo`), #1194 cnvparse, #1195 cnvingest,
  #1196 cnvfinance, #1197 cnvorch, #1198 platform showcase,
  #1193 rehearsal audit PR (Devin remediation).
