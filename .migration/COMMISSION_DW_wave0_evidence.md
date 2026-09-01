# Wave 0 evidence — COMMISSION_DW scaffolding (2026-09-01, parent-owned, serial)

| Gate (plan §W0) | Result | Evidence |
|---|---|---|
| W0-1 catalog `ow_tp`, schemas `bronze/silver/gold/ops`, volume `ow_tp.bronze.landing` | created (`IF NOT EXISTS`, nothing unprefixed touched) | `scripts/tp_dbx/cdw_baseline.py provision` |
| W0-1 `make tp-preflight-databricks` | 11 probes, 0 denied (the 3 catalog-dependent probes that failed at intake now pass) | preflight run after provision |
| W0-2 DEC-011 legacy load once (shipped procedures only, via `scripts/tp-run-deterministic.sh make insurance-test NS=cdw`) | `FACT_COMMISSION` 0→3, `COMMISSION_LEDGER` 0→3, MV 0→3; no authored source DDL/DML | read-only counts before/after |
| W0-3 baseline extract, 9 objects, ordered UTF-8 CSV + `manifest.json` (sha256, rows, order key, extracted_at) | AGENTS 4, PRODUCTS 3, POLICIES 5, COMMISSION_LEDGER 3, DIM_AGENT 4, DIM_PRODUCT 3, DIM_PERIOD 1, FACT_COMMISSION 3, MV 3 | `etl/legacy-extra/commission_dw/cdw/` (committed, hash-pinned) |
| W0-3 local transport `FIXTURE_SOURCE=etl/legacy-extra/commission_dw/cdw make tp-fixture-land/verify NS=cdw` | 10/10 files byte-identical | local fixture layer |
| W0-3 Files API landing `/Volumes/ow_tp/bronze/landing/cdw/{feed,baseline}/` + re-read | checksum mismatches: 0 | `cdw_baseline.py upload` |
| W0-3 bronze feed tables `agents_cdw` 4, `products_cdw` 3, `policies_cdw` 5, `commission_ledger_cdw` 3 | rows == manifest | `cdw_baseline.py load-feed` (same statement text U4's T0 reuses) |
| W0-4 dialect skill stub | `.agents/skills/oracle-plsql/SKILL.md` v0 | — |
| W0-5 recon harness | `scripts/tp_dbx/cdw_recon.py`; report shape passes `make tp-validate-recon`; dry run reaches the target read (table absent as expected pre-wave-1) | — |
| W0-6 write-target ledger seeded; `make tp-smoke` | passed | `05_progress.md` |

Baseline is tiny (3 fact rows, 1 period) but non-vacuous: three agents split one AUTO policy for 2025-06, cents total 7000 (38.00 + 19.20 + 12.80). Full row-level diff is the recon method for every unit.
Cost line: parent session only (no children); serverless warehouse time ≈2 min.
