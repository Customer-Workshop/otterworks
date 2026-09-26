# Census coverage — OW_BILLING (live, `ORACLE_BILLING_RO_DSN`, 2026-09-26)

Catalog run: `discovery.json` (profile `discovery_commands` as written + `COUNT(*)` per table because
`ALL_TABLES.NUM_ROWS` is NULL on the fixture). `ow_billing_ro` holds only CREATE SESSION + SELECT, no
`SELECT_CATALOG_ROLE`, so `ALL_OBJECTS/ALL_SOURCE/ALL_SEQUENCES/ALL_SCHEDULER_JOBS/ALL_DEPENDENCIES`
returned 0 rows for PL/SQL, triggers, sequences and jobs (D4-4). Those rows below are FACT from the
repo DDL that built the fixture (`services/legacy-billing/db/oracle/`), PROPOSED as to deployment state.

Every object in exactly one bucket. Rows: live COUNT(*).

## Tables (20)
| Object | Rows | Bucket | Unit / collection | Cite |
|---|---|---|---|---|
| CODES | 32 | shared/reference | wave 0 `codes` | facade.py:114,215,245,342,394 |
| TENANTS | 70 (60 `mmprt::*` + 9 static + 1) | shared/reference | wave 0 `tenants` | facade.py:113; oracle.py:136 |
| PLANS | 3 | shared/reference | wave 0 `plans` | pkg_plans; oracle.py:150 |
| CUSTOMER_MASTER | 25001 (25000 batch 14531857 + 1 static) | migration unit | `customers` (customers, XL: 155 cols) | facade.py:287; reports.py:87 |
| ENTITY_ATTR_VALUE | 8337 (all ENTITY_TYPE=CUSTOMER, 0 dangling) | migration unit | embedded `customers.attributes` | facade.py:294 |
| INVOICE_HEADER | 18750 | migration unit | `invoice_headers` (invoice_batch) | reports.py:46,67 |
| INVOICE_LINE | 150000 (37 orphans) | migration unit | embedded `invoice_headers.lines` + `invoice_line_orphans` | reports.py:46,67; mmprt.json planted_anomalies |
| SUBSCRIPTIONS | 70 | migration unit | `subscriptions` (subscriptions_rating) | pkg_plans; oracle.py:68,161 |
| USAGE_EVENTS | 805 | migration unit | `usage_events` | facade.py:214,401; pkg_rating |
| RATING_PERIODS | 3 | migration unit | `rating_periods` | pkg_rating.sp_finalize_rating |
| RATING_RESULTS | 3 | migration unit | embedded `rating_periods.results` | pkg_rating |
| INVOICES | 4 | migration unit | `invoices` (invoicing) | pkg_invoicing; facade.py:243 |
| INVOICE_LINES | 4 | migration unit | embedded `invoices.lines` | pkg_invoicing.fn_invoice_lines |
| CREDIT_NOTES | 5 | migration unit | `credit_notes` | pkg_invoicing.compute_preview |
| DUNNING_ATTEMPTS | 1 | migration unit | `dunning_attempts` (dunning) | facade.py:341; pkg_dunning |
| NOTIFICATIONS | 1 | migration unit | `notifications` | pkg_dunning.sp_suspend_overdue |
| CUSTOMER_MASTER_HIST | 0 | proposed-unused | retire; only writer is trigger `trg_customer_master_hist` (02_horror.sql:358); no app reader (grep `customer_master_hist` in app/, bridge/: none) | D3-3 |
| SUBSCRIPTIONS_HIST | 0 | proposed-unused | retire; only writer is `trg_subscriptions_hist` (01_tables.sql:206); no app reader | D3-4 |
| BILLING_AUDIT_LOG | 0 | proposed-unused | retire; written by `pkg_ow_util.log_msg` (autonomous txn), purged by JOB_PURGE_AUDIT_LOG; no app reader | D3-2 |
| FIXTURE_META | 2 | excluded | fixture bookkeeping (`04_upgrade_static.sql:170`), not business data | — |

## Indexes (25) — all PK/UQ-backing or single-column; folded into `03_mapping_spec.json.index_plan`. No views, no materialized views.

## PL/SQL (from repo DDL; catalog not visible to `ow_billing_ro`, D4-4)
| Object | Kind | Bucket | Plan | Cite |
|---|---|---|---|---|
| pkg_ow_util | package | shared | rewrite as app helper (uuid5, code lookup, date str<->date); `log_msg` -> app logging | packages/01_pkg_util.sql |
| pkg_plans | package | unit subscriptions_rating | app code (fn_list_plans, fn_entitlement, sp_change_plan; `FOR UPDATE` at :80 -> findOneAndUpdate) | packages/02_pkg_plans.sql |
| pkg_rating | package | unit subscriptions_rating | app code / aggregation ($group by tenant+period); package globals -> request-scoped state | packages/03_pkg_rating.sql |
| pkg_invoicing | package | unit invoicing | app code; preview globals -> request-scoped | packages/04_pkg_invoicing.sql |
| pkg_dunning | package | unit dunning | app code; scheduled via D3-1 replacement | packages/05_pkg_dunning.sql |
| trg_billing_audit_log_id, trg_subscriptions_hist, trg_sub_no_uncancel, trg_usage_events_check | trigger | D3 | id-assign -> loader/app; hist -> retire with tables; no_uncancel + usage check -> app validation / JSON schema validator | schema/01_tables.sql:179-245 |
| trg_customer_master_seq, trg_customer_master_hist, trg_entity_attr_value_seq | trigger | D3 | seq -> counters (PROPOSED); hist -> retire | schema/02_horror.sql:346-400 |
| seq_billing_audit_log, seq_subscriptions_hist, seq_customer_master, seq_customer_master_hist, seq_entity_attr_value | sequence | key strategy | values copied as long; post-cutover counters collection (PROPOSED) | schema/*.sql |
| JOB_NIGHTLY_DUNNING (02:00, DISABLED) | scheduler job | D3-1 | Atlas Trigger (scheduled) or app cron calling dunning unit; stays disabled until cutover | schema/04_jobs.sql:10 |
| JOB_PURGE_AUDIT_LOG (03:30, DISABLED) | scheduler job | D3-2 | retire with BILLING_AUDIT_LOG (or TTL index if kept) | schema/04_jobs.sql:21 |

## Application SQL touchpoints (services/legacy-billing)
- `app/backends/oracle.py`: 13 pkg calls (callfunc/callproc) + raw SQL on tenants, plans, subscriptions (ensure-tenant path).
- `app/facade.py`: tenants+codes, customer_master+entity_attr_value, usage_events (+insert), invoices+rating_periods+codes, dunning_attempts+codes.
- `app/reports.py`: invoice_header x invoice_line x codes by batch_no; customer_master by conversion_batch_no.
- `bridge/bridge.py`: SQS/SNS only, no Oracle SQL (D2: consumes app HTTP, not the DB).
- Traps found: `FOR UPDATE` (pkg_plans:80), `MERGE` (fixture_meta only), no ROWID, no CONNECT BY, no window functions. Text dates in `*_DT` VARCHAR2 (`DD-MON-YY`, 50 planted dirty), `RELATED_ACCT_IDS` CSV (31 malformed), `*_YN` CHAR flags, `ADDR_LINE_1..6` repeating groups, EAV table, CODES lookup.

## Access-pattern evidence
Read-heavy: every route is a read except change_plan, rating_finalize, invoice_issue, schedule_dunning, suspend_overdue, usage insert. Joins are 1-hop to CODES (lookup) plus parent->child (header->line, customer->EAV, invoice->lines, period->results): all embedded. Transaction boundaries: one PL/SQL call = one transaction; sp_issue_invoice writes invoices+invoice_lines together (embed keeps it a single-document write).
