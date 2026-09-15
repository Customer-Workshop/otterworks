# PRD Open items 1–5 — evidence and proposals (for STOP B)

The PRD leaves five decisions open. Each one below has the evidence that answers it and a
proposal. The mapping spec already implements the proposal; a different answer at STOP B
changes the spec before any wave runs.

---

## 1. Drop the 80 `flag_NN` / `udf_*` columns, or carry them as `attributes[]`?

**Proposal: drop all 80.** The PRD's own condition ("if profiling confirms they are all
NULL") is met.

Evidence: each of the 80 columns was counted individually over all 25,000
`CUSTOMER_MASTER` rows — `FLAG_01..FLAG_20`, `UDF_01..UDF_40`, `UDF_AMT_01..UDF_AMT_10`,
`UDF_DT_01..UDF_DT_10`. Every one returned 0 non-null values. No package, trigger or
application file reads any of them: `all_dependencies` has no reference, and a repo-wide
search finds them only in the DDL and in the `TRG_CUSTOMER_MASTER_HIST` column list that
copies the whole row. `CUSTOMER_MASTER_HIST` carries the same 80 columns and is empty.

Consequence recorded in the spec: `customers.dropped_columns`. The recon count of mapped
fields will not include them, so a future non-null value would surface as an unmapped
source column, not silent loss.

---

## 2. `usage_events`: time-series collection or plain collection?

**Proposal: plain collection**, with a `{tenantId: 1, occurredAt: 1}` index and a
`$jsonSchema` validator.

Evidence, in order of weight:

1. **The PRD identity rule forbids it in practice.** Every `_id` is the source UUID and
   reconciliation is a keyed diff on `_id`. A time-series collection does not support a
   unique index on `_id`, keyed upsert, or `_id`-based re-load, so the unit would not be
   idempotent and the recon key would have to be invented — a crosswalk by another name,
   which the PRD rules out.
2. **The only reader does range-by-tenant work that a compound index serves.**
   `PKG_RATING.compute_rating` selects `SUM(units)` from `USAGE_EVENTS` for one tenant
   between two dates (comparing `TO_CHAR(occurred_at,'YYYYMMDD')`, which the migration
   replaces with a real date range). `PKG_INVOICING` reaches usage only through
   `PKG_RATING`. Nothing else reads the table.
3. **Scale does not call for it.** 814 rows in the fixture, on an M0.

Revisit when production usage volume is known and the collection is append-only and never
re-loaded; the conversion is a rewrite either way.

---

## 3. One `invoices` collection with a `source` field, or two collections?

**Proposal: one collection**, `source: "conversion" | "billing"`.

Evidence:

- The PRD already states the reason (one customer query for dunning and statements).
- The keys do not collide: `INVOICES.id ∩ INVOICE_HEADER.invoice_id` = **0 rows**, so the
  PRD identity rule (`_id` = source UUID) holds for the union without qualification.
- The shapes differ only where the source differs, and the difference is real, not a
  nullability artefact: conversion rows carry `total_amt` only, billing rows carry
  subtotal, tax and total. The spec therefore writes `totals.subtotal`/`totals.tax` for
  billing rows and **omits** them for conversion rows rather than writing zeros.
- The two estates have disjoint writers (`PKG_INVOICING`/`PKG_DUNNING` write the
  transactional estate; the CUSTBILL batch chain wrote the conversion feed) and disjoint
  readers (the RPT-114 month-end report in `services/legacy-billing/app/reports.py` reads
  only the conversion estate). A `source` filter reproduces either reader exactly.

The 37 orphaned lines stay out, in `invoice_lines_orphaned`, per the PRD.

---

## 4. Retention for `customer_history`, `subscription_history`, `audit_log`

**Proposal: TTL of 90 days on `audit_log` only; no retention on the two history
collections in v1.**

Evidence:

- `JOB_PURGE_AUDIT_LOG` runs `DELETE FROM billing_audit_log WHERE logged_at < SYSDATE - 90`
  daily at 03:30. Ninety days is the estate's existing, stated policy for this table, so a
  TTL index on `loggedAt` (`expireAfterSeconds: 7776000`) is a like-for-like carry-over,
  not a new policy. **The job is currently `enabled=FALSE`**, so the TTL would begin
  enforcing a rule the source has stopped applying — that is the part that needs a human
  answer. Recommended: enable the TTL, because the rule is the documented policy and the
  table is empty today (0 rows), so nothing is deleted at migration time.
- No purge job, retention rule or reader exists for `CUSTOMER_MASTER_HIST` or
  `SUBSCRIPTIONS_HIST`. Both are trigger-fed audit trails and both are currently empty.
  Inventing a TTL would destroy history the source keeps forever.

---

## 5. Who owns `segment`, `region`, `territory`, `channel`, `rate_class`?

**Proposal: no owner found. Carry all five as integers, unchanged, and route the question
to the billing data owner as a finding.**

Evidence:

- `CODES` holds 10 code types (`CUST_STATUS, CUST_TYPE, DUN_STATUS, INV_STATUS,
  NOTIF_KIND, PHONE_TYPE, PLAN_TIER, SUB_STATUS, TENANT_STATUS, USAGE_KIND`). None of the
  five has rows, so `PKG_OW_UTIL.f_code_desc` would return `UNKNOWN(<n>)` for every value.
- No package, trigger, view, scheduler job or application file reads any of the five.
  They appear only in the two table definitions, the history trigger's copy list, and the
  seed script.
- `TERRITORY_CD`, `CHANNEL_CD`, `RATE_CLASS_CD` are **100% NULL** across 25,000 rows.
  `SEGMENT_CD` has 9 distinct values (1–9) and `REGION_CD` has 12 (1–12), both non-null on
  every row, with no legend anywhere in the estate.

So the PRD's fallback rule applies verbatim: an integer with no `CODES` row stays an
integer. The fields keep their PRD names (`segment`, `region`, `territory`, `channel`,
`rateClass`) and their values; nothing is decoded, renamed or dropped. Carried in the
dependency register as **D5-1**, open against the data owner. If the legend arrives later,
decoding is a one-pass update, not a re-migration.
