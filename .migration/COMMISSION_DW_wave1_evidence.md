# Wave 1 (pilot, width 3) — close brief

- **Run branch:** `tp-run/databricks-20260901T205306Z`
- **Merged PRs:** #1425 (`dim_product`), #1426 (`dim_agent`), #1427 (`dim_period`)
- **Merge date:** 2026-09-01

## What landed

Three silver targets now implement the dimension loads:

- `ow_tp.silver.dim_agent_cdw`
- `ow_tp.silver.dim_product_cdw`
- `ow_tp.silver.dim_period_cdw`

Each run drops and rebuilds its target from the snapshot baseline, then MERGEs
the corresponding `COMMISSION_PAY` feed. Surrogate keys are preserved
verbatim from the baseline.

## Evidence

| Unit | Child recon | Parent independent recon | Baseline manifest SHA-256 |
|---|---|---|---|
| `dim_agent` | PASS; rowcount 4/4; row_diff 0; key_preservation 4/4; dup 0; null 0; idempotency performed+pass | PASS; rowcount 4/4; row_diff 0; key_preservation 4/4; dup 0; null 0; idempotency performed+pass | `ecdebbadb7acd3a2ccf1a6fb7f50078cb1f8300babe2ad6f7b941e44de628f8f` |
| `dim_product` | PASS; rowcount 3/3; row_diff 0; key_preservation 3/3; dup 0; null 0; idempotency performed+pass | PASS; rowcount 3/3; row_diff 0; key_preservation 3/3; dup 0; null 0; idempotency performed+pass | `dc2941c1724b27f37a5dec2f2c2bf8a66397ee488b61a8455687734cf15a216d` |
| `dim_period` | PASS; rowcount 1/1; row_diff 0; key_preservation 1/1; dup 0; null 0; idempotency performed+pass | PASS; rowcount 1/1; row_diff 0; key_preservation 1/1; dup 0; null 0; idempotency performed+pass | `d55687af0968d1763aa1cc2dd0064e8b21972f24ec48410954efe8a5e79168b0` |

The parent window ran in order `dim_agent`, `dim_product`, `dim_period` against
the existing serverless warehouse. Reports and validation output are recorded
under `/home/ubuntu/w1-recon/`; each report was validated successfully.

## Decisions

DEC-017 establishes drop + rebuild-from-baseline + feed MERGE per run for the
wave-1 dimensions. Init-once versus recurring-run separation is deferred to the
U4 loader Workflow, which owns wave-2 ordering.

## Review findings and wave-2 implications

Review flagged drop/recreate on U1/U3; it is retained under DEC-017. The
declared-volume assertion on U2 is retained as a packet rule. For wave 2, the
U4 Workflow must sequence dimension loads before fact loading and make
init-versus-recurring mode explicit.

## SKILL FEEDBACK harvested (7 items)

1. Allocate new surrogate keys only over feed rows absent from the target; the
   target may be referenced in the MERGE `USING` subquery. Fixed in **B**.
2. Unit SQL runners split on semicolons, so string literals must not contain
   `;`. Fixed in **B**.
3. Guard `YYYY-MM` derivation with the full month-range regular expression in
   addition to NULL checks. Fixed in **B**.
4. Declare `loaded_at TIMESTAMP NOT NULL` as an insert-time audit column and
   exclude it from recon. Fixed in **B/D**.
5. Dimension runs are full snapshot operations; init-once versus recurring-run
   ownership belongs to the U4 Workflow. Fixed in **B/E/F**.
6. Recon accepts `--baseline` as an alias for `--baseline-dir`, and each gate
   budgets two full loads when `--rerun` is used. Fixed in **A/B/C**.
7. Non-live reports explicitly name both the DEGRADED legacy comparison and the
   parent independent recon gate. Fixed in **A**.

## Unproven paths

Live legacy comparison remains DEGRADED because federation is unreachable.
The D4 query-history gap and cross-table atomicity remain unproven and are
owned by later work in wave 2.

## Cost

Session ACU: U1 4.99 / U2 4.58 / U3 3.52. Warehouse time: U1 ≤15 wh-min,
U2 ≈2 wh-min, U3 ≈8 wh-min; parent recon window ≈5 wh-min.

This brief uses snapshot-baseline and recon-tooling terminology throughout.
