# Open issues with dispositions (playbook 5 step 2)

| ID | Unit | Issue | Disposition | Owner |
|---|---|---|---|---|
| OI-1 | all | No live/snapshot recon against a migration cluster; nothing merge-eligible (offline policy) | **blocks STOP C**; customer DBA runs the harness in-network (runbook §1.2) | customer DBA |
| OI-2 | all | No parallel-run log, no watermark recon | blocks STOP C; produced only after OI-1 | customer DBA |
| OI-3 | u-02 | 13 `relatedAcctIds` malformed-CSV diffs remain (`harness_gap_csv_unparseable`): `csv_to_array` has no quarantine-aware parameter | harness fix (add `unparseable: quarantine` to `csv_to_array`) or explicit risk-accept row at STOP C; 13 rows are quarantined and counted | plugin maintainer / customer |
| OI-4 | u-04 | BILLING_AUDIT_LOG has 0 fixture rows: audit-log path passes trivially, unverified | verify in the customer live run (non-empty table) | customer DBA |
| OI-5 | u-06 | 37 orphan INVOICE_LINE rows (no parent header) quarantined, not embedded | data-owner decision before repoint: discard, or parent them in Oracle first (source read-only for Devin) | customer billing team |
| OI-6 | u-06 | Where-scoped embed: harness never reports `merge_eligible=true` and warns "extra target elements not checked" (known limitation, D-018) | harness limitation to be lifted or a countersigned manual element-count check in the customer run | plugin maintainer |
| OI-7 | u-07 | F1 (low): `ow_util.code_desc(type, None)` raises `TypeError`; Oracle returns `UNKNOWN(-1)` | fix on PR #1725 before any live run; unreachable from current callers | orchestrator (next code handoff) |
| OI-8 | u-11 | F2 (low): `suspend_overdue` cutoff compares full timestamp vs Oracle day-granular `TO_CHAR` | fix on PR #1726 before any live run; unreachable while `issue_invoice` writes midnight-only | orchestrator |
| OI-9 | u-07/u-08 | committed `mapping.subset.json` labelled map-draft-2 while content is verbatim map-draft-3.1 | relabel on PR #1725 before any live run | orchestrator |
| OI-10 | u-01..u-06 | Waves 1-2 independent verifier `NOT RUN` (workflow reported it; recorded in result files) | covered by the customer live run + independent audit (`cutover/audit.md`) | customer DBA |
| OI-11 | register | D4-3 production counts / snapshot manifest FOUND, not supplied; D2-4 no-out-of-repo-reader confirmation pending | customer to supply before STOP C | customer DBA |
| OI-12 | tooling | `make tp-smoke` Go stage cannot run on the Devin box (`go: command not found`); `make -C services/legacy-billing tp-smoke` target does not exist | rely on repo CI for Go/Node stages; blueprint gap | org env owner |
