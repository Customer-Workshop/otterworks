# Recon summary — `dim_period` (ns `cdw`, mode fixture, DEGRADED snapshot, tolerances v1)

**Verdict: PASS**

| check | expected | actual | result |
|---|---|---|---|
| rowcount | `1` | `1` | pass |
| duplicate_keys | `0` | `0` | pass |
| null_count | `0` | `0` | pass |
| row_diff | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | pass |
| key_preservation | `1` | `1` | pass |

Idempotency rerun: pass — rerun rc=0; rows before=1 after=1; row set identical=True (loaded_at excluded)
Source of truth: legacy baseline DIM_PERIOD.csv (manifest-pinned) vs ow_tp.silver.dim_period_cdw
