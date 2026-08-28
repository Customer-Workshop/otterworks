# 06 — Decision log

All decisions below were settled at intake on **2026-08-28** and must not be re-asked at
STOP A.

| ID | Decision | Owner | Date | Evidence |
|---|---|---|---|---|
| SCOPE-1 | `OW_BILLING` only; `COMMISSION_DW` is out of scope for this run. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:149-154` |
| DATA-1 | Lakehouse Federation over JDBC to Oracle is approved; coexistence is federation-first and recon mode is `LIVE`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:138-145,153-154` |
| TOL-1 | Money comparisons are exact to the cent; money remains `DECIMAL(14,2)`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156` |
| TOL-2 | Unparseable `VARCHAR2(9)` dates quarantine the row, continue loading, and count in recon. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156` |
| PILOT-1 | Pilot is exactly `PKG_RATING` plus `PKG_INVOICING`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157` |
| D4-1 | Consumer population is declared `UNMAPPED`; carry it as an explicit coverage gap. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157-159,169-176` |
| D10-1 | Use targeted grants, not `SELECT_CATALOG_ROLE`; grants are applied and verified. | Customer / DBA | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:159,178-194` |
| D4-2 | No audit observation window; customer accepted the unmapped-consumer risk. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:160,196-224` |
| NOTIFY-1 | Route only blocking STOP A/B/C/E readiness, STOP D wave close with exception count, and fan-out halts to `#ow-migrations` (`C0BQP3P965V`). | Migration lead | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:233-236`; `.migration/00_context.md` |
