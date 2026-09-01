# Recon summary — `dim_agent` (ns `cdw`, mode fixture, DEGRADED snapshot, tolerances v1)

**Verdict: PASS**

| check | expected | actual | result |
|---|---|---|---|
| rowcount | `4` | `4` | pass |
| duplicate_keys | `0` | `0` | pass |
| null_count | `0` | `0` | pass |
| row_diff | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | pass |
| key_preservation | `4` | `4` | pass |

Idempotency rerun: pass — rerun rc=0; rows before=4 after=4; row set identical=True (loaded_at excluded)
Source of truth: legacy baseline DIM_AGENT.csv (manifest-pinned) vs ow_tp.silver.dim_agent_cdw
