# Billing report contract (admin dashboard ⇄ billing estate)

The admin dashboard's **Billing Report** page (`/billing-report`) renders whatever
backend currently serves this contract. On `tech-partnerships` that backend is the
legacy billing app (`services/legacy-billing`), which reads the Oracle billing
estate directly. **Re-plumbing this page to MongoDB is a migration unit**: the
migrated backend must serve the same two endpoints with the same JSON shape —
only `source.engine` and the reconciliation checks change. The UI is not edited
during the migration.

## Wiring

- Dev proxy: `frontend/admin-dashboard/proxy.conf.mjs` maps `/billing-api/*` to
  `BILLING_REPORT_API_URL` (default `http://localhost:8096`, the legacy app from
  `make procs-up`). Cutover = point `BILLING_REPORT_API_URL` at the migrated
  backend that serves this contract from MongoDB.
- The legacy app reaches Oracle via `ORACLE_HOST`/`ORACLE_PORT`/`ORACLE_USER`/
  `ORACLE_PASSWORD`/`ORACLE_SERVICE` (defaults: localhost:52521, ow_billing,
  FREEPDB1 — `make oracle-billing-up` + `make oracle-billing-seed NS=<ns>`).
- Namespacing: `ns` query param (default `demo`), resolved to the deterministic
  conversion `batch_no` (`sha256(ns)[:8] % 90_000_000 + 1_000_000`), matching
  `testdata/legacy/oracle_billing_seed.py`.

## `GET /api/reports/month-end?ns=<ns>`

Legacy semantics are contractual: statuses resolve through the `CODES` lookup
(`INV_STATUS`), unmapped codes render as `UNKNOWN(<cd>)`, line types are DECODEd
inline (1 CHARGE, 2 CREDIT, 3 ADJUSTMENT, 9 MISC), and orphaned `INVOICE_LINE`
rows fall out of the join. Amounts are strings with exactly two decimals.

```json
{
  "report": "month-end-finance",
  "namespace": "demo",
  "batch_no": 12345678,
  "source": {"engine": "oracle", "system": "...", "detail": "..."},
  "generated_at": "2026-08-01T00:00:00Z",
  "by_status": [
    {"status": "ISSUED", "invoice_count": 100, "header_total_amt": "12345.00"}
  ],
  "by_status_line_type": [
    {"status": "ISSUED", "line_type": "CHARGE", "line_count": 400,
     "line_amount": "12000.00", "line_tax": "345.00", "invoices_touched": 100}
  ]
}
```

Migrated backends set `source.engine` to `mongodb` (the page's badge flips from
"Legacy Oracle Estate" to "MongoDB Atlas") and must match the legacy numbers to
the cent for the same namespace.

## `GET /api/reports/reconciliation?ns=<ns>`

```json
{
  "namespace": "demo",
  "batch_no": 12345678,
  "source": {"engine": "oracle", "system": "...", "detail": "..."},
  "generated_at": "2026-08-01T00:00:00Z",
  "balances": {"customer_count": 25000,
               "current_balance_total": "1234567.00",
               "past_due_total": "8901.00"},
  "status": "baseline",
  "checks": []
}
```

`status` drives the page banner:

- `baseline` (legacy only): blue "Legacy source of truth" — the estate is the
  baseline, there is nothing to compare against, `checks` is empty.
- `pass` (migrated): green — every check in `checks` has `"status": "pass"`.
- `fail` (migrated, e.g. after drift): red banner naming the failing checks and
  a red current-balances tile. Check objects: `{"name", "status", "expected"?,
  "actual"?}` (e.g. `{"name": "customers-checksum", "status": "fail"}`).

## Error behavior

If the backing estate is unreachable, respond `503` with
`{"error": "legacy estate unavailable", "detail": "..."}` — never fabricate
numbers. The page shows a retryable error state.

## Tests

- Backend contract: `services/legacy-billing/tests/test_reports.py`
  (`uv run --with pytest --with flask==3.1.1 pytest tests/` from
  `services/legacy-billing`).
- UI behavior: `frontend/admin-dashboard/src/app/pages/billing-report/billing-report.component.spec.ts`
  (`npm test` in `frontend/admin-dashboard`).

A migrated backend is done when the backend contract tests (pointed at it) and
the cent-exact parity against the legacy golden both pass.

## Storefront billing facade (`/api/v1/billing`, via api-gateway)

The storefront calls these routes through the gateway with a bearer access
token:

- `GET /plans` → plans with `plan_id`, `plan_code`, `tier`, `monthly_fee`,
  `included_units`, and `overage_rate`.
- `GET /me[?on=YYYY-MM-DD]` → tenant identity, status, entitlement, and the
  first customer balance record.
- `GET /entitlement?on=YYYY-MM-DD` → entitlement rows for the requested date.
- `POST /plan-change` with `{"plan_id":"...","effective_on":"YYYY-MM-DD"}` →
  `{"status":"changed","entitlement":[...]}`.
- `GET /usage?period_start=YYYY-MM-DD&period_end=YYYY-MM-DD` → summary,
  rating, and the last 50 usage events.
- `GET /invoices` → newest-first invoice headers.
- `GET /invoices/<invoice_id>/lines` → invoice lines owned by the caller.
- `GET /customer` → all legacy customer fields plus `attributes`.
- `GET /admin/overdue?as_of=YYYY-MM-DD` → overdue accounts for admins.
- `GET /admin/dunning?as_of=YYYY-MM-DD` → scheduled dunning attempts for
  admins.

The gateway validates the bearer JWT, deletes inbound `X-User-ID`,
`X-User-Email`, and `X-User-Roles` headers, then sets those headers from the
validated claims. The facade uses `X-User-ID` as the tenant identity,
`X-User-Email` for onboarding, and comma-separated `X-User-Roles` for admin
authorization. Clients cannot override these headers.

Representative response shapes:

```json
{"plan_id":"10000000-...","plan_code":"STANDARD","tier":"STANDARD",
 "monthly_fee":"99.00","included_units":"1000","overage_rate":"0.05"}
```

```json
{"tenant_id":"a0000000-...","name":"OtterWorks Admin","status":"ACTIVE",
 "tax_exempt":"N","entitlement":[{"plan_code":"STANDARD","effective_on":"2026-01-01"}],
 "customer":{"cust_no":"OW-ADMIN-0001","cur_bal_amt":"0.00",
 "past_due_amt":"0.00","credit_hold_yn":"N"}}
```

```json
{"summary":[{"kind":"API","units":"12"}],"rating":[{"total":"12.00"}],
 "events":[{"id":"30000000-...","occurred_at":"2026-02-01",
 "units":"12","kind":"API"}]}
```

```json
[{"invoice_id":"50000000-...","period_start":"2026-02-01",
 "period_end":"2026-02-28","subtotal":"99.00","tax":"0.00",
 "total":"99.00","status":"ISSUED"}]
```

```json
{"cust_id":"40000000-...","cust_no":"OW-ADMIN-0001",
 "cust_name":"OtterWorks Admin","cur_bal_amt":"0.00",
 "past_due_amt":"0.00","credit_hold_yn":"N",
 "attributes":[{"attr_name":"TAX_REGION_OVERRIDE","attr_value":"US",
 "attr_type":"STRING"}]}
```

Admin collection responses are arrays of the Oracle report rows; fields retain
their lowercase contract names, including account, invoice, amount, schedule,
and status fields.

When Oracle cannot be reached, every facade route returns HTTP 503:

```json
{"error":"legacy estate unavailable",
 "detail":"the Oracle billing estate is not reachable"}
```

## `GET /api/reports/finance?ns=<ns>`

This endpoint serves the namespace's persisted month-end batch artifact rather
than querying Oracle live. The artifact is produced by the Oracle CUSTBILL
extract, the ksh/bash fixed-width parser, and the Perl finance rollup. The
dashboard labels this panel **Month-end finance batch**.

```json
{
  "ns": "demo",
  "source": {
    "system": "CUSTBILL month-end batch",
    "detail": "ksh/Perl chain over Oracle CUSTBILL extract",
    "generated_at": "2026-02-28T02:10:00+00:00",
    "file": "finance_billing_20260228.csv"
  },
  "rows": [
    {"currency": "USD", "record_type": "INVOICE",
     "record_count": 2, "total_amount": "25.00"}
  ],
  "totals": {"record_count": 2, "total_amount": "25.00"}
}
```

The Perl job writes a CSV report and copies it byte-for-byte to a `.xls` name;
the endpoint parses either representation. If no report has been generated for
the requested namespace, it returns HTTP 404:

```json
{"error":"no finance report for namespace",
 "detail":"run make tp-month-end NS=demo"}
```
