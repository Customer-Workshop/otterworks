# 06 — Census & data model (playbook 2, STOP B)

Source profile: `skills/mongo-migration/profiles/oracle.md` (plugin
`account-upload_org-default-8486a6b8` v0.1.2). One profile loaded; no other profile read.
`mcp_delegation` names `reasoning` for schema analysis / census / mapping proposal, so no
MCP tool was called for this artifact.

All `discovery_commands` in the profile were run **verbatim** as `SELECT`s against
`OW_BILLING` on the fixture at `localhost:52521/FREEPDB1` (no DSN secret exists yet — see
`01_conventions.md`; every statement in this playbook is read-only, per gap G1).
Source: Oracle AI Database 26ai Free, `23.26.3.0.0`. Target: Atlas `otterworks-demo`,
MongoDB 8.0.29, database `ow_tp_demo`.

Rows marked **FACT** are measured. Everything under "Decisions" is **PROPOSED** until STOP B.

---

## 1. Object-level coverage (FACT)

| Object | Rows | Columns | Key / constraints | Indexes | Unit | Target shape |
|---|---:|---:|---|---|---|---|
| `OW_BILLING.CUSTOMER_MASTER` | 25,000 | 155 (42 populated, 113 100% NULL) | PK `CUST_ID`; no FK, no unique, no check | `PK_CUSTOMER_MASTER` (UNIQUE, NORMAL) — the only index | `customers` (wave 1) | root document, `_id = CUST_NO` |
| `OW_BILLING.ENTITY_ATTR_VALUE` | 8,333 | 7 (all populated) | PK `EAV_ID`; no FK to `CUSTOMER_MASTER` | `PK_ENTITY_ATTR_VALUE` (UNIQUE, NORMAL) | `customers` (wave 1) | embedded array `attributes[]` |
| `OW_BILLING.INVOICE_HEADER` | 18,750 | 9 (all populated) | PK `INVOICE_ID`; no FK | `PK_INVOICE_HEADER` (UNIQUE, NORMAL) | `invoices` (wave 2) | root document, `_id = INVOICE_ID` |
| `OW_BILLING.INVOICE_LINE` | 150,000 | 20 (19 fully populated, `POSTED_YN` 120,058) | PK `LINE_ID`; **no FK to `INVOICE_HEADER`** | `PK_INVOICE_LINE` (UNIQUE, NORMAL) | `invoices` (wave 2) | embedded array `lines[]` (149,963 rows; 37 orphans quarantined) |

Every in-scope object appears exactly once. Facts worth carrying forward:

- **No secondary indexes exist anywhere in scope** — four primary-key indexes, nothing else.
  The target index plan is therefore designed from the app's read paths (§3), not ported.
- **No declared foreign keys in scope.** `INVOICE_LINE → INVOICE_HEADER` and
  `ENTITY_ATTR_VALUE.ENTITY_ID → CUSTOMER_MASTER.CUST_ID` are conventions enforced by
  nothing; the 37 orphaned lines are what that costs.
- `all_tables.num_rows` is NULL for every table (gap G5); counts above are `COUNT(*)`.

### Declared coverage gaps (deliberately not migrated)

| Excluded | Reason |
|---|---|
| 113 of 155 `CUSTOMER_MASTER` columns — `UDF_01..40`, `UDF_AMT_01..10`, `UDF_DT_01..10`, `FLAG_01..20`, `ADDR_LINE_4..6`, `MAIL_*`, `PHONE3/4`, `EMAIL_2/3`, `FAX`, `DBA_NAME`, `ZIP4`, `COUNTRY_CD`, `CHILD_ACCT_IDS`, `CONTACT_NOTES`, `LTD_BILLED_AMT`, `YTD_PAID_AMT`, `LAST_INVOICE_DT`, `LAST_PAYMENT_DT`, `TERMINATE_DT`, `TERRITORY_CD`, `CHANNEL_CD`, `RATE_CLASS_CD`, `DUNNING_EXEMPT_YN` | **100% NULL in the source** (`COUNT(col) = 0` over all 25,000 rows). Carrying an always-absent field adds no data and, on this harness, is not even checkable (see H1). Retired; the loader asserts they are still empty at load time and quarantines any row that is not |
| `CUSTOMER_MASTER_HIST` (158 cols), `INVOICES`, `INVOICE_LINES`, `CODES`, `TENANTS`, `PLANS`, `SUBSCRIPTIONS`, `SUBSCRIPTIONS_HIST`, `USAGE_EVENTS`, `RATING_PERIODS`, `RATING_RESULTS`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS`, `CREDIT_NOTES`, `BILLING_AUDIT_LOG`, `FIXTURE_META` | The 16 `OW_BILLING` tables outside the two approved units (STOP A) |
| Postgres `documents` workload, DynamoDB `files` workload | No source profile; one profile per engagement (STOP A) |
| `CODES` lookup | Out of unit scope, but the billing-report contract resolves `STATUS_CD` through it (§3). Status **codes** are migrated as-is; the code→description lookup stays source-side for this engagement and must be served by the migrated backend from a static map. Flagged as decision D8 |

---

## 2. Stored logic inventory (FACT + disposition)

17 PL/SQL objects, 5 sequences and 2 scheduler jobs exist in `OW_BILLING`. Only the three
objects that `all_dependencies` reports against in-scope tables affect this migration.

| Object | Type | Touches in-scope? | Disposition |
|---|---|---|---|
| `TRG_CUSTOMER_MASTER_SEQ` | TRIGGER | yes — `CUSTOMER_MASTER` | **Rewrite in app code.** Does three things on insert: `SEQ_CUSTOMER_MASTER.NEXTVAL → CUST_SEQ_NO`, `CUST_NAME_UPPER := UPPER(CUST_NAME)`, `ROW_VERSION_NO := NVL(...,1)`. On Atlas: counters collection for `cust_seq_no` (D3), collation index instead of the shadow upper column (D6), `row_version_no` maintained by the writer |
| `TRG_CUSTOMER_MASTER_HIST` | TRIGGER | yes — `CUSTOMER_MASTER` | **Retire.** Full-row copy into the 158-column `CUSTOMER_MASTER_HIST`, which is out of scope. Change history on Atlas is a change-stream/Atlas-trigger concern, deliberately not rebuilt in this engagement |
| `TRG_ENTITY_ATTR_VALUE_SEQ` | TRIGGER | yes — `ENTITY_ATTR_VALUE` | **Retire.** `EAV_ID` exists only to give EAV rows a PK; embedded `attributes[]` elements need no surrogate |
| `PKG_OW_UTIL`, `PKG_PLANS`, `PKG_RATING`, `PKG_INVOICING`, `PKG_DUNNING` (+ bodies) | PACKAGE | no (`PKG_INVOICING` reads the out-of-scope `INVOICE_LINES`, not `INVOICE_LINE`) | **Out of scope**, left source-side. `PKG_OW_UTIL.fn_fmt_dt/fn_parse_dt` (`TO_CHAR/TO_DATE 'DD-MON-YY'`) is the estate's string-date convention that D4 replaces |
| `TRG_BILLING_AUDIT_LOG_ID`, `TRG_SUBSCRIPTIONS_HIST`, `TRG_SUB_NO_UNCANCEL`, `TRG_USAGE_EVENTS_CHECK` | TRIGGER | no | Out of scope |
| `SEQ_CUSTOMER_MASTER` (last 125,000), `SEQ_ENTITY_ATTR_VALUE` (11,001) | SEQUENCE | yes | See D3 |
| `SEQ_BILLING_AUDIT_LOG`, `SEQ_SUBSCRIPTIONS_HIST`, `SEQ_CUSTOMER_MASTER_HIST` | SEQUENCE | no | Out of scope |
| `JOB_NIGHTLY_DUNNING`, `JOB_PURGE_AUDIT_LOG` | SCHEDULER JOB | no (dunning + audit retention, both out-of-scope tables) | Out of scope; both are `ENABLED=FALSE` on the fixture |
| Materialized views | — | — | **None exist** |

---

## 3. Access-pattern evidence (FACT — from app code)

The only application that reads the in-scope tables today is the legacy billing app that
backs the admin dashboard's Billing Report page. Its contract is what the migrated backend
must reproduce, so it — not the table shape — drives the model.

| Read path | Code | Query shape | Model consequence |
|---|---|---|---|
| `GET /api/reports/month-end` — invoice counts + header totals by status | `services/legacy-billing/app/reports.py` `month_end()` / `STATUS_SQL` | `INVOICE_HEADER` filtered by `BATCH_NO`, grouped by `STATUS_CD` (outer-joined to `CODES`) | `invoices` needs `{batch_no, status_cd}`; a header-only read must not have to touch lines |
| same endpoint — line rollup by status × line type | `reports.py` `LINE_SQL` | `INVOICE_HEADER ⋈ INVOICE_LINE ON INVOICE_ID` filtered by header `BATCH_NO`, grouped by status and `LINE_TYPE_CD`, summing `AMOUNT`/`TAX_AMT`; **orphan lines fall out of the join** | Lines are never read except through their header, and the join drops exactly the orphans → **embed `lines[]`, quarantine the 37 orphans** |
| `GET /api/reports/reconciliation` — customer balance rollup | `reports.py` `BALANCES_SQL` | `CUSTOMER_MASTER` filtered by `CONVERSION_BATCH_NO`, summing `CUR_BAL_AMT` / `PAST_DUE_AMT` | `customers` needs `{conversion_batch_no}`; money must stay exact to the cent → Decimal128 |
| Contract + UI wiring (page is not edited during the migration; only `source.engine` flips) | `docs/tech-partnerships/billing-report-contract.md`, `frontend/admin-dashboard/src/app/pages/billing-report/` | two endpoints, identical JSON, amounts as strings with two decimals | These two reports are the Tier-4 parity ops for both units |
| Customer name search | `TRG_CUSTOMER_MASTER_SEQ` maintains `CUST_NAME_UPPER`; no live query uses it (`grep` over the repo outside the schema DDL: no hits) | shadow-uppercase column, i.e. case-insensitive lookup by convention | Replace with a collation-aware index (D6) rather than migrating the shadow column as data |

Nothing in the repo reads `ENTITY_ATTR_VALUE` through an application path — it is written
and read ad hoc (the "156th field" escape hatch). It is fetched only alongside its customer,
which is what justifies embedding rather than referencing.

### 16 MB ceiling check (FACT)

| Embed | Max children per parent | Max measured payload | Verdict |
|---|---:|---|---|
| `customers.attributes[]` | 5 | EAV row ≤ 4 KB (`ATTR_VALUE VARCHAR2(4000)`), observed max 5 attrs/customer | safe by ~3 orders of magnitude |
| `invoices.lines[]` | 23 (avg 7.99) | line row ≈ 0.7 KB worst case → ≤ 17 KB/invoice | safe |
| `customers` root | — | widest measured variable payload (`CUST_ID + CUST_NAME + CONTACT_NOTES + *_CSV`) = 91 bytes | safe |

No CLOB/BLOB/RAW/XMLTYPE column exists in scope, so there is no LOB tier and no GridFS
decision (D7).

---

## 4. Anomaly scan — every `known_incompatibilities` trap (FACT)

| # | Trap | Hit? | Evidence |
|---|---|---|---|
| 1 | Empty string IS NULL (`'' = NULL`) | **hit (structural)** | 122 VARCHAR2 + 25 CHAR columns in scope. No sentinel-blank rows exist (`CUST_NAME = ' ' OR CONTACT_NOTES = ' '` → 0), but Oracle cannot distinguish `''` from NULL, so every string field carries `empty_string_is_null` (STOP A decision D2, target policy `null`) |
| 2 | Sequences (`.NEXTVAL`) | **hit** | `SEQ_CUSTOMER_MASTER` (last_number 125,000, max `CUST_SEQ_NO` 124,999) fired by `TRG_CUSTOMER_MASTER_SEQ`; `SEQ_ENTITY_ATTR_VALUE` (11,001) fired by `TRG_ENTITY_ATTR_VALUE_SEQ`. → D3 |
| 3 | ROWID-based access | **not hit** | Profile's ROWID probe over `ALL_SOURCE` returned 0 rows; no `ROWID`/`UROWID` column exists in scope |
| 4 | PL/SQL packages, triggers, materialized views | **hit** | 3 triggers on in-scope tables (§2); 0 materialized views; the 5 packages touch out-of-scope tables only |
| 5 | `CONNECT BY` | **not hit** | `ALL_SOURCE LIKE '%CONNECT BY%'` → 0 rows; no hierarchy column in scope |
| 6 | `MERGE` | **not hit** | `ALL_SOURCE LIKE '%MERGE %'` → 0 rows. (The **loader** will still use `bulkWrite` upserts for idempotence — that is a load choice, not a ported statement) |
| 7 | Analytic/window functions | **not hit** | `ALL_SOURCE LIKE '%OVER (%'` → 0 rows; the report queries are plain `GROUP BY` |
| 8 | Oracle DATE arithmetic (`date + 1`) | **not hit in scope** | `ALL_SOURCE LIKE '%SYSDATE -%'` → 0 rows; the only date arithmetic in the estate is `JOB_PURGE_AUDIT_LOG` (`logged_at < SYSDATE - 90`), on an out-of-scope table |
| 9 | Case-insensitive comparison via NLS | **not hit as NLS; hit as pattern** | `NLS_COMP=BINARY`, `NLS_SORT=BINARY` → `collation_casefold` stays disabled (STOP A). The estate implements case-insensitive name lookup *manually*, via the `CUST_NAME_UPPER` shadow column maintained by a trigger. → D6 |

### Data-quality anomalies (FACT, matched against `testdata/legacy/manifests/demo.json`)

| Anomaly | Measured | Manifest | Handling |
|---|---:|---:|---|
| Orphaned `INVOICE_LINE` (no header) | 37 | 37 | quarantine `ow_tp_demo_quarantine.invoices` |
| Unparseable `SIGNUP_DT` strings (`31-FEB-24`, `N/A`, `99-999-99`, `1/1/1900`, `  -   -  `, `12-13-201`, `00-XXX-00`, `29-FEB-23`) | 50 | 50 | D4: field-level quarantine — document loads, `signup_at` omitted, raw string preserved and the row logged to quarantine |
| Malformed CSV lists in `RELATED_ACCT_IDS` (`NULL,NONE,`, `,,`, ` , 99 ,`, `12345,,67890,`) | 31 | 31 | D5: raw string preserved verbatim; parsed array holds only well-formed tokens; row logged to quarantine |
| Other dirty-date columns (`LAST_ACTIVITY_DT`, and the 3 all-NULL date-strings) | 0 | — | `LAST_ACTIVITY_DT` parses 25,000/25,000 |
| `INVOICE_HEADER` / `INVOICE_LINE` unparseable dates | 0 / 0 | — | clean |
| Duplicate `(INVOICE_ID, LINE_NO)` pairs | 19,512 invoices | — | `LINE_NO` is **not** unique within an invoice; `LINE_ID` is the only line identity. Array order is by `LINE_ID`, not `LINE_NO` |
| `SUM(line.amount + tax_amt) ≠ header.total_amt` | 18,745 of 18,750 | — | the legacy estate does not reconcile; `TOTAL_AMT` is migrated as stored. Recomputing it would silently "fix" the source and break report parity |
| Duplicate `(ENTITY_ID, ATTR_NAME)` in EAV | 187 | — | an attribute can repeat per customer → `attributes` must be an **array**, not a key/value object (D2) |
| Duplicate/NULL `CUST_NO`, orphan `INVOICE_HEADER.CUST_ID`, NULL `TENANT_ID`, duplicate `INVOICE_NO` | 0 each | — | `CUST_NO` is safe as `_id`; every invoice resolves to a customer |
| Blank-padded CHAR values | 0 | — | `rstrip_spaces` still applied per profile (CHAR is padded by definition) |

---

## 5. Mapping spec (`.migration/03_mapping_spec.json`, version `1.0.0`)

Validated against the harness contract:

```
$ python3 -c "from recon.config import load_mapping_spec as l; import pathlib; \
    s=l(pathlib.Path('.migration/03_mapping_spec.json')); print(s.version, len(s.collections))"
1.0.0 2
```

| Collection | Root table | Comparison key | Fields | Embed (Tier-1 cardinality rule) |
|---|---|---|---:|---|
| `customers` | `OW_BILLING.CUSTOMER_MASTER` | `CUST_NO → _id` | 42 | `attributes[]` ← `ENTITY_ATTR_VALUE WHERE ENTITY_TYPE = 'CUSTOMER'` (8,333) |
| `invoices` | `OW_BILLING.INVOICE_HEADER` | `INVOICE_ID → _id` | 9 | `lines[]` ← `INVOICE_LINE WHERE EXISTS (matching header)` (149,963) |

Type rules applied straight from the profile's `type_mappings`:

- `NUMBER(p,s)` with `s > 0` (`CUR_BAL_AMT`, `PAST_DUE_AMT`, `YTD_BILLED_AMT`,
  `CREDIT_LIMIT_AMT`, `TOTAL_AMT`, `QTY`, `UNIT_PRICE`, `AMOUNT`, `TAX_AMT`) →
  **Decimal128** + `decimal_round`. No money field is a double anywhere in the spec.
- `NUMBER(p,0)`, p ≤ 18 (`CUST_SEQ_NO`, `*_CD`, `BATCH_NO`, `ROW_VERSION_NO`) → `long`.
- `VARCHAR2` → `string` + `empty_string_is_null`; `CHAR` → `string` +
  `rstrip_spaces, empty_string_is_null`; partially-populated columns also carry
  `null_missing_equiv`. Fully-populated columns deliberately omit it so Tier 2 keeps
  checking their `null_rate`/`distinct`/`min`/`max` instead of deferring to Tier 3.
- `DATE` (`CREATED_DT`, `UPDATED_DT`) → `date` + `datetime_utc_truncate_ms`.

**Transformed columns are mapped to the raw value the loader preserves**, not to the derived
field: `SIGNUP_DT → legacy.signup_dt`, `LAST_ACTIVITY_DT → legacy.last_activity_dt`,
`RELATED_ACCT_IDS → legacy.related_acct_ids`, `PROMO_CODES_CSV → legacy.promo_codes_csv`,
`INVOICE_DT → legacy.invoice_dt`, `DUE_DT → legacy.due_dt`. The derived, typed fields
(`signup_at` as a BSON date, `related_acct_ids` as an array, …) are additive and validated by
the collection's `$jsonSchema` plus Tier-4 parity, because the harness has no rule that can
compare a `DD-MON-YY` string against a BSON date or a CSV string against an array (see H2).
This keeps recon proving losslessness of the source bytes while the document still gets the
modern shape.

---

## 6. Decisions requiring STOP B sign-off (all PROPOSED)

| # | Decision | Recommendation | Evidence |
|---|---|---|---|
| D1 | Embed vs reference: `INVOICE_LINE` | **Embed** as `invoices.lines[]`; 37 orphans → quarantine | Lines are only ever read through their header (`LINE_SQL`); max 23 lines/invoice, ≤17 KB |
| D2 | Embed vs reference: `ENTITY_ATTR_VALUE` | **Embed as an array** `attributes[{name, value, type}]`, not a key/value subdocument | 187 duplicate `(entity, attr_name)` pairs would silently collapse in an object; an array also lets Tier 1 count 8,333 elements against 8,333 rows |
| D3 | Sequence-backed keys | `_id = CUST_NO` / `INVOICE_ID` (natural keys, per conventions). `CUST_SEQ_NO` is migrated as data and, for new inserts, served by a `counters` collection in `ow_tp_demo` (`findOneAndUpdate $inc`), seeded to 125,000. `EAV_ID` retired | `SEQ_CUSTOMER_MASTER` is at 125,000 and `CUST_SEQ_NO` is a real column other systems may read; EAV ids are surrogate-only |
| D4 | 50 unparseable `SIGNUP_DT` strings | **Field-level quarantine**: load the customer, omit `signup_at`, keep `legacy.signup_dt`, write a quarantine record naming the field. Do not drop the customer | Row-level drop would break the 25,000-doc count and lose 50 real customers; STOP A D3 (quarantine malformed) is field-scoped |
| D5 | 31 malformed CSV lists | Same pattern: raw preserved, array holds well-formed tokens only, row logged to quarantine | Same as D4 |
| D6 | Case-insensitive name lookup | Replace `CUST_NAME_UPPER` with a **collation-aware index** on `customers.name` (`{locale: "en", strength: 2}`); do not migrate the shadow column | The shadow column is trigger-derived, and no query in the repo reads it |
| D7 | LOB/BLOB handling | **None needed** — no LOB in scope, max document ≈ 17 KB | §3 ceiling check |
| D8 | `CODES` lookup (`INV_STATUS`) | Migrate `status_cd` as-is; the migrated backend resolves descriptions from a static map that reproduces `UNKNOWN(<cd>)` for unmapped codes | Contract requires byte-identical report output; `CODES` is out of unit scope |
| D9 | Target index plan | `customers`: `_id` (`CUST_NO`), `{cust_id: 1}` unique, `{conversion_batch_no: 1}`, `{tenant_id: 1, status_cd: 1}`, `{name: 1}` with collation. `invoices`: `_id` (`INVOICE_ID`), `{batch_no: 1, status_cd: 1}`, `{cust_id: 1, "legacy.invoice_dt": 1}`, `{invoice_no: 1}` unique, `{"lines.line_id": 1}` | Derived from the report queries in §3, plus the join keys wave 2 needs from wave 1; the source has no secondary index to port |
| D10 | Sync/CDC for the parallel-run window | **None.** One-shot idempotent load per namespace, re-runnable, with the source frozen for the window; the fixture has no supplemental logging/GoldenGate and the estate is read-only by policy | Setting up CDC would require writes to the source (guardrail 1). Cutover stays a customer-held, human-started action |
| D11 | Wave order | Unchanged: `customers` (wave 1) → `invoices` (wave 2) | Invoice documents carry `cust_id`/`cust_no` established by wave 1 |
| D12 | Tolerance change | **None proposed.** Tolerances stay at version `1` | Exact-money comparison at `numeric_abs_tol = 0.0` is achievable with Decimal128 |
| D13 | 113 all-NULL columns retired | Declared coverage gap (§1) rather than 113 always-absent fields | `COUNT(col) = 0` over 25,000 rows for each |

### Blocking harness findings (must be resolved before any unit can go green)

| # | Finding | Impact | Recommendation |
|---|---|---|---|
| **H1** | Tier 2's `sum` check is not type-aware. `_SqlAdapterBase.field_aggregates` catches Oracle's `ORA-01722` on `SUM(<non-numeric>)` and records `sum = None`; `MongoTargetAdapter` uses `$sum`, which ignores non-numeric values and returns **0**. `_agg_close(None, 0)` is False → an `aggregate_sum` finding for **every string, date and all-NULL field**, on a perfectly correct load. Verified both sides: `SUM(CUST_NAME)` → `ORA-01722`, `SUM(UDF_AMT_01)` → `NULL`; `$sum` over a string field on mongo:7 → `0` | 40 of 42 `customers` fields and 7 of 9 `invoices` fields would fail Tier 2 no matter how good the load is. No mapping-spec option avoids it: `NULL_SEMANTIC` rules reduce the checked stats to `("sum",)` — precisely the broken one | Skip `sum` when the source side reports `None` (or compare only when both sides are numeric). Filed as PROFILE/HARNESS FEEDBACK. **Choose at STOP B:** (a) wait for the plugin release, or (b) run wave 1 against a repo-vendored copy of the harness carrying only this fix, so the harness verdict stays the merge authority |
| **H2** | No canonicalization rule can compare a `DD-MON-YY` string to a BSON date, or a CSV string to an array | The migration's whole point — typing the string dates and CSV lists — is invisible to recon | Worked around in v1.0.0 by mapping the raw source value to a preserved `legacy.*` field (§5). Proposed profile rules for a future version: `oracle_ddmonyy_to_date` and `csv_to_array` |

---

## 7. PROFILE FEEDBACK

For the `oracle` profile / recon harness (do not patch locally — these are upstream):

1. **`tier2_aggregates` sum asymmetry (H1).** SQL `SUM(<non-numeric>)` errors → `None`;
   Mongo `$sum` over the same field → `0`. Guard the comparison with "both sides numeric",
   or skip `sum` when either side is `None`. This is a false-FAIL generator for every
   string-heavy estate, i.e. every Oracle estate.
2. **Missing canonicalization rules (H2):** `oracle_ddmonyy_to_date` (`VARCHAR2` date strings
   → BSON date, with an unparseable → `None` policy) and `csv_to_array` (delimited
   `VARCHAR2` → array, with an empty-token policy). Legacy Oracle estates store dates and
   lists as strings constantly; without these, every real conversion has to be modeled as a
   preserved raw field to stay recon-visible.
3. **`discovery_commands` gaps.** Add to the profile:
   - per-column population (`SELECT COUNT(col) …`) — 113 of 155 columns here are 100% NULL,
     which changes the model, the mapping and the coverage gaps. Nothing in the current
     command set reveals it.
   - `all_tab_columns.char_length` (the current list selects `char_used` but not the length,
     so `source_type` in the mapping spec cannot be written from the census output alone).
   - a "declared vs actual relationship" probe: this estate has **zero** foreign keys, so the
     constraints query returns nothing and the real cardinality rules have to be found by
     `NOT EXISTS` counts. Suggest an anti-join template in `conversion_patterns`.
   - `all_tables.num_rows` is NULL without gathered statistics (gap G5) — the profile should
     say "verify with `COUNT(*)`", not present it as a row estimate.
4. **`known_incompatibilities` addition — trigger-maintained shadow-uppercase columns.**
   The NLS row only catches `NLS_COMP`/`NLS_SORT`. Estates that compare case-insensitively
   with a `*_UPPER` column plus a trigger look binary-collated to the census and quietly
   migrate a derived column as data. Suggested required decision: collation-aware index,
   drop the shadow column.
5. **`known_incompatibilities` addition — unenforced relationships.** "No FK constraint but
   an application-level parent/child" deserves its own row: it decides embed cardinality
   (`child_where`) and the orphan quarantine policy, and it is invisible to the constraints
   query.
