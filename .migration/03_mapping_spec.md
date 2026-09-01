# 03 — Mapping spec

Version: `1.2` (v1.0 approved at STOP B, 2026-09-01; v1.1 amendment approved 2026-09-01,
see 05_decisions.md: 19 NULL-bearing numeric CUSTOMER_MASTER fields carry
`null_missing_equiv` to defer Tier-2 native aggregates to the Tier-3 keyed diff, and the
17 all-NULL fields among them drop the bson_type assertion; v1.2 amendment approved
2026-09-01: the same Tier-2 deferral on the two all-NULL DATE fields
`subscriptions.ends_on`/`suspended_on`, bson_type stays date. Loaded data is unchanged —
source NULL still maps to explicit BSON null and NULL != missing everywhere).
Machine-readable contract: `.migration/03_mapping_spec.json` (generated deterministically
by `.migration/census/gen_mapping_spec.py` from `census/raw/columns.txt`; regenerating is
byte-stable). Canonicalization rules: `.migration/recon_canonicalization.json` v1.2.
Tolerances: `.migration/02_tolerances.{md,json}` v1.0 (approved STOP A).
Coverage table: `.migration/census/coverage.md`.

Target database: `ow_tp_mongodb_032752`; quarantine: `ow_tp_mongodb_032752_quarantine`.
Every migrated document carries `ns: "mongo_032752"` (loader-added; not part of parity
comparison). All facts cite `census/raw/*`; PROPOSED items need STOP B approval.

## Global type contract (FACT — profile + tolerances v1.0)

| Oracle | BSON | Canonicalization |
|---|---|---|
| NUMBER(p,0) p≤9 | int | — |
| NUMBER(p,0) 9<p≤18 | long | — |
| NUMBER scaled / p>18 / unbounded | decimal (Decimal128) | decimal_round half-even |
| VARCHAR2 | string | empty_string_is_null (explicit BSON null) |
| CHAR | string | rstrip_spaces + empty_string_is_null |
| DATE, TIMESTAMP(6) | date | UTC, truncate to ms |

NULL ↦ explicit BSON null; NULL and missing stay distinct (null_missing_equiv NOT applied).
Collation: binary, case-sensitive (census found no NLS case-insensitive comparisons;
appcode.txt:222-227) — collation_casefold NOT applied.

PROPOSED: VARCHAR2 columns holding formatted dates (INVOICE_DT, DUE_DT, HIST_DT,
CREATED_DT, SUBSCRIPTIONS_HIST.HIST_DT, and the CUSTOMER_MASTER string-date fields)
migrate **verbatim as strings** in v1. Parity-first: typed-date normalization is recorded
backlog, never a silent transform inside this migration.

## Collections (16)

| Collection | Root table | _id (key strategy) | Embeds | Cardinality rule | Access-pattern citation |
|---|---|---|---|---|---|
| tenants | TENANTS | source ID | — | 1 row = 1 doc | entitlement/dunning joins (access_patterns.txt:40-45, 86-90) |
| plans | PLANS | source ID | — | 1:1 | fn_list_plans / entitlement (40-52) |
| codes | CODES | `<code_type>#<code_val>` (loader-composed; recon keys on the composed expression `CODE_TYPE \|\| '#' \|\| CODE_VAL` vs `_id`, single whole-table gate — amendment approved 2026-09-01, see 05_decisions.md) | — | 1:1 | report decode lookups, f_code_desc (10-21, 35-38) |
| customers | CUSTOMER_MASTER | source CUST_ID | attributes[] ← ENTITY_ATTR_VALUE (child_where ENTITY_TYPE='CUSTOMER', parent_key ENTITY_ID, element key eav_id) | 25,000 roots; 8,333 attrs, 0 orphans (live probe 2026-09-01) | BALANCES_SQL; EAV always entity-keyed, no independent reader (73-79, 181-183) |
| customer_master_hist | CUSTOMER_MASTER_HIST | source HIST_ID | — | append-only audit, 1:1 | TRG_CUSTOMER_MASTER_HIST (134-139) |
| invoice_feed | INVOICE_HEADER | source INVOICE_ID | lines[] ← INVOICE_LINE (parent_key INVOICE_ID, element key line_id; child_where excludes orphans) | 18,750 roots; 149,963 embedded lines; **37 orphan lines → quarantine** `ow_tp_mongodb_032752_quarantine.invoice_feed_orphan_lines` (STOP A: no silent drops) | LINE_SQL inner join reproduces this exactly (16-21) |
| subscriptions | SUBSCRIPTIONS | source ID | — | 1:1; latest-covering lookup → index (tenant_id, starts_on desc) | entitlement/rating covering-row reads (40-52) |
| subscriptions_hist | SUBSCRIPTIONS_HIST | source HIST_ID | — | append-only audit | TRG_SUBSCRIPTIONS_HIST (124-128) |
| usage_events | USAGE_EVENTS | source ID | — | 1:1; index (tenant_id, occurred_at) | rating tenant+date scans (47-57) |
| rating_periods | RATING_PERIODS | source ID | — | 1:1 (3 rows) | sp_finalize_rating upsert (59-62) |
| rating_results | RATING_RESULTS | source ID | — | 1:1; index period_id (join to periods for rollover) | rollover read joins results↔periods (49-52) |
| invoices | INVOICES | source ID | lines[] ← INVOICE_LINES (element key line_no); dunning_attempts[] ← DUNNING_ATTEMPTS (element key attempt_no) | delete+rebuild of all lines per invoice is one transaction → single-doc embed; unique (invoice_id, attempt_no) preserved by element key | sp_issue_invoice (72-75, 103-105); dunning max-attempt per invoice (81-84) |
| credit_notes | CREDIT_NOTES | source ID | — | 1:1; read/decremented row-by-row | compute_preview / sp_issue_invoice (64-75) |
| notifications | NOTIFICATIONS | source ID | — | 1:1; unique index (tenant_id, kind_cd, sent_at) preserves dedup contract | sp_suspend_overdue conditional insert (86-90) |
| billing_audit_log | BILLING_AUDIT_LOG | source LOG_ID | — | append-only; TTL index logged_at 90d replaces JOB_PURGE_AUDIT_LOG | log_msg autonomous txn (113-115, 157-161) |
| fixture_meta | FIXTURE_META | initialized_at | — | single bookkeeping row; parity count-only, INITIALIZED_AT declared-unexercised (SYSTIMESTAMP at fixture init is non-deterministic; amendment approved 2026-09-01) | no runtime reader; migrated verbatim |

Embed-vs-reference rationale (PROPOSED): embed only where the dominant access is
through the parent and the write unit is the whole parent (invoice lines both pairs,
customer attributes, dunning attempts). Everything crossing tenants or queried
independently stays a referenced collection. No shard keys proposed: M0 target,
single-shard; largest collection 25k docs (FACT).

## Index plan (PROPOSED)

- customers: unique _id (cust_id); (conversion_batch_no) for BALANCES_SQL; (tenant_id)
- invoice_feed: unique _id; (batch_no) for STATUS/LINE_SQL; (cust_id)
- subscriptions: (tenant_id, starts_on) for latest-covering lookup
- usage_events: (tenant_id, occurred_at, kind_cd)
- invoices: (tenant_id, status_cd, issued_at) for overdue scans; unique (period_id, tenant_id) not asserted (no source constraint)
- notifications: unique (tenant_id, kind_cd, sent_at)
- credit_notes: (tenant_id, issued_on)
- billing_audit_log: TTL on logged_at (90d, matches purge job)
- codes: unique _id

## Sequence replacement (PROPOSED)

Per profile: migrated rows keep their source numeric keys; new writes use app-generated
ids/ObjectId — census found no external consumer of the raw sequence numbers. No counters
collection needed. (Details per sequence in coverage.md.)

## Units and waves

Units (each = one PR into `tp-run/mongodb-20260901T032752Z`, gated by harness recon):

| Unit | Scope | Size | Class |
|---|---|---|---|
| U0 shared-reference | codes, tenants, plans, fixture_meta + indexes | S | reference (wave 0, serial) |
| U1 customers | customers (+attributes embed), customer_master_hist, 3 triggers, 3 sequences | **XL** | wide-embed calibration (155 cols) |
| U2 invoice-feed | invoice_feed (+lines embed), orphan quarantine, reports.py port | L | bulk-load calibration (150k child rows) |
| U3 subscriptions | subscriptions, subscriptions_hist, PKG_PLANS conversion, 2 triggers | M | proc-heavy calibration |
| U4 rating | usage_events, rating_periods, rating_results, PKG_RATING, usage trigger | M | proc-heavy |
| U5 invoicing | invoices (+lines embed), credit_notes, PKG_INVOICING | **XL** | proc-heavy (multi-doc txn) |
| U6 dunning | dunning_attempts embed, notifications, PKG_DUNNING, nightly job replacement | M | proc-heavy |
| U7 audit-util | billing_audit_log, PKG_OW_UTIL, purge job → TTL | S | utility |

Waves (dependency-ordered; U5 needs U3/U4 landed — sp_issue_invoice invokes PKG_RATING
and reads subscriptions; U6 needs U5's `invoices`):

- **Wave 0**: U0 (serial, parent-run)
- **Wave 1** (calibration): U1, U2 — fan-out width 2
- **Wave 2**: U3, U4, U7 — fan-out width 3
- **Wave 3**: U5 then U6 (one child, sequential batch — hard data dependency)

XL units (U1, U5) get decision-first contract PRs: the mapping/interface excerpt is
confirmed against this spec before load code lands.

Source-load cap compliance (cap = 1, STOP A): child sessions parallelize code work, but
every live source extract/recon run takes the single live window serialized through the
orchestrator merge queue (recorded per unit in 04_progress.md); each harness run itself
uses `source_concurrency: 1`. Fan-out width above refers to sessions, not source load.

Expected cost discount: U1/U2/U3 calibrate the three pattern classes; waves 2-3 reuse
their loader/recon scaffolding and conventions — expected ~40-60% lower session cost per
unit versus wave 1 (PROPOSED estimate).

## Recon invocation contract (per unit)

```
recon run --unit <unit_id> \
  --mapping .migration/03_mapping_spec.json \
  --tolerances .migration/02_tolerances.json \
  --canonicalization .migration/recon_canonicalization.json \
  --mode live --source-dsn-secret <oracle fixture DSN secret> \
  --target-uri-secret MONGODB_ATLAS_URI \
  --out .migration/recon/<unit_id>/
```
`codes` runs as one whole-table gate on the composed key (per the approved amendment).
`result.json` is the merge authority; UNGRADED embeds are work, never a PASS.
