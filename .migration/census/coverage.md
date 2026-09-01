# Phase 2 — object-level coverage table

Every OW_BILLING object is exactly one of: MIGRATION UNIT / SHARED-REFERENCE /
PROPOSED-UNUSED (with evidence) / CONFIRMED EXCLUSION. Evidence citations refer to
`census/raw/*.txt` and repository paths recorded there.

## Tables (20/20 covered)

| Object | Rows | Bucket | Target | Unit | Evidence |
|---|---|---|---|---|---|
| CODES | 32 | SHARED-REFERENCE | `codes` | U0 | reports.py STATUS/LINE_SQL lookups; PKG_OW_UTIL.f_code_desc; TRG_USAGE_EVENTS_CHECK (access_patterns.txt:10-21, 35-38, 132) |
| TENANTS | 69 | SHARED-REFERENCE | `tenants` | U0 | PKG_PLANS.fn_entitlement, PKG_INVOICING tax_exempt_yn, PKG_DUNNING joins/updates (access_patterns.txt:40-45, 64-69, 77-90) |
| PLANS | 3 | SHARED-REFERENCE | `plans` | U0 | PKG_PLANS.fn_list_plans/fn_entitlement, PKG_RATING, PKG_INVOICING (access_patterns.txt:40-52, 64-69) |
| FIXTURE_META | 1 | SHARED-REFERENCE | `fixture_meta` | U0 | estate bookkeeping row; no runtime reader found; migrated verbatim (trivial) to keep scope carve-out-free |
| CUSTOMER_MASTER | 25,000 | MIGRATION UNIT | `customers` | U1 | reports.py BALANCES_SQL; probe scripts/tp_pain/mongodb.py (appcode.txt:15-52) |
| ENTITY_ATTR_VALUE | 8,333 | MIGRATION UNIT (embedded) | `customers.attributes[]` | U1 | 100% ENTITY_TYPE='CUSTOMER', 0 rows without matching CUST_ID (live probe 2026-09-01); no independent query path found (access_patterns.txt:181-183) — always keyed by entity |
| CUSTOMER_MASTER_HIST | 0 | MIGRATION UNIT | `customer_master_hist` | U1 | trigger-maintained full-row history (TRG_CUSTOMER_MASTER_HIST); append-only audit → own collection |
| INVOICE_HEADER | 18,750 | MIGRATION UNIT | `invoice_feed` | U2 | reports.py STATUS_SQL/LINE_SQL (bulk conversion-feed pair; distinct from transactional INVOICES) |
| INVOICE_LINE | 150,000 | MIGRATION UNIT (embedded) | `invoice_feed.lines[]` | U2 | LINE_SQL inner join header→line by invoice_id (access_patterns.txt:16-21); 37 orphan rows → quarantine (STOP A tolerance) |
| SUBSCRIPTIONS | 69 | MIGRATION UNIT | `subscriptions` | U3 | PKG_PLANS entitlement/change-plan, PKG_RATING covering-row reads, PKG_DUNNING suspend (access_patterns.txt:40-52, 86-98) |
| SUBSCRIPTIONS_HIST | 0 | MIGRATION UNIT | `subscriptions_hist` | U3 | TRG_SUBSCRIPTIONS_HIST old-row copies; append-only audit → own collection |
| USAGE_EVENTS | 814 | MIGRATION UNIT | `usage_events` | U4 | PKG_RATING compute_rating / fn_usage_summary tenant+date scans (access_patterns.txt:47-57) |
| RATING_PERIODS | 3 | MIGRATION UNIT | `rating_periods` | U4 | PKG_RATING sp_finalize_rating upserts; joined to RATING_RESULTS for rollover (access_patterns.txt:49-62) |
| RATING_RESULTS | 3 | MIGRATION UNIT | `rating_results` | U4 | same as above; harness probes join results↔periods (oracle_map.yaml:73-78) |
| INVOICES | 3 | MIGRATION UNIT | `invoices` | U5 | PKG_INVOICING sp_issue_invoice insert/update; PKG_DUNNING reads (access_patterns.txt:64-90, 103-105) |
| INVOICE_LINES | 2 | MIGRATION UNIT (embedded) | `invoices.lines[]` | U5 | sp_issue_invoice deletes+rebuilds all lines per invoice in one transaction → single-document embed matches the transaction boundary (access_patterns.txt:72-75) |
| CREDIT_NOTES | 5 | MIGRATION UNIT | `credit_notes` | U5 | PKG_INVOICING row-by-row read/decrement of remaining_amount (access_patterns.txt:66, 74-75) |
| DUNNING_ATTEMPTS | 1 | MIGRATION UNIT (embedded) | `invoices.dunning_attempts[]` | U6 | unique (invoice_id, attempt_no); read as max(attempt_no) per invoice, inserted per invoice (access_patterns.txt:81-84) |
| NOTIFICATIONS | 1 | MIGRATION UNIT | `notifications` | U6 | PKG_DUNNING dedup-checked inserts; unique (tenant_id, kind_cd, sent_at) (access_patterns.txt:86-90) |
| BILLING_AUDIT_LOG | 0 | MIGRATION UNIT | `billing_audit_log` | U7 | PKG_OW_UTIL.log_msg autonomous-transaction inserts; JOB_PURGE_AUDIT_LOG 90-day purge → TTL index (access_patterns.txt:113-115, 157-161) |

## PL/SQL packages (5/5 covered — conversion scope)

| Object | Bucket | Unit | Replacement |
|---|---|---|---|
| PKG_OW_UTIL | MIGRATION UNIT | U7 | f_code_desc → `codes` lookup; f_md5_uuid → app-side MD5; f_dt2str/f_str2dt → app date formatting (NLS_DATE_LANGUAGE=ENGLISH pinned); log_msg → independent-write audit logger (autonomous txn semantics preserved: audit write never joins the business transaction) |
| PKG_PLANS | MIGRATION UNIT | U3 | fn_list_plans, fn_entitlement, sp_change_plan → service functions over `plans`/`tenants`/`subscriptions`; FOR UPDATE row lock → single-document transaction / findOneAndUpdate |
| PKG_RATING | MIGRATION UNIT | U4 | compute_rating, fn_usage_rating, fn_usage_summary, sp_finalize_rating → aggregation over `usage_events` + upserts of `rating_periods`/`rating_results`; TO_CHAR(...,'YYYYMMDD') string filters → real date-range predicates (behavior-preserving on day boundaries) |
| PKG_INVOICING | MIGRATION UNIT | U5 | compute_preview, fn_invoice_preview, fn_invoice_lines, sp_issue_invoice → single-document invoice rebuild + credit-note application in a multi-document transaction |
| PKG_DUNNING | MIGRATION UNIT | U6 | fn_overdue_accounts, sp_schedule_dunning, sp_suspend_overdue → queries/updates over `invoices`/`tenants`/`subscriptions`/`notifications` |

## Triggers (7/7 covered)

| Trigger | Bucket | Unit | Replacement |
|---|---|---|---|
| TRG_CUSTOMER_MASTER_SEQ | MIGRATION UNIT | U1 | app-side id assignment + cust_name_upper derivation at write time |
| TRG_CUSTOMER_MASTER_HIST | MIGRATION UNIT | U1 | app-side history write to `customer_master_hist` on update/delete |
| TRG_ENTITY_ATTR_VALUE_SEQ | MIGRATION UNIT | U1 | embedded attribute keys assigned at write time |
| TRG_SUBSCRIPTIONS_HIST | MIGRATION UNIT | U3 | app-side history write to `subscriptions_hist` |
| TRG_SUB_NO_UNCANCEL | MIGRATION UNIT | U3 | write-path guard: reject cancelled→active transitions |
| TRG_USAGE_EVENTS_CHECK | MIGRATION UNIT | U4 | write-path validation against `codes` |
| TRG_BILLING_AUDIT_LOG_ID | MIGRATION UNIT | U7 | app-assigned audit log id |

## Sequences (5/5 covered)

| Sequence | Last value | Unit | Replacement |
|---|---|---|---|
| SEQ_CUSTOMER_MASTER | 125,000 | U1 | migrated rows keep source cust_seq_no; new writes use app-generated ids (no external numeric-key consumer found) |
| SEQ_CUSTOMER_MASTER_HIST | 1 | U1 | ObjectId (history rows have no external key consumer) |
| SEQ_ENTITY_ATTR_VALUE | 11,001 | U1 | embedded eav_id preserved for migrated rows; new attributes keyed by attr_name |
| SEQ_SUBSCRIPTIONS_HIST | 1 | U3 | ObjectId |
| SEQ_BILLING_AUDIT_LOG | 1 | U7 | ObjectId / app-assigned |

## Scheduler jobs (2/2 covered)

| Job | State | Bucket | Unit | Replacement |
|---|---|---|---|---|
| JOB_NIGHTLY_DUNNING | disabled | MIGRATION UNIT | U6 | app-side scheduled task invoking dunning service functions |
| JOB_PURGE_AUDIT_LOG | disabled | MIGRATION UNIT | U7 | TTL index (90d) on `billing_audit_log.logged_at` |

## Application code paths (census in raw/appcode.txt)

| Path | Bucket | Unit |
|---|---|---|
| services/legacy-billing/app/reports.py (3 report queries) | MIGRATION UNIT | U2 (reads `invoice_feed`, `customers`, `codes`) |
| scripts/tp_pain/mongodb.py read-only probe | CONFIRMED EXCLUSION | diagnostic probe, not a business path |
| procs/harness/oracle_record.py + procs/oracle/oracle_map.yaml (12 entrypoints) | SHARED-REFERENCE | parity-harness contract consumed by U3–U7 verification |
| services/legacy-billing/tests/test_reports.py | SHARED-REFERENCE | monkeypatched tests; no Oracle connection |
| services/legacy-billing/db/oracle/** (schema/packages/seed/jobs/bootstrap) | CONFIRMED EXCLUSION | estate definition, not a consumer |
| testdata/legacy/oracle_billing_seed.py | CONFIRMED EXCLUSION | fixture generator |
| services/legacy-billing/db/procs/*.sql (PostgreSQL billing.*) | CONFIRMED EXCLUSION | separate comparison estate; does not touch OW_BILLING |
| docs/**, procs/transcripts/**, ops/deploy_prod_FINAL_v2.sh.txt | CONFIRMED EXCLUSION | documentation / recorded evidence |

## Proposed-unused findings

- ENTITY_ATTR_VALUE has no runtime reader in the inspected estate (raw/access_patterns.txt:181-183),
  but it is populated (8,333 rows, 100% customer-keyed). Disposition proposed at STOP B:
  migrate as embedded `customers.attributes[]` rather than drop — zero data loss, no
  orphan collection.
