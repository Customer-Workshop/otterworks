# 05 — Migration progress

Status flow: `NOT_STARTED → IN_FLIGHT → PR_OPEN → RECON_GREEN → MERGED`

| Unit | Status | Owner | Evidence |
|---|---|---|---|
| `PKG_RATING` | `NOT_STARTED` | Unassigned | No child PR or recon report yet. |
| `PKG_INVOICING` | `NOT_STARTED` | Unassigned | No child PR or recon report yet. |

## Wave 0 — parent-owned foundation

| Area | Status | Owner | Evidence |
|---|---|---|---|
| Contracts | `COMPLETE` | Parent | Nine OW_BILLING Databricks contracts authored; `make tp-validate-contracts` reports `validated 9 contracts file(s) / PASS`. |
| Capability preflight | `COMPLETE` | Parent | `.migration/07_access_checklist.md` records `probes: 11, denied: 0`. |
| Shared Terraform | `COMPLETE` | Parent | `infrastructure/terraform-databricks/` shared stack landed; children add only `jobs_<unit>.tf`. |
| Dictionary | `COMPLETE` | Parent | `.migration/09_semantic_dictionary.md` is in place from PR #1358. |

Remaining wave-0 work: capture golden baselines from `procs/transcripts/` and
add the quarantine reason-code table if it is not already present in
`.migration/`.
