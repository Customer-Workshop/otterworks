# Unit contract — `dim_agent` (COMMISSION_DW → `ow_tp.silver.dim_agent_cdw`)

Wave 1, batch B1-1. Target profiles: CORE + SQL + PIPELINE (`.migration/COMMISSION_DW_target_state.md`);
dialect rules: `.agents/skills/oracle-plsql/SKILL.md`; tolerances v1 (`.migration/03_recon_tolerances.md`).

## Source
| Item | Value |
|---|---|
| Legacy DDL | `services/industry-solutions/insurance/db/olap/01_star_schema.sql` — `dim_agent` |
| Legacy load | `02_etl_pkg.sql` L23–33: `MERGE INTO dim_agent ... ON (d.agent_id = s.agent_id)` from `COMMISSION_PAY.AGENTS` |
| Baseline snapshot | `etl/legacy-extra/commission_dw/cdw/DIM_AGENT.csv` — **declared source volume 4 rows**, sha256 `ecdebbad…628f8f` (manifest-pinned); landed at `/Volumes/ow_tp/bronze/landing/cdw/baseline/DIM_AGENT.csv` |
| Feed | `AGENTS.csv` (4 rows, sha256 `8e8c8cf0…e83443`) → `ow_tp.bronze.agents_cdw` (bronze table owned by wave 0 / U4 task T0; read-only here) |

## Target
| Column | Legacy | Target | Rule |
|---|---|---|---|
| `agent_key` | `NUMBER` identity | `BIGINT NOT NULL` | value carried over verbatim from the baseline (DEC-003); new agents get `max(agent_key) + row_number() OVER (ORDER BY agent_id)` |
| `agent_id` | `NUMBER NOT NULL UNIQUE` | `BIGINT NOT NULL` | MERGE key |
| `agent_code` / `full_name` / `status` | `VARCHAR2(16/120/12) NOT NULL` | `STRING NOT NULL` | byte-exact, no trim, no case folding |
| `loaded_at` | — | `TIMESTAMP NOT NULL` | `current_timestamp()` at insert; not touched on update; excluded from recon (DEC-004) |

Write target: `ow_tp.silver.dim_agent_cdw` only. No other table, schema, job or grant is created.

## Semantics preserved
- MERGE on `agent_id`; WHEN MATCHED updates exactly `agent_code`, `full_name`, `status`; WHEN NOT MATCHED inserts.
- Each run drops and recreates the target, re-initialises it from the baseline snapshot, then applies the MERGE
  from the feed. Re-running yields the identical row set (`loaded_at` excluded) — proven by the harness rerun.

## Ambiguity classes (resolved up front)
| Class | Policy |
|---|---|
| Encoding | UTF-8 in, UTF-8 out; strings compared byte-for-byte after UTF-8 normalisation |
| Malformed records | `read_files(..., mode => 'FAILFAST')` with an explicit schema: an extra/missing delimited field, a non-numeric key or a type mismatch aborts the run — nothing is quarantined or skipped. An empty CSV field is NULL; a NULL in any NOT NULL column fails the run via `assert_true` before the MERGE (the legacy load raised ORA-01400 in the same case) |
| Empty input | empty baseline → empty table, run succeeds only if the feed is also empty of unknown agents (it then inserts from key 1); empty feed → MERGE is a no-op and the table equals the baseline. Both are legitimate outcomes, not errors |
| Batch granularity | full snapshot per run (no incremental / period filter — the legacy MERGE reads all of `AGENTS`); single writer |

## Coverage gaps / unverified paths
| Path | Owner | Severity | Closes at |
|---|---|---|---|
| live-legacy-comparison (DEGRADED mode — snapshot vs snapshot, federation unavailable) | parent | medium | wave-1 independent recon window |
| new-agent key allocation exercised only by a read-only probe (feed has no agents absent from the baseline) | U1 | low | first feed delivering a new agent; recon `key_preservation` guards existing keys |
| `loaded_at` audit column has no legacy counterpart on `DIM_AGENT` | U1 | info | accepted (DEC-004 exclusion) |

## Recon gate
```
python3 scripts/tp_dbx/cdw_recon.py --unit dim_agent --ns cdw --run-mode fixture \
  --baseline etl/legacy-extra/commission_dw/cdw --out dbx/commission_dw/dim_agent/recon/ \
  --rerun "python3 dbx/commission_dw/dim_agent/run.py --ns cdw"
make tp-validate-recon FILE=dbx/commission_dw/dim_agent/recon/dim_agent.recon.json
```
PASS ⇔ rowcount exact, duplicate_keys 0, null_count 0, row_diff 0/0/0 on `agent_key`, key_preservation 4/4, idempotency rerun performed and pass.
