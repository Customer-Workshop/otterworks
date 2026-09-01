# Recon summary — `dim_product` (ns `cdw`, mode fixture, DEGRADED snapshot, tolerances v1)

**Verdict: PASS**

| check | expected | actual | result |
|---|---|---|---|
| rowcount | `3` | `3` | pass |
| duplicate_keys | `0` | `0` | pass |
| null_count | `0` | `0` | pass |
| row_diff | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | pass |
| key_preservation | `3` | `3` | pass |

Idempotency rerun: pass — rerun rc=0; rows before=3 after=3; row set identical=True (loaded_at excluded)
Source of truth: legacy baseline DIM_PRODUCT.csv (manifest-pinned) vs ow_tp.silver.dim_product_cdw
