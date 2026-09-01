# Recon summary — `mv_agent_commission_summary` (ns `cdw`, run_mode fixture, DEGRADED snapshot (federation unavailable), tolerances v1)

**Verdict: PASS**

| check | expected | actual | result |
|---|---|---|---|
| rowcount | `3` | `3` | pass |
| duplicate_keys | `0` | `0` | pass |
| null_count | `0` | `0` | pass |
| row_diff | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | `{'missing': 0, 'unexpected': 0, 'changed': 0}` | pass |
| money_sum_cents:total_commission | `7000` | `7000` | pass |

Idempotency rerun: pass — rerun rc=0; rows before=3 after=3; row set identical=True (loaded_at excluded)
Source of truth: legacy baseline MV_AGENT_COMMISSION_SUMMARY.csv (manifest-pinned) vs ow_tp.gold.mv_agent_commission_summary_cdw
