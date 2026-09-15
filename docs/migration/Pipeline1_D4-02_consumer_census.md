# D4-02 — who reads the OW_BILLING invoicing surfaces, and what happens to each

Mechanical census, not recall. Method: grep the whole repo for the Oracle connection surface
(`ORACLE_HOST`/`ORACLE_SERVICE`/`oracledb`/`cx_Oracle`/`jdbc:oracle`), for `OW_BILLING` and
`FREEPDB1`, for the package entrypoints (`pkg_invoicing`, `pkg_dunning`,
`fn_invoice_preview`, `fn_overdue_accounts`, `sp_issue_invoice`, `sp_suspend_overdue`), and
for direct reads of the invoicing tables (`invoice_header`, `invoice_line`, `invoices`,
`invoice_lines`, `customer_master`, `codes`). 158 files matched; the table below is what is
left after separating runtime callers from fixtures, tests, docs, the legacy DDL itself and
this migration's own artifacts.

The routing rule is the owner's (D4-02): package-entrypoint callers get a thin temporary shim
that keeps the existing call shape over Lakebase; direct table readers are repointed to the
Postgres wire protocol; anything that fits neither is flagged rather than forced.

## Runtime consumers

| # | Consumer | What it actually calls | Class | Action |
|---|---|---|---|---|
| 1 | `services/legacy-billing/app/app.py` (Flask, `psycopg`) | `billing.fn_invoice_preview`, `billing.sp_issue_invoice`, `billing.fn_overdue_accounts`, `billing.sp_suspend_overdue` | package entrypoints | **SHIM.** Thin service in front of Lakebase that keeps the four call shapes byte-identical, including the swallowed-exception behaviour of the dunning path. Temporary, and it needs a named removal owner (see below). |
| 2 | `services/legacy-billing/app/reports.py` (Flask blueprint, `oracledb` direct to `FREEPDB1`) | `invoice_header`, `invoice_line`, `codes`, `customer_master` with `NVL`/`TO_CHAR` and the legacy join that preserves orphan lines | direct table reader — but of **analytical-track** tables | **FLAGGED, not repointed.** It is a direct reader, so the rule says Postgres wire; but every table it reads is on the Delta track (`ow_tp.silver.invoice_header` / `invoice_line`), which Postgres wire cannot serve. Repointing it means DBSQL and rewriting the Oracle-specific SQL, and the orphan-line behaviour is contract (`docs/tech-partnerships/billing-report-contract.md`). Decision needed at STOP E: DBSQL repoint, or keep it on the shim until the report is rebuilt. |
| 3 | `frontend/admin-dashboard` — `core/services/billing-report.service.ts`, `pages/billing-report/` | HTTP `GET /billing-api/api/reports/{month-end,reconciliation}` | indirect (HTTP) | **No action.** It holds no database connection and is deliberately backend-agnostic; it follows whatever serves the report contract. Listed so nobody counts it twice. |

No other service in the repo holds a connection to the billing estate: `billing-service`,
`report-service` and `api-gateway` matched only on unrelated strings (an audit-service URL, a
build-time read of the legacy `seed.sql`).

## Matched but not consumers

Fixtures and dev infrastructure: `docker-compose.oracle-billing.yml`, the `oracle-billing-*`
Makefile targets, `testdata/legacy/oracle_billing_seed.py`,
`services/legacy-billing/db/**` (the legacy DDL and packages themselves — read-only source),
`services/billing-service/scripts/generate_seed.py` (reads the seed file at build time).

Test and demo harnesses: `procs/harness/oracle_record.py`, `procs/oracle/**`,
`procs/scenarios/**`, `procs/transcripts/**`, `services/legacy-billing/tests/**`,
`frontend/admin-dashboard/**/billing-report.component.spec.ts`, `scripts/tp_pain/`,
`scripts/tp_break/`.

Documentation: `docs/tech-partnerships/**`, `.agents/skills/**`.

Unrelated estate: `services/industry-solutions/insurance/**` is a different Oracle database
and is out of pipeline-1 scope.

## Open items for STOP E

1. **Shim removal owner is unnamed.** The shim in row 1 is explicitly temporary and the owner
   required a named removal owner in the STOP E packet. Nobody in this repo identifies that
   person, so it has to come from the customer.
2. **Row 2 needs a routing decision.** It is the one consumer the D4-02 rule does not cover,
   because its tables are analytical-track.
3. No repoint happens before STOP E authorisation, and none is performed by this session.
