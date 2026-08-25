# mongo_customers

Moves the customer estate off Oracle billing and into MongoDB.

Sources: `OW_BILLING.CUSTOMER_MASTER` (155 columns) and the
`OW_BILLING.ENTITY_ATTR_VALUE` attribute table, which billing has been using as
a side channel for anything the 155 columns could not hold.

Target: one document per customer in `ow_tp_mongodb_<ns>.customers`, with every
row that could not be carried over faithfully recorded in
`ow_tp_mongodb_<ns>_quarantine.customers_quarantine`.

## Target model

| Oracle | Document |
| --- | --- |
| `CUST_ID` | `customer_id`, and `_id` as `uuid5(unit-namespace, "<ns>:<CUST_ID>")` |
| `CUST_NO`, `CUST_NAME`, `LEGAL_NAME`, `TENANT_ID` | `customer_no`, `customer_name`, `legal_name`, `tenant_id` |
| `SIGNUP_DT` (`DD-MON-YY` text) | `signup_dt`, a BSON date in UTC |
| `RELATED_ACCT_IDS`, `PROMO_CODES_CSV` | `related_acct_ids`, `promo_codes` — BSON arrays |
| the six `*_AMT` columns | `balances.*` as `Decimal128` |
| `ENTITY_ATTR_VALUE` rows | `attributes.<ATTR_NAME>` — names carried verbatim |
| the remaining sparse columns | the `legacy` subdocument, written only when the source value is non-null |

`_id` is derived, never random, so a rerun addresses the same document instead of
inserting a second copy of the same customer.

## Fidelity rules

- A `SIGNUP_DT` that is not a real `DD-MON-YY` date is quarantined and the field
  is left off the document. It is never coerced, defaulted, or nulled — the
  billing team needs to know which 50 customers have an unusable signup date, and
  a document that says `1900-01-01` hides that.
- A malformed list is tolerated: the elements that do parse are kept and the row
  is attributed in quarantine with the raw source string.
- A well-formed empty list becomes `[]` — not `null`, and not `[""]`.
- A value that will not decode as UTF-8 is quarantined with its raw bytes as hex,
  never replaced with a substitution character.
- A missing required source value fails closed: no document is written.
- A run over an empty source set is a no-op and leaves prior output untouched.

The collection carries a `$jsonSchema` validator with `additionalProperties:
false`, so the two shapes that legacy code tends to write — a string
`signup_dt`, and a stray 156th top-level field such as `tax_region_override` —
bounce with server error 121 instead of landing.

## Running it

Needs the Oracle estate up (`make oracle-billing-up`, `make oracle-billing-seed
NS=demo`) and a document store at `TP_MONGODB_URI`.

```sh
make mongo-customers-test                 # transform contract tests, no services needed
make mongo-customers-migrate NS=demo SUMMARY_OUT=run1.json
make mongo-customers-migrate NS=demo SUMMARY_OUT=run2.json   # idempotency: identical numbers
make mongo-customers-recon   NS=demo RUN_SUMMARIES="run1.json run2.json"
```

Recon recomputes every count, the line-format md5 checksum, and both planted
anomaly sets from the document store itself, compares the anomaly sets as sets
(reporting `missing` and `unexpected`), and exits non-zero if any check fails.
It writes `docs/tech-partnerships/recon/mongo_customers.recon.json`; run it under
`TP_FAKETIME` (as `scripts/tp-run-deterministic.sh` does) so the committed report
is byte-reproducible.
