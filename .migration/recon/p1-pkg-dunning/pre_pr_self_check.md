# Pre-PR self-check - p1-pkg-dunning

Every box from `.agents/skills/tp-pre-pr-self-check/SKILL.md`, run on this unit before the
PR was opened. Nothing here is an official harness verdict: recon on this run is graded
DEGRADED with `official_verdict=false`, reason `d10_01_denied`.

| check | result | evidence |
|---|---|---|
| NULL / missing attribution cannot fail open | pass | `fn_overdue_accounts` maps an unmatched or unknown tenant status to the literal `'UNKNOWN'`, never to NULL or to `'active'`; the suspension sweep gates on `status_cd = 10` counted explicitly, so a missing tenant row suspends nothing instead of falling through |
| references scoped to `ow_tp` / `ow-tp-` | pass | catalog `ow_tp`, schema `billing`, Lakebase project `ow-tp-billing`, branch `mig-p1-w2`; recon run with `--target-catalog ow_tp --target-schema billing --allowed-targets-file .migration/allowed_targets.json` |
| no DDL drops / replaces / alters a shared table | pass | the unit creates only `billing.fn_overdue_accounts`, `billing.sp_schedule_dunning` and `billing.sp_suspend_overdue` (`CREATE OR REPLACE` on its own routines). Runtime DML into `billing.tenants` and `billing.subscriptions` is declared; no DDL against them |
| retention and cleanup safe on rerun | pass | the loader upserts by key and never deletes a newer run's rows; no retention job in this unit |
| cleanup paths retain run evidence | pass | evidence lives under `.migration/recon/p1-pkg-dunning/` and is committed, not cleaned |
| no secrets, tokens or real addresses in source, evidence or history | pass | credentials referenced by name only (`OW_TP_ORACLE_RO`, `OW_TP_LAKEBASE_DSN`, `ow-tp/oracle/ow_billing_ro`); grep over the unit's files and evidence finds no value, DSN or address |
| parity-vs-tolerance decision matches the contract | pass | `.migration/03_recon_tolerances.json` used unmodified; money exact, counts exact |
| idempotency proven by an actual rerun | pass | the package's mapped tables were loaded twice through `oracle_to_lakebase_load.py --digest-out`; `load_digest_run1.json` / `load_digest_run2.json` carry different `run_id`s and identical row counts and content hashes. Behavioural idempotency of the sweep itself is listed as unverified below |
| recon values recomputed from the target platform | pass | the harness reads Lakebase `billing` on `mig-p1-w2` directly; `values_recomputed_from_target: true` in the report |
| every unverified path listed | pass | `unverified_paths` in `p1-pkg-dunning.recon.json` and the "unverified" section of `summary.md` |
| machine-readable report present | pass | `.migration/recon/p1-pkg-dunning/p1-pkg-dunning.recon.json`, `"kind": "recon-report"`, `make tp-validate-recon` green |
| capability preflight passed | pass | `.migration/09_capabilities.json` on the base branch; Lakebase credential issued for `projects/ow-tp-billing/branches/mig-p1-w2/endpoints/primary`, Oracle read-only reachable, guard active |
| `make tp-smoke` green | pass | `tp-smoke: all checks passed` |

## Not green, stated rather than hidden

- The three routines were **not executed end to end**: a sweep writes `dunning_attempts`, `notifications`, `tenants`, `subscriptions` and the audit log on the shared wave branch, which are the rows recon compares against Oracle, so running one here would destroy the baseline the wave is measured on. They install and resolve their table references at execution time. The wave gate runs the end-to-end op diff.
- Behavioural idempotency of `sp_suspend_overdue` (a second sweep on the same day writing nothing) needs that sweep and is **unverified**.
- Tiers 5-7 (source-side constraint, index and identity metadata) are **unverified**: the repo-local Oracle JDBC adapter does not read them under `d10_01_denied`.
- Logging is kept: Oracle's `pkg_ow_util.log_msg` calls convert to `billing.log_msg`, which inserts into `billing.billing_audit_log` - a declared runtime write for this batch (wave-3 manifest, ledger D-009), DML only, never its DDL. The line's text is compared against Oracle by the `dunning_log_line_text` op; the insert path was exercised on the wave branch in a rolled-back transaction.
- The verdict is DEGRADED, `official_verdict=false`. Merge evidence, not an official harness verdict.
