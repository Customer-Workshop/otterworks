# 01_conventions.md — working conventions (appended, never rewritten)

Target state: `docs/tech-partnerships/OtterWorks_ETL_target_state.md` (v1.0-draft). This file
holds process conventions only; engineering conventions live there.

## Repo roles
| Role | Location |
|---|---|
| SOURCE (legacy, read-only) | `etl/**` on `tech-partnerships` (identical on the run branch; never edited) |
| TARGET (migrated code) | `databricks/<unit>/`, `infrastructure/terraform-databricks/` on `tp-run/databricks-20260901T205308Z` |
| DOCS | `docs/tech-partnerships/` (target state, contracts, recon reports) + `.migration/` (ledgers) |
| Designated write area (cloud) | Unity Catalog `ow_tp` only; AWS `ow-tp-*` prefixed serverless resources only. Nothing else is ever written. |

## Branches and PRs
- Run branch: `tp-run/databricks-20260901T205308Z` (off `tech-partnerships`). Every PR targets it. `main` and `tech-partnerships` are never targets.
- Child branches: `migrate/<wave>-<unit>` off the run branch, e.g. `migrate/w1-parse_custbill_fixedwidth`.
- Parent wave-0 code (Terraform, `dbx.py`, contracts): `migrate/w0-<topic>` via PR. `.migration/` ledger and DOCS artifact updates are committed directly to the run branch by the parent (no PR), as the front-door intake was.
- **One PR per unit**, never a stack. Title `[DBX w<N>] <unit>: <one-line>`. Body sections: Contract, What changed, Recon evidence (path to `<unit>.recon.json`, `run_mode`, pass/fail per check, unverified paths), Deficiencies retired (ids from the contract), Skill feedback.
- Review budget 2 rounds; `.agents/skills/tp-pre-pr-self-check` before opening; `make tp-smoke`, `make tp-validate-contracts`, `make tp-validate-recon FILE=...` must pass.
- A unit is DONE only when its PR is MERGED into the run branch.

## PR-evidence contract
Every unit PR carries: `docs/tech-partnerships/contracts/<unit>.contract.json` (schema-valid),
`docs/tech-partnerships/recon/<unit>.recon.json` (schema-valid, `run_mode: fixture` for
children), and the recon script that produced it. Parent re-runs recon live on NS=demo once per
wave and commits `docs/tech-partnerships/recon/wave<N>/<unit>.live.recon.json`.

## Namespaces
- Children: `NS=<unit-short>-w<N>` local fixture namespace with its own `OTTERWORKS_LEGACY_ROOT=/home/ubuntu/otterworks-legacy-<ns>`; children never write to Databricks NS=demo.
- Parent: `NS=demo` (persistent, left up and browsable after the run).
- Deterministic clock for baselines: `scripts/tp-run-deterministic.sh` with `TZ=UTC LC_ALL=C`.

## Audience-facing style
Slack, Jira OTD, Confluence OWTP, PR bodies: the estate is a genuine production legacy system.
Messages: 2-4 sentences, the one decision first, recommended answer, exact approval reply, link.

## Ledger discipline
`04_dependency_register.md`, `05_progress.md`, `06_decisions.md` updated after every step by the
parent; children never edit `.migration/`.
