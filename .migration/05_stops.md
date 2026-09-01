# 05 — Stop decision log

## STOP A — setup and engagement intake

Artifacts presented: `00_context.md`, `01_conventions.md`, `02_tolerances.json` v1,
`03_mapping_spec.json` (placeholder), `04_progress.md`, `profile.canon.json`.
Profile: `oracle`. Target: `ow_tp_demo` on Atlas `otterworks-demo`.

Status: **APPROVED** 2026-09-01. Playbook 2 (`!mongo_model`) started only after the
approval below was recorded verbatim.

### Intake answers already given by the approver

| Question | Answer (as selected) |
|---|---|
| Unit scope, given Postgres/DynamoDB have no source profile | "Oracle-only: customers + invoices; declare documents/files as a coverage gap at STOP A" |
| Read-only Oracle principal | "Use ow_billing as-is and declare the write-capable-principal gap at STOP A" |

### Decision table

FACT = probed against the live source or target. PROPOSED = my recommendation, resolved by
this approval.

| # | Decision | Status | Resolution | Consequence of the choice |
|---|---|---|---|---|
| D1 | `null_missing_equiv` | PROPOSED | `equivalent` — an absent target field equals a source NULL | Loads may omit null fields instead of writing explicit nulls, which is the smaller document. Recon cannot then catch "field dropped by the loader" as distinct from "field was NULL" — acceptable because Tier 2 compares null *rates* per field, so a systematic drop still shows up |
| D2 | Empty-string policy (`empty_string_is_null.target_policy`) | PROPOSED | `null` — write null/omit, never `""` | Matches Oracle, where `'' IS NULL` for VARCHAR2 and there is no distinction to preserve. If the app later needs "explicitly blank", that is a new value it must write itself; the migration will not invent one |
| D3 | Encoding / byte transparency | FACT-backed PROPOSED | Pass through byte-transparently: source is `AL32UTF8`, target BSON strings are UTF-8, no transcoding step. No LOB tier | Census FACT: the 4 in-scope tables have **no** CLOB/BLOB/RAW/XMLTYPE columns (VARCHAR2 122, NUMBER 42, CHAR 25, DATE 2), so the 16 MB document limit is unreachable and no GridFS decision is needed. If a later unit adds a LOB column this decision does not cover it |
| D4 | Malformed-record policy | PROPOSED | **Quarantine**, never reject or coerce. Field-level for bad values (the document still lands, the offending field is null and the raw value is written to `ow_tp_demo_quarantine.<unit>`); row-level for records with no valid parent (the row does not land, only the quarantine entry) | Coercing would silently invent data (a `31-FEB-24` becoming a real date is a fabricated fact); rejecting the whole load on first bad row makes the estate unmigratable. Quarantine keeps the anomaly auditable and countable. Direct recon consequence: the 37 orphaned `INVOICE_LINE` rows are row-level quarantined, so the mapping spec's embed **must** carry a `child_where` excluding them or Tier 1 fails 150,000 vs 149,963 by construction. Field-level quarantine leaves root counts unchanged at 25,000 |
| D5 | Empty-input semantics | PROPOSED | An empty source table is a **FAIL** for both load and recon | Guards against the failure mode where a broken extract loads nothing and recon happily agrees. Gap G2: the harness cannot enforce this — `tier1_counts` passes `0 == 0` vacuously — so each unit's loader carries a pre-load precondition check asserting a non-zero source count, and the PR states the count it asserted |
| D6 | Source-load concurrency cap | PROPOSED | `source_concurrency = 1` | The source is one Oracle Free container shared with the rest of the demo estate. Serial extraction is slower but keeps the legacy box's budget intact and timings reproducible. Gap G4: no throughput has been measured yet, so wave 2's 150,000-row embed load is unsized |
| D7 | Batch / trigger granularity | PROPOSED | One unit = one collection, loaded as a single namespace-scoped operation, **idempotent by re-run**: `delete_many({ns})` + bulk insert, or upsert-by-`_id`. Never `drop()` a collection | Retries start clean without a manual cleanup step. `drop()` is banned specifically because it destroys other namespaces' slices and any validator or index on the collection — a prior run lost a column in a shared table that way |
| D8 | Cutover principal | FACT | Customer-held; Devin never requests, holds, or stores it, and performs no production repoint | No cutover action appears in any playbook deliverable of this engagement |

### Approval

> Question 1: Selected: Approved as-is — proceed to !mongo_model (playbook 2)

Recorded 2026-09-01, in-session reply to the STOP A approval request (approver: the
engagement requester for this run). Approved as-is: no decision row amended.

Artifact versions approved: tolerances v1, mapping spec (placeholder, v0), profile.canon
resolved at STOP A, context/conventions/progress as of this commit.

## STOP B — data model sign-off

Artifacts presented: `06_census.md` (object census, stored-logic dispositions,
access-pattern evidence, anomaly scan), `03_mapping_spec.json` **v1.0.0** (2 collections,
51 mapped fields, 2 embeds, harness-validated), `04_progress.md` ledger.

Status: **APPROVED** 2026-09-01 for mapping spec version `1.0.0`. Wave 1 (`customers`)
starts under `!mongo_unit`; H1 is resolved by option (b), a repo-vendored pinned harness
copy carrying only the Tier-2 `sum` fix.

### Decision table (all PROPOSED; full evidence in `06_census.md` §6)

| # | Decision | Recommendation |
|---|---|---|
| D1 | `INVOICE_LINE` embed vs reference | Embed `invoices.lines[]` (max 23/invoice, ≤17 KB); 37 orphans row-quarantined |
| D2 | `ENTITY_ATTR_VALUE` embed shape | Embed as an **array** `attributes[]`, not a key/value object (187 duplicate `(entity, attr_name)` pairs) |
| D3 | Sequence-backed keys | Natural `_id` (`CUST_NO` / `INVOICE_ID`); `CUST_SEQ_NO` served by a `counters` collection seeded to 125,000; `EAV_ID` retired |
| D4 | 50 unparseable `SIGNUP_DT` strings | Field-level quarantine; document still lands with the raw string preserved |
| D5 | 31 malformed CSV lists | Field-level quarantine; raw preserved, array holds well-formed tokens |
| D6 | Case-insensitive name lookup | Collation index `{locale:"en", strength:2}` on `customers.cust_name`; drop the `CUST_NAME_UPPER` shadow column |
| D7 | LOB/BLOB handling | None needed — no LOB in scope |
| D8 | `CODES` lookup | Migrate `status_cd` as-is; descriptions from a static map reproducing `UNKNOWN(<cd>)` |
| D9 | Target index plan | Per `06_census.md` §6 (report-query driven; the source has no secondary index to port) |
| D10 | Sync/CDC | None — one-shot idempotent load, source frozen; CDC would require writing to the source |
| D11 | Wave order | `customers` → `invoices`, unchanged |
| D12 | Tolerance change | None; tolerances stay at version `1` |
| D13 | 113 all-NULL `CUSTOMER_MASTER` columns | Retired as a declared coverage gap |
| H1 | Tier-2 `sum` is not type-aware (false FAIL on every string/date/all-NULL field) | **Approved: option (b)** — wave 1 runs against a repo-vendored, pinned harness copy carrying only that fix; the upstream profile feedback still stands |
| H2 | No canon rule compares a `DD-MON-YY` string to a date, or CSV to an array | v1.0.0 maps the preserved raw value (`legacy.*`); proposed profile rules for a later version |

### Approval

Approved 2026-09-01, verbatim:

> Question 1: Selected: Approved — proceed to !mongo_unit wave 1, vendoring a pinned harness copy with the H1 fix

Scope of the approval: mapping spec `03_mapping_spec.json` version **1.0.0** (2 collections,
51 fields, 2 embeds, both roots and both embeds scoped to the deterministic `demo` batch
`85559852`), decisions D1–D13 as recommended, tolerances unchanged at version `1`, wave order
`customers` → `invoices`. No later mapping version inherits this approval.

### D6 follow-up, 2026-09-01 (wave 1 review)

Review of PR #1392 asked for `CUST_NAME_UPPER` to be dropped from the target document, which
would change the approved mapping version. Answer, verbatim:

> Question 1: Selected: Keep 1.0.0 as approved — retire the column at cutover

So mapping `1.0.0` keeps the field and the loaded documents carry it; the collation index on
`cust_name` remains the lookup path, and the column is retired at cutover rather than by an
unapproved mid-wave mapping change.

## STOP C — cutover readiness

Not reached.

## Routing log (`!mongo_migrate`)

| Timestamp (UTC) | Phase detected | Evidence read | Action taken |
|---|---|---|---|
| 2026-09-01T00:15Z | STOP A pending | `05_stops.md` STOP A "Status: **PENDING**", approval block still the `_(verbatim approval to be pasted here…)_` placeholder; `03_mapping_spec.json` still the playbook-2 placeholder; `04_progress.md` ledger shows both units `not started`, write-target registry `not loaded`, circuit breaker 0 failures for wave 1; no `recon/` evidence directory exists | Reported that the engagement is awaiting STOP A approval; no phase launched, no unit dispatched, no write to source or migration cluster |
