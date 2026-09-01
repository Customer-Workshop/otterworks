# 03_recon_tolerances.md — THE parity contract

**Version 1 (2026-09-01) — PROPOSED, pending STOP A.** Every recon report cites this version.

## Recon mode
**LIVE dual-run.** The legacy chain is re-executed from the deterministic seed for the same `ns`
(`make legacy-etl-gen-data NS=<ns>` + `make legacy-etl-run ...` under an isolated
`OTTERWORKS_LEGACY_ROOT`, deterministic clock via `scripts/tp-run-deterministic.sh`) and its
outputs are the baseline. Children run in `run_mode: fixture` (local fixture layer / LocalStack);
only the parent's `run_mode: live` pass on NS=demo counts as proof. There is no live production
legacy host in the loop and none is requested; this is not DEGRADED mode because the baseline is
the legacy code itself executed on identical inputs, not a sample.

## Tolerance table (surface: PIPELINE for all rows)

| # | Data type / check | Tolerance | Population | Tag |
|---|---|---|---|---|
| T1 | Row count (silver vs `.psv`, bronze vs source records) | exact (0) | every table, per `ns` | PROPOSED |
| T2 | Money (amount, totals) | exact to the cent, DECIMAL(18,2) vs legacy `%.2f`; no float compare | every money column/aggregate | PROPOSED |
| T3 | Dates | exact ISO `YYYY-MM-DD` after legacy reformat; invalid legacy dates → quarantine, counted separately (T7) | every date column | PROPOSED |
| T4 | Strings (id, name, currency, record type) | byte-exact after trailing-space trim (legacy `cut` trims); collation-insensitive not allowed | every string column | PROPOSED |
| T5 | Aggregates (gold finance report: 6 rows × count, total) | exact count, exact total to the cent, exact set of (currency, record_type) keys | gold table vs `finance_billing_*.csv` | PROPOSED |
| T6 | File artifacts (Glacier JSONL.gz, `activity_report.json`, CSV exports) | byte-identical after canonicalisation (gzip `mtime=0`, JSON key order sorted, `\n` line ends); ordering of unordered legacy outputs canonicalised by sort before compare | every file the legacy job writes | PROPOSED |
| T7 | Quarantine rate on the clean NS=demo seed | exactly 0 rows | silver quarantine tables | PROPOSED |
| T8 | Planted anomalies | compared as sets: `missing` = ∅ and `unexpected` = ∅ | contract `planted_anomalies` with `must-detect` | PROPOSED |
| T9 | Idempotency | rerun for the same `ns` yields identical row counts and identical file bytes | every unit | FACT (recon schema requires `idempotency_rerun`) |
| T10 | Nondeterministic legacy behaviour (unordered `awk` hash output, S3 listing order) | canonicalise by sort on the natural key before comparing; ties resolved by full-row sort | any unordered output | PROPOSED |
| T11 | Timestamps written by the job itself (`ingested_at`, report date in filename) | excluded from parity; must exist and be non-null | metadata columns only | PROPOSED |
| T12 | Halt threshold (circuit breaker) | 3 children reporting the same failure class → pause launches | every population, whole wave | FACT (kit default) |

## Recon economics
- Row-diff size threshold: **full row diff** up to 10^5 rows per `ns`; above that, keyed stratified sample (10%, min 1,000) plus full aggregates. Estate is ≤10^4 rows/ns, so full diff applies everywhere this run. PROPOSED.
- Legacy-query concurrency cap: **N/A** (no live legacy engine). Local legacy re-runs are per child, isolated by root. Databricks live recon: exactly **one** parent window per wave, no concurrent children on NS=demo. PROPOSED.

## Amendment procedure
A tolerance changes only by explicit user approval recorded in `06_decisions.md`. The change is
written as a new dated version below this table with the old row preserved (struck through), and
names the re-verification scope: every already-merged unit whose recon cited the old version is
re-run under the new one before the next wave closes.

## Version history
- v1 2026-09-01 — initial, PROPOSED at STOP A.
