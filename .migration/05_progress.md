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
| Quarantine reason codes | `COMPLETE` | Parent | `.migration/11_quarantine_codes.md`; closed code set with no `OTHER`. |
| Golden baselines | `COMPLETE` | Parent | `.migration/12_golden_baselines.md`; 24 immutable Oracle transcripts under `procs/oracle/transcripts/`, pinned by `ORACLE_SOURCE_SHA=0d326cad54d94cd64e8abb53585b37436eaad2193fdc15ba3596fbb8db3f0d55` and verified against the Oracle SQL source. |

Wave 0 has no remaining items.
