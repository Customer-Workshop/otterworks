# Wave 1 independent recon report

Verifier session: migrated none of this wave. Every verdict below comes from a harness run
this session made itself, against the live Oracle source (`OW_BILLING`, read-only) and the
Atlas target `ow_billing_migration`. The children's pasted evidence was not used.

**Wave verdict: PASS.** All four batches merged.

| Unit | Batch | PR | Mode | Verdict | merge_eligible |
|---|---|---|---|---|---|
| U2-customers (customers, customer_history) | w1-b01 | #1567 | live | PASS | true |
| U3-invoices (invoices, invoice_lines_orphaned) | w1-b02 | #1568 | live | PASS | true |
| U4-usage (usage_events, rating_periods) | w1-b03 | #1565 | live | PASS | true |
| U5-ancillary (credit_notes, notifications, audit_log) | w1-b04 | #1564 | live | PASS | true |

## How the gates were re-run

Mapping slices were regenerated from `.migration/03_mapping_spec.json` in a scratch
directory outside `.migration/`, with `.migration/02_tolerances.json` and
`.migration/canonicalization.json` copied unchanged. Tolerances were not altered. One live
run per unit, source concurrency 2, seed 714559852.

Tier counts from this session's `result.json` files:

| Unit | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Findings |
|---|---|---|---|---|---|
| U2-customers | 3 | 29 | 33,333 | 26 | none |
| U3-invoices | 6 | 21 | 168,756 | 17 | none |
| U4-usage | 3 | 6 | 820 | 4 | none |
| U5-ancillary | 3 | 9 | 6 | 6 | none |

No tier reported a mismatch, so no source re-run for drift was needed and no unit is marked
DRIFT-EXPLAINED.

Two mapping details had to be rendered before the harness would accept the spec, neither of
which changes what is graded: array-index target paths (`addresses.0.city` and similar) are
not addressable by the harness's field paths, and the `invoices` collection has two source
roots (`INVOICE_HEADER` and `INVOICES`), which the harness grades as two scoped entries. The
fields that fall out of the graded set are covered by the probes below.

## Probes past the gate

Run directly against source and target, independent of the harness.

- Row counts: customers 25,000 = 25,000; invoices 18,753 = 18,750 conversion + 3 billing;
  orphan invoice lines 37 = 37; usage_events 814; rating_periods 3; credit_notes 5;
  notifications 1.
- Empty collections: `customer_history` and `audit_log` are empty in the target because
  `CUSTOMER_MASTER_HIST` and `BILLING_AUDIT_LOG` are empty in the source (0 = 0).
- Duplicate keys: no duplicates on `customers.custNo`, `legacy.sysKey`, `legacy.custSeqNo`,
  or `invoices.invoiceNo`; the harness saw 0 duplicate source keys on every keyed diff.
- Embedded arrays: 149,965 invoice line items = 149,963 attached `INVOICE_LINE` rows + 2
  `INVOICE_LINES` rows; line-count distribution per invoice matches source exactly;
  customer attributes 8,333 = 8,333 `ENTITY_ATTR_VALUE` rows; dunning attempts 1 = 1.
- Array-index fields the gate cannot address: physical-address city and zip histograms match
  the source exactly (6 cities, 6 zips, all counts equal); the source holds no mailing
  address at all and the target's second address entry is empty for all 25,000 customers.
- Denormalised header fields: 18,745 invoices carry `customer.custNo`/`customer.name`,
  matching the 18,745 headers whose lines carry a customer number; no header has conflicting
  customer values across its lines, and no name disagrees with `CUSTOMER_MASTER`.
- `lines[].servicePeriod`: 149,963 non-null both sides, including the 68,340 rows whose
  period runs backwards in the source — the same 68,340 backwards ranges appear in the
  target, so the anomaly is carried, not invented or silently repaired.
- Null and missing rates: `flags.dunningExempt`, `balances.ltdBilled`, `contactNotes` are
  null for all 25,000 customers, matching empty source columns; `totals.subtotal`,
  `totals.tax`, `dunning` and `periodId` are absent on exactly the 18,750 conversion
  invoices, which is what the mapping spec calls for; `invoiceNo` is absent only on the 3
  billing-estate invoices.
- Boundaries: invoice totals min 20.81, max 19,999.51, sum 187,618,458.58 identical on both
  sides; no zero or negative totals; no null line amounts.
- Anomaly budget matches the wave contract exactly: 37 orphaned invoice lines, 50
  unparseable `SIGNUP_DT` values (each kept as `legacy.signupDtRaw` with a null date), 31
  malformed `RELATED_ACCT_IDS` lists (each kept as `legacy.relatedAcctIdsRaw`).

## Cross-unit consistency

- Every `invoices.customer.id` exists in `customers`; the customer `_id` set is exactly the
  source `CUST_ID` set.
- No orphaned invoice line points at an invoice that exists in `invoices`; all 37 stay
  dangling, as in the source.
- Every `invoices.periodId` exists in `rating_periods`.
- `usage_events`, `rating_periods`, `credit_notes` and `notifications` reference only tenant
  ids present in `tenants`.
- `customers` and `invoices` reference 50 tenant ids that are not in `tenants`. The same 50
  ids are missing from the source `TENANTS` table, so this is carried-over source breakage,
  not a migration defect. Recorded as a finding for the cutover pack.

## App-level parity replay

Tier 4 was replayed by this session from the recorded operation files
(`.migration/ops/U3-invoices.json`, `U4-usage.json`, `U5-ancillary.json`, and the customers
operations recorded under `.migration/recon/U2-customers/inputs/`): 53 operations across the
four units, all matching. These cover the transformations the value tiers cannot grade —
Y/N flags, CSV lists, `DD-MON-YY` dates, and CODES-decoded fields.

## Findings

1. All four wave 1 units pass an independent live recon run and all four PRs were merged.
2. Customers and invoices point at 50 tenant ids that do not exist in the tenants
   collection, exactly as in the legacy source, so the gap predates the migration.
3. The `invoices` collection mixes two shapes because it has two legacy sources: 18,750
   converted invoices carry numeric line type codes and no subtotal, tax, period or dunning,
   while the 3 billing-estate invoices carry string line types and no invoice number.
4. 68,340 invoice lines have a service period that ends before it starts; the migration
   carries them unchanged rather than repairing them.
5. Three customer fields (`flags.dunningExempt`, `balances.ltdBilled`, `contactNotes`) are
   null for every customer because the legacy columns are empty everywhere.
6. The harness cannot address array positions or two-root collections, so the mapping had to
   be rendered into harness terms before it would run; the fields this leaves out were
   checked by hand here and all match.
