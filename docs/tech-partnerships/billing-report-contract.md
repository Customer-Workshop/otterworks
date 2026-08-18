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
