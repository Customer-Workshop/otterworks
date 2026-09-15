# Source census — OW_BILLING (Oracle Free 23c, PDB FREEPDB1)

Read-only. Discovery queries are the `oracle` profile's `discovery_commands`, run verbatim.
Raw output: `/home/ubuntu/census/*.txt` (kept off the repo; regenerate with the same queries).
Profiled at namespace `demo`, seed 714559852.

## 1. Objects and bucketing

Every object is bucketed exactly once.

| Object | Rows | Bucket | Unit |
|---|---|---|---|
| `PLANS` | 3 | migration unit | U1 reference |
| `CODES` | 32 | migration unit | U1 reference |
| `TENANTS` | 69 (60 in ns `demo` + 9 static baseline) | migration unit | U1 reference |
| `SUBSCRIPTIONS` | 69 | migration unit (embeds into `tenants`) | U1 reference |
| `CUSTOMER_MASTER` | 25,000 (155 cols) | migration unit | U2 customers |
| `CUSTOMER_MASTER_HIST` | 0 (trigger-fed) | migration unit | U2 customers |
| `ENTITY_ATTR_VALUE` | 8,333 (all `entity_type='CUSTOMER'`) | migration unit (embeds into `customers`) | U2 customers |
| `INVOICE_HEADER` | 18,750 | migration unit | U3 invoices |
| `INVOICE_LINE` | 150,000 (37 orphan) | migration unit | U3 invoices |
| `INVOICES` | 3 | migration unit | U3 invoices |
| `INVOICE_LINES` | 2 | migration unit | U3 invoices |
| `DUNNING_ATTEMPTS` | 1 | migration unit (embeds into `invoices`) | U3 invoices |
| `USAGE_EVENTS` | 814 | migration unit | U4 usage |
| `RATING_PERIODS` | 3 | migration unit | U4 usage |
| `RATING_RESULTS` | 3 | migration unit (embeds into `rating_periods`) | U4 usage |
| `CREDIT_NOTES` | 5 | migration unit | U5 ancillary |
| `NOTIFICATIONS` | 1 | migration unit | U5 ancillary |
| `BILLING_AUDIT_LOG` | 0 | migration unit | U5 ancillary |
| `SUBSCRIPTIONS_HIST` | 0 (trigger-fed) | migration unit | U1 reference (`subscription_history`) |
| `FIXTURE_META` | 1 | excluded | harness bookkeeping, not business data; the PRD does not model it |
| 5 sequences (`SEQ_*`) | — | excluded | surrogate keys; every PRD `_id` is the source UUID, so no counters collection is needed. `SEQ_CUSTOMER_MASTER_HIST`, `SEQ_ENTITY_ATTR_VALUE`, `SEQ_BILLING_AUDIT_LOG` feed numeric ids carried as-is. |
| 7 triggers | — | D3 (see register) | logic, not data |
| 5 packages | — | D3 (see register) | logic, not data; separate extraction track |
| 2 scheduler jobs (both `enabled=FALSE`) | — | D3 (see register) | |

No materialized views. No `ROWID` usage anywhere in stored code (`all_source` scan returned
nothing) — the Oracle ROWID trap does not apply. No case-insensitive NLS comparisons; the
one case-fold path is `CUST_NAME_UPPER`, which the PRD replaces with a collation index.

## 2. Keys and constraints

- Every business table has a `VARCHAR2(36)` UUID primary key, so the PRD identity rule
  (`_id` = source UUID) applies everywhere without a crosswalk. Exceptions:
  `CUSTOMER_MASTER_HIST.HIST_ID`, `SUBSCRIPTIONS_HIST.HIST_ID`, `ENTITY_ATTR_VALUE.EAV_ID`
  and `BILLING_AUDIT_LOG.LOG_ID` are `NUMBER` sequence keys, used as `_id` unchanged.
- The conversion estate (`INVOICE_HEADER` / `INVOICE_LINE`) has **no foreign keys** —
  hence the 37 orphans.
- Uniques that become target indexes: `TENANTS(name)`, `PLANS(code)`,
  `SUBSCRIPTIONS(tenant_id, plan_id, starts_on)`, `RATING_PERIODS(tenant_id, period_start)`,
  `RATING_RESULTS(period_id, subscription_id)`, `DUNNING_ATTEMPTS(invoice_id, attempt_no)`,
  `NOTIFICATIONS(tenant_id, kind_cd, sent_at)`, `INVOICE_HEADER(invoice_no)`.

## 3. Data profile (drives the typing rules)

| Probe | Result |
|---|---|
| `SIGNUP_DT` values that fail `TO_DATE(...,'DD-MON-YY')` | **50** |
| `RELATED_ACCT_IDS` that are not a clean numeric CSV | **31** |
| `INVOICE_LINE` rows with no matching header | **37** |
| Any other dirty column | none. `LAST_ACTIVITY_DT`, `INVOICE_DT`, `DUE_DT`, `CHILD_ACCT_IDS`, `PROMO_CODES_CSV`, `GL_ACCT_CSV`, `SERVICE_PERIOD`, `*_YN` all parse 100% |
| 80 `FLAG_NN` / `UDF_*` columns | **0 non-null values across 25,000 rows** (all 80 probed individually) |
| `SEGMENT_CD` | 25,000 non-null, 9 distinct (1–9) |
| `REGION_CD` | 25,000 non-null, 12 distinct (1–12) |
| `TERRITORY_CD`, `CHANNEL_CD`, `RATE_CLASS_CD` | 100% NULL |
| `CODES` types present | `CUST_STATUS, CUST_TYPE, DUN_STATUS, INV_STATUS, NOTIF_KIND, PHONE_TYPE, PLAN_TIER, SUB_STATUS, TENANT_STATUS, USAGE_KIND` — none for segment/region/territory/channel/rate class |
| `STATUS_CD = 99` ("conversion limbo") | 473 customers; kept, per PRD |
| `ENTITY_ATTR_VALUE` | 7 attribute names; **187** (entity, attr_name) pairs occur more than once → confirms the PRD's array-not-map decision |
| `INVOICE_LINE` per header | avg 7.99, max 23 → embedding is safe; the PRD's p99 check passes |
| `INVOICES.id` ∩ `INVOICE_HEADER.invoice_id` | **0 overlap** → the two estates can share one collection without key collisions |

The anomaly profile matches `testdata/legacy/manifests/demo.json` exactly: 37 / 50 / 31,
nothing else. No finding to report to the data owner beyond the three planted sets.
