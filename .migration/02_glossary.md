# Glossary

| Term | Plain meaning |
|---|---|
| `OW_BILLING` | The Oracle schema holding OtterWorks billing: tenants, plans, subscriptions, usage, rating, invoices, dunning. |
| Tenant | A customer account in the billing model (`TENANTS`); demo rows are `demo::tenant-*`. |
| Rating | Turning usage events into priced line items for a period (`pkg_rating`, `RATING_PERIODS`, `RATING_RESULTS`). |
| Invoicing | Issuing an invoice from rated usage (`pkg_invoicing.sp_issue_invoice`, `INVOICES`, `INVOICE_LINES`). |
| Dunning | Chasing and suspending overdue accounts (`pkg_dunning`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS`). |
| `CUSTOMER_MASTER` | 155-column denormalized customer record (`ADDR_LINE_1..6`, `FLAG_01..20`, `UDF_01..40`). |
| `INVOICE_HEADER` / `INVOICE_LINE` | Legacy bulk reporting copies of invoices (distinct from the transactional `INVOICES`/`INVOICE_LINES`); contain 37 planted orphan lines. |
| `_HIST` tables | Trigger-maintained full-row history copies. |
| `CODES` | Generic lookup for magic-number `*_CD` status columns. |
| EAV | `ENTITY_ATTR_VALUE`, key/value attribute dumping ground. |
| NS / `ns=demo` | Seed namespace; every target row and job carries it. |
| SCN | Oracle System Change Number; the consistency pin for freeze-and-load and recon. Seed SCN 2137574. |
| Operational track | Tables/procedures the application transacts against; target Lakebase Postgres. |
| Analytical track | Reporting/batch-only surfaces; target Delta on Unity Catalog. |
| Lakebase branch | Copy-on-write Postgres branch of project `ow-tp-billing`; one per wave batch. |
| Debezium / LogMiner | Log-based CDC from Oracle redo into Kafka; needs supplemental logging (D10-1). |
| Recon | Machine-checked comparison of legacy vs migrated data; verdict in `*.recon.json`. |
| STOP A..E | The five human decision points (target/tolerances/access, pipeline choice, plan, wave review, cutover). |
| D1..D10 | Dependency classes; D10 = environment/access. |
| CUSTBILL | The companion ksh/awk/Perl batch chain (pipelines 2/3, not this one). |
