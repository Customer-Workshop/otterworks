# OtterWorks billing -> Databricks: what moved (run 20260927c)

One tenant, one vertical slice: signup -> subscription -> issue_invoice -> nightly CUSTBILL -> finance close on a dashboard.
Production Oracle `OW_BILLING` and Lakebase branch `production` were read-only / untouched throughout. Repoint declined at STOP E.

## The three numbers (legacy | Databricks | dbx-recon)

| Evidence | Legacy (Oracle / ksh+perl) | Databricks | dbx-recon |
|---|---|---|---|
| Invoice row, Tenant One, Feb-2026 (`sp_issue_invoice`) | id `109bb68d-8fc1-401b-9a8a-fa89e98e2388`, subtotal 49.00, tax 4.04, **total 53.04**, 5 lines, issued | Lakebase `mig-20260927c-exec` `billing.sp_issue_invoice`: same id, 49.00 / 4.04 / **53.04**, 5 lines, issued, audit log 4/4 in order | PASS (pkg_invoicing Tier 0-3 live; routine parity 44/44) |
| CUSTBILL nightly file (18,750 records, 1,237,500 bytes) | sha256 `c3e2cf43e099f9e17cc59a2b202cd876c103b8f21a8693eba45fb5fd7eb946db` | Lakeflow `ow_tp_20260927c_custbill` + paused render job: sha256 `c3e2cf43e099f9e17cc59a2b202cd876c103b8f21a8693eba45fb5fd7eb946db` | PASS (bronze 4 tables, 152k keyed rows sampled; rejects 0, quarantine wired) |
| Finance close total, ns=demo | **187,618,458.58** | gold `ow_tp.mig_20260927c_gold.finance_close` **187,618,458.58** = SUM(detail, 18,750 rows) | PASS x2 (Tier-2 aggregate 187,618,458.58); dashboard published |

## Also recorded live
Mar-2026 (psql) and Apr-2026 (through the legacy-billing app UI, side by side) issue_invoice on Lakebase exec vs Oracle fixture: same invoice ids (`8faeec95-...`, `a0e5370d-...`), total 53.04, 5 lines on both.

## What moved
- Wave 0: `billing` schema + reference tables on Lakebase `mig-20260927c-w0` (918 rows). PR #1729.
- Wave 1: `pkg_ow_util`, `pkg_plans`, `pkg_rating`, `pkg_invoicing` -> 19 PL/pgSQL routines + 8 state tables; live issue_invoice on `mig-20260927c-exec`. PR #1730. CUSTBILL ksh/perl chain -> Lakeflow SDP with expectations + quarantine, render job paused. PR #1731.
- Wave 2: gold `finance_close_detail` / `finance_close`, paused job `ow_tp_20260927c_finance_close`, AI/BI dashboard. PR #1732.

## What did not move (by design)
- `pkg_dunning`: dependency ledger DEP-010, no call edge from the slice; finding only.
- Analytics crons and the Scala job: findings only (DEP-009, `02_inventory.md`).
- Production Oracle, production Lakebase branch, shared `ow_tp.bronze/silver/gold`, Airbyte/Fivetran: no writes.

## Accepted by human override (harness rules, not data)
D-016 (w0), D-023 (w1), D-024 (w2): merge_eligible=false came only from the rerun-proof rule having no leg for first-run/unchanged shapes and `table_privileges` being unreadable to the SP. Independent verifier never ran. `pkg_plans` structural `trigger_extra` is `ALL_TRIGGERS` visibility for the RO principal. Every accepted unit has a live dbx-recon PASS.

## Qualitative SI comparison
Same deliverables an SI would hand over (side-by-side outputs, recon reports, decision ledger, PRs), produced by the factory with every guard block surfaced as a finding, every scope/tolerance change as a ledger row, and no human touching legacy systems.
