# Pipeline 2 — OtterWorks finance close (CUSTBILL batch chain) → Lakeflow

**STOP C artifact.** Decision required: approve this plan, the record contract, and the
schedule model, so waves 1–4 can start.

- Record contract: [`Pipeline2_custbill_record_contract.md`](Pipeline2_custbill_record_contract.md)
- Schedule model: [`Pipeline2_schedule_model.md`](Pipeline2_schedule_model.md)
- Target conventions: [`OtterWorks_target_state.md`](OtterWorks_target_state.md)
- Census (accepted at STOP B): [`OtterWorks_inventory.md`](OtterWorks_inventory.md)

Working branch and PR base: `tp-run/databricks-20260915T045714Z`. One PR per unit.
Pipeline 1 is still merging into the same branch, so every unit rebases before its PR.

## 1. Scope

| Unit | Legacy object | Lines | Wave |
|---|---|---:|---:|
| `p2-foundations` | `etl/crontab`, `etl/legacy-extra/crontab`, landing conventions, record contract | 9 + 13 | 0 |
| `p2-sftp-ingest` | `etl/legacy-extra/jobs/sftp_ingest_poll.ksh` | 70 | 1 |
| `p2-custbill-parse` | `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh` | 81 | 2 |
| `p2-finance-close` | `etl/legacy-extra/jobs/finance_excel_report.pl` | 91 | 3 |
| `p2-orchestration` | `etl/legacy-extra/run_all.sh` + both crontabs | 28 | 4 |

Out of scope: the two Perl fixture generators (dropped at STOP B), `docker-compose.sftp.yml`
(local fixture infrastructure), everything under `billing.` and every pipeline 1 unit, the
five Python jobs in `etl/crontab` (pipeline 3 implements them; they inherit this schedule
model), and `MVSPROD` job `CB77340` (outside the estate).

## 2. Target objects and write targets

Every object lives in catalog `ow_tp`. No new clusters; existing serverless SQL warehouse
`565cd2fd713738c4`.

| Unit | Write targets |
|---|---|
| `p2-foundations` | repo only: docs, probe fixture, captured legacy baseline. No Databricks objects. |
| `p2-sftp-ingest` | volume path `/Volumes/ow_tp/bronze/landing/custbill/`; `ow_tp.bronze.custbill_raw`; `ow_tp.bronze.custbill_files` (processed-file ledger) |
| `p2-custbill-parse` | `ow_tp.silver.custbill`; `ow_tp.bronze.custbill_quarantine`; `ow_tp.bronze.custbill_trailer_audit`; pipeline `ow_tp_p2_custbill_ingest_parse` |
| `p2-finance-close` | `ow_tp.gold.custbill_finance_close`; volume path `/Volumes/ow_tp/gold/exports/custbill/` |
| `p2-orchestration` | jobs `ow_tp_p2_custbill_ingest`, `ow_tp_p2_finance_close` (both PAUSED) |
| recon baseline (wave 0, one owner) | `ow_tp.bronze.custbill_legacy_baseline_psv`, `ow_tp.bronze.custbill_legacy_baseline_close` |

**Transitive writes.** Pipeline 1 lost two waves to an undeclared write: a util package wrote
an audit log from inside every other package. The equivalent trace here: each legacy script
writes a `/tmp` lock file, `sftp_ingest_poll.ksh` writes `incoming/` **and** `archive/`,
`parse_custbill_fixedwidth.sh` renames its input to `.done` (a write to the *ingest* unit's
output directory), and `finance_excel_report.pl` writes both `.csv` and `.xls` plus a sendmail
pipe. Every one of those is accounted for above or explicitly dropped; the `.done` rename is
why `p2-custbill-parse` declares the bronze file ledger as a write target even though the
ledger is conceptually the ingest unit's.

No target above collides with any pipeline 1 unit (all of which sit under `ow_tp.silver`/
`ow_tp.gold` with `invoice`/`customer`/`usage`/`dunning`/`plan` names, or in the Lakebase
`billing` schema) or with anything pipeline 3 has declared.

## 3. Decisions to record

| id | Decision | Recommendation | When |
|---|---|---|---|
| **P2-D01** | The legacy can parse a half-written file (1-second double-stat, then parse 5 minutes later). The target lands atomically, so that can no longer happen. | Accept the fix: remove the race. It changes output only on a day the legacy would have produced a corrupt report. | STOP C |
| **P2-D02** | Expectation failures are copied to quarantine **and still flow through**, because the legacy processes them. Quarantine is observability, not a filter. | Accept for the migration. Turning any expectation into a real filter is a post-cutover change. | STOP C |
| **P2-D03** | A `\|` byte inside a sliced field shifts every downstream field and corrupts the aggregation (contract §5). The target reproduces this by aggregating a re-split of the rendered psv line. | Reproduce the bug. Fixing it silently would break parity. | STOP C |
| **P2-D04** | Schedule timezone and the date stamp in `finance_billing_<YYYYMMDD>`. | `UTC`. Flag: if finance reads that stamp as a local business date, cutover shifts a day boundary. | STOP C |
| **P2-D05** | The Sunday 06:00 `run_all.sh` re-run is a near no-op that re-emits the same totals under a new filename. | Drop it. Keep a weekly full-recompute job only if finance relies on the Sunday file existing. | STOP E |
| **D4-01 / D-007** | Consumer: gold table + byte-compatible CSV/`.xls` export, sendmail dropped. | Already decided by the parent; confirm at STOP E. If a human consumer surfaces, repoint to the gold table or the volume export, never a revived mail pipe. | STOP E |
| **D3-01** | Does `CB77340` keep dropping to SFTP, or is it repointed at the landing volume, and who makes that change? | Not mine. User decision. | STOP E |

### Behaviour changes (named, not buried)

Approved at STOP C on the condition that they are stated in every wave brief and in the
STOP E packet, in prose — a reader must not have to open a recon JSON to learn we changed
what the legacy chain did.

| id | Behaviour change | Blast radius |
|---|---|---|
| **P2-D01** | The legacy can parse a half-written file; the target cannot. Landing is atomic (staging name + rename) and the parse is a dependency edge, not a 5-minute guess. | Output differs from the legacy only on a run where the legacy would have produced a corrupt report from a partial file. Cannot be exercised against pinned inputs, so it is untested by construction and listed as an unverified path in every recon report as well as here. |
| — | The target does not delete source files, does not write `/tmp` lock files, and fails loudly where the legacy ends a stage in `\|\| true`. | Operational only; no effect on row content. |
| — | sendmail is dropped in favour of the job's failure notification (D4-01/D-007). | No live consumer exists to lose. |

Everything else in this plan reproduces the legacy exactly, corruption included.

## 4. Waves

Serial by construction — the chain is four dependency-ordered stages, so every wave is one
batch. `migration-fanout`/`run_workflow` is therefore **not** used: it exists for waves with
more than one batch, and forcing a one-child workflow would add the pipeline-1 environment
failure mode for no parallelism. Manifests are still written in the fan-out shape
(`.migration/waves/p2-wave-<n>.json`) so the collision check and the circuit breaker apply,
and wave 4 closes with an independent verifier that migrates zero units and writes nothing.

| Wave | Unit | Depends on | Verify depth |
|---:|---|---|---|
| 0 | `p2-foundations` | — | none (no data) |
| 1 | `p2-sftp-ingest` | wave 0 contract | full row parity on bronze |
| 2 | `p2-custbill-parse` | wave 1 | full row parity on silver + quarantine set equality |
| 3 | `p2-finance-close` | wave 2 | full row parity on gold + byte compare on CSV/`.xls` |
| 4 | `p2-orchestration` | wave 3 | structural: job graph, retries, PAUSED state, no live schedule |

Circuit breaker: 3 same-class failures halts the wave and I stop and report. Recon re-runs
capped at 3 per unit.

## 5. Recon gate

Source is files, not Oracle, so the harness's untested-Oracle-adapter limitation does not
apply. Both sides are read through the tested Databricks adapter and the official harness
verdict is the merge gate.

How the two sides stay independent — the rule is *never reconcile output against the artifact
that produced it*:

1. **Source side.** Run the real legacy scripts over a pinned fixture set under the
   `legacy-etl-demo` harness. Their `.psv` and `.csv` outputs are loaded verbatim into
   `ow_tp.bronze.custbill_legacy_baseline_*` and never touched again.
2. **Target side.** The Lakeflow pipeline reads the **same raw `.dat` inputs** and recomputes
   everything from scratch. It never reads the baseline tables.
3. The harness compares the two, recomputing from the target platform.

Tolerances are the frozen ones in `.migration/03_recon_tolerances.json` — money exact, row
counts exact, 1e-9 relative on other floats, dates ISO-canonicalized, anomalies as sets.
Changing them needs a human decision recorded by the parent.

Idempotency is proven by an actual second run of each unit, not asserted.

### What recon does not cover

Named up front, repeated in every unit PR:

- **Structure, not rows.** Grants, table properties, column comments, Unity Catalog
  permissions and volume ACLs are outside row-level parity. Pipeline 1 passed row parity with
  constraints and grants missing; the same hole exists here.
- **The partially-written-input race.** Recon runs against pinned, stable fixtures, so the one
  real-world condition where legacy and target legitimately disagree (P2-D01) is untested by
  construction.
- **Timing and orchestration.** The job graph is verified structurally; no recon proves the
  converted schedule produces the same output *at the same time* as cron.
- **Scale.** The fixture set is ~100 records. Nothing here exercises a production-volume file,
  and C-7.9's double-precision bound (`abs(total) < ~9.0e13`) is reasoned, not measured.
- **Mail.** The sendmail step is removed, so there is nothing to reconcile.
- **Upstream.** Whatever `CB77340` does.

## 6. Capability contract

```json
{
  "identity": "2e90bc1d-e9a1-4703-8c48-ad28ebb1864d",
  "host": "https://dbc-8bc9474f-40ae.cloud.databricks.com",
  "catalogs": ["ow_tp"],
  "guard_mode": "block",
  "stop_mode": "soft",
  "ready": true
}
```

`factory-doctor` runs before every wave. Current state: 14 ok, 1 warn, 2 fail. The warn is
`recon_drivers` (`databricks-sql-connector` not installed — installed before the first live
recon in wave 1). The two fails are `delete_evidence` and `source_principal_read_only`, which
need per-unit ids and a source-secret name; they clear once the unit mapping specs in
`.migration/units/p2-*/` exist, which this PR adds. Identity, host, warehouse, allowlist,
hook loading and stop mode all pass.

## 7. Repo gates before each PR

`make tp-validate-contracts`, `make tp-validate-recon`, `make tp-validate-schemas`,
`make tp-smoke`, plus the repo's `tp-pre-pr-self-check` checklist and the unit's live recon
verdict. No PR body names an individual or carries a credential value.

## 8. Not done by this child

No production repoint, no schedule activation, no cutover, no merge of my own PRs, and no
approval of any stop on the user's behalf. Pipeline 2 parks at STOP E.
