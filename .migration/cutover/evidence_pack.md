# Cutover evidence pack: OtterWorks billing, Oracle OW_BILLING -> Atlas ow_tp_mmp_live

Aggregate evidence only. No production row values. Secrets are named, never valued.

## 1. Scope and approved inputs
| Item | Value | Where |
|---|---|---|
| Coverage table | 20 tables + 5 packages + 7 triggers + 2 jobs + 5 sequences, every object dispositioned | `inventory/model.md` |
| Mapping spec | map-1, sha256 `e6fda960...` (STOP B, D-011, wave plan superseded by D-015) | `03_mapping_spec.json` |
| Tolerances | v1, sha256 `03b3c6cc...` (STOP A, D-006/D-010) | `02_tolerances.json` |
| Source baseline | 20 tables; 25,000 / 18,750 / 150,000 / 37 orphans | `baseline/oracle_counts.json` |
| Access | source live read-only `OW_TP_ORACLE_RO_DSN`; target `OW_TP_MMP_TARGET_URI` = readWrite@ow_tp_mmp_live only | `08_connectivity.json`, D-007 |

## 2. Wave reports (all independent, fresh non-migrating sessions, live source + migration cluster)
| Wave | Units | Verdict | Report | PRs |
|---|---|---|---|---|
| 0 | U0-reference (codes, tenants, plans, sequences) | PASS, T3 104/104 | `recon/wave-0:.migration/recon/wave-0/report.md` | #1742 |
| 1 | U1-customers | PASS, T3 33,333/33,333, attribute arrays 8,333 = 8,333 | `recon/wave-1:.migration/recon/wave-1/report.md` | #1743 |
| 2 | U2-invoices + quarantine, U3-billing-core, U4-app-backend | PASS 3/3; U2 T3 168,750/168,750, U3 T3 901/901, U4 T4 app parity 6/6 + post-wave 7/7 | `recon/wave-2:.migration/recon/wave-2/report.md` | #1745, #1744, #1746 |

Wave results: `waves/wave-{0,1,2}.result.json`, briefs `waves/wave-{0,1,2}.brief.md`.

## 3. Parallel-run log
None. The source has no writers other than legacy-billing (DEP-1) and was held static for the whole engagement (every recount equals the baseline). There is no live-write delta to observe, so a parallel-run window was not run (D-020, confirmed at STOP C).

## 4. Watermark recon
Watermark W = the source state equal to `baseline/oracle_counts.json`, verified by a read-only recount. The full recon gate across U0-U4 at W, plus the independent audit, is in `recon/cutover-audit:.migration/recon/cutover/audit.md` (D-021). The customer re-verifies W at freeze (runbook step F2); any drift means a delta reload before repoint.

## 5. Business-logic track
| Legacy object | Mongo path | Evidence |
|---|---|---|
| PKG_PLANS (plan list, plan change, entitlement) | `app/backends/mongo.py` | parity suite 45/45 on fixture; T4 ops live 6/6 |
| PKG_RATING (usage ingest via usage-bridge, rating) | `mongo.py`, occurred_at truncated to seconds as TIMESTAMP(0) | parity suite |
| PKG_INVOICING (preview, issue, invoices, lines) | `mongo.py`, Decimal128, issued tax rounded to 2dp | parity suite; post-wave ops 7/7 |
| PKG_DUNNING (on-demand admin endpoint) | `mongo.py` | parity suite |
| PKG_OW_UTIL.log_msg (autonomous audit) | separate insert outside the caller transaction, id from `sequences` | parity suite |
| TRG_SUB_NO_UNCANCEL, TRG_USAGE_EVENTS_CHECK, TRG_SUBSCRIPTIONS_HIST, TRG_BILLING_AUDIT_LOG_ID | reimplemented in `mongo.py` | parity suite |
| TRG_CUSTOMER_MASTER_SEQ / _HIST, TRG_ENTITY_ATTR_VALUE_SEQ | not ported: no app path writes those tables | coverage table |
| JOB_NIGHTLY_DUNNING, JOB_PURGE_AUDIT_LOG | not ported: DISABLED, 0 runs (DEP-3) | census_dba.json |
| admin `/billing-report` (`reports.py`) | same shapes, `source.engine=mongodb` | T4 ops; parity suite |

Every legacy-billing path repoints. The only legacy consumer that does not repoint is the CUSTBILL extract (DEP-2), stated first in the runbook.

## 6. Open issues and dispositions
| ID | Issue | Disposition |
|---|---|---|
| OI-1 | All 50 customer/invoice tenant_id values are absent from TENANTS in the source itself | Carried exactly; source property; no fix |
| OI-2 | U2 (#1745) not harness merge-eligible: `invoices.lines` embed is scoped (orphans excluded by design), so the harness skips its extra-element check | Closed by the verifier's full-population probe (every lines array equals its source lines); merge is a human call at STOP C |
| OI-3 | `subscriptions_hist`, `billing_audit_log` are empty in the source | Vacuous PASS; informational |
| OI-4 | `RECON_REDACT_SALT` not provisioned; live artifacts use unsalted hashes | Accepted: artifacts hold aggregates only; provision a salt for future runs |
| OI-5 | Empty `_connectivity_probe` collection left in `ow_tp_mmp_live` from the STOP A probe | Harmless; customer may drop it after cutover |
| OI-6 | `02_tolerances.md` named the quarantine collection in plural | Doc typo fixed; `02_tolerances.json` was always authoritative |
| OI-7 | compose hardcoded `BILLING_BACKEND: oracle` for legacy-billing; 3 ruff issues in U4 test files | Fixed on #1746 (compose passes `BILLING_BACKEND`, `BILLING_MONGO_URI`, `BILLING_MONGO_DB` through; defaults unchanged) |
| OI-8 | No PR is merged yet (hard mode, auto_merge=false) | Merge order in the runbook section M; required before post-STOP C verification |

## 7. Dependency register
`07_dependency_register.md`: DEP-1 (writers) DONE via U4; DEP-2 (CUSTBILL extract) DEFERRED, owner customer billing/ETL team; DEP-3 (jobs/triggers) DONE (ported or dispositioned); DEP-4, DEP-5 RESOLVED; DEP-6 (repoint) customer-held, this runbook.
