# Oracle invoice migration

`mongo_invoices` migrates invoice headers and lines from the legacy Oracle
billing estate into a namespace-scoped MongoDB document model.

## Source tables

- `OW_BILLING.INVOICE_HEADER`
- `OW_BILLING.INVOICE_LINE`

The source rows are selected by the namespace conversion batch. An invoice
header is the parent document. A line whose `INVOICE_ID` has no matching
header is not attached to a guessed or synthesized invoice.

## Target collections

For namespace `<ns>`:

- Database `ow_tp_mongodb_<ns>`, collection `invoices`
- Database `ow_tp_mongodb_<ns>_quarantine`, collection
  `invoice_lines_quarantine`

The default document-store URI is the local MongoDB fixture at
`mongodb://localhost:27017`. Set `TP_MONGODB_URI` only when an explicitly
approved target is required.

## Document model

Each invoice document contains:

- A deterministic UUID `_id` derived from the namespace and source
  `INVOICE_ID`
- `ns`, `invoice_no`, and UTC `issue_date`/`due_date`
- Decimal128 `header_total`, `lines_total`, and `lines_tax_total`
- `lines_count` and an embedded `lines` array
- Source provenance under `source`, including system, schema, table, invoice
  key, and batch number
- Customer identifiers under `customer`

Embedded line documents retain the source line key, line number and type,
description, Decimal128 quantity and monetary values, UTC line date, service
period, posted flag, and parsed GL account numbers. The bounded model is
25 lines per invoice; larger arrays are reported rather than truncated.

The invoices collection enforces the document contract with a strict
`$jsonSchema` validator and namespace-scoped indexes. Issue dates are stored
as BSON dates, not legacy date strings.

## Quarantine reason codes

Lines that cannot be represented safely in the invoice document model are
written to the quarantine collection with one of these reasons:

- `orphan_no_header`
- `null_amount`
- `null_quantity`
- `null_foreign_key`
- `invalid_encoding`
- `extra_delimited_fields`
- `invalid_date`
- `header_unusable`

Quarantine documents retain source identifiers and parsed values where
available. NULL amounts, quantities, and foreign keys are never replaced with
zero or a placeholder.

## Running

The wrapper pins `TZ=UTC`, `LC_ALL=C`, and `LANG=C` through
`scripts/tp-run-deterministic.sh`, then invokes `uv run --no-project` with
the pinned `oracledb==2.5.1` and `pymongo==4.10.1` dependencies.

Run the migration:

```bash
migrations/mongodb/mongo_invoices/run.sh migrate \
  --ns demo \
  --summary-out /home/ubuntu/tp-evidence/mongo_invoices-run.json
```

Run reconciliation:

```bash
migrations/mongodb/mongo_invoices/run.sh recon \
  --ns demo \
  --out docs/tech-partnerships/recon/mongo_invoices.recon.json \
  --rerun-summary-a /home/ubuntu/tp-evidence/run1.json \
  --rerun-summary-b /home/ubuntu/tp-evidence/run2.json \
  --empty-input-evidence /home/ubuntu/tp-evidence/empty-input.json
```

Run the pure transform self-test. It does not connect to Oracle or MongoDB:

```bash
migrations/mongodb/mongo_invoices/run.sh selftest
```

An empty source namespace is a no-op: existing target documents remain
untouched and no collection is created solely by the empty run.
