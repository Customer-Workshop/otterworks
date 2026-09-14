# STOP A: target, tolerances, access (pipeline 1, OW_BILLING)

Repo `Cognition-Partner-Workshops/otterworks`, branch `tp-run/databricks-20260914T183234Z`, path `.migration/`.
Posted 2026-09-14 by the pipeline-1 orchestrator session. Blocking (the parent asked that no answer be
assumed; two rows below are safety posture, so the soft 60 s default is not applied).

## The decision
Approve the setup as written, or amend specific rows:

1. **Target profiles** as in `docs/migration/ow_billing_target_state.md` (Lakebase Postgres 17 branch-per-batch for the operational track; Delta in `ow_tp` for the analytical track; serverless only).
2. **Track split** as in `00_context.md`: 15 operational tables (10 package-written FACT + 5 reference PROPOSED), 4 analytical (`*_HIST`, `INVOICE_HEADER`, `INVOICE_LINE`), `FIXTURE_META` excluded. Live `DBA_SOURCE` write-set matches the intake exactly.
3. **Tolerances `tol-p1-v1`** (`03_recon_tolerances.md/.json`): 0 unexplained row diffs, money exact, floats 1e-6, timestamps to the second, planted anomalies compared as sets into quarantine, `cdc_lag_max_s = 60`, legacy query cap 2/unit, 4 total.
4. **Access posture** (`07_access_checklist.md`): Oracle RO, Databricks, Lakebase, recon harness all WORK. Open D10s in `04_dependency_register.md`:
   - D10-1 supplemental logging + `c##dbzuser` (customer DBA) — still `NO` / absent. Until closed: **rehearsal = SCN-pinned freeze-and-load into the Lakebase branch**, Debezium side prepared but not started.
   - D10-2 serverless egress: workspace is AWS **us-west-2**; Databricks publishes serverless outbound CIDRs at `https://www.databricks.com/networking/v1/ip-ranges.json` (not static; must be re-read): currently `18.246.106.0/24`, `3.42.138.0/25`, `44.234.192.32/28`, `52.27.216.188/32`. Docs: `docs.databricks.com/aws/en/security/network/serverless-network-security/serverless-firewall-config`. Parent applies to `sg-0eaf11f4434260e1` port 1521. Not needed for wave 0/1 (recon runs from Devin VMs).
   - D10-3 Debezium + Kafka as Docker on the existing t3.medium — **keep as proposed**. Alternative noted: Lakeflow Connect's managed Oracle CDC connector removes Kafka hosting but needs the same D10-1 and still requires a Lakebase apply step; not recommended for this run.
   - D10-4 Databricks identity is a human PAT (workspace admin), not a migration service principal. Doctor: `ready=false`. **Recommend option (a): accept for this demo run**; children run under the same PAT, wave launches at width 4 with the identity gate acknowledged. Option (b): parent provisions an SP scoped to `ow_tp`.
   - D10-5 recon harness has no Oracle adapter — wave-0 item, Devin-owned.
   - D10-6 the `ow_billing_ro` password was echoed once into a tool transcript during the first probe (fixed, no artifact holds it). **Recommend rotating it**; nothing blocks on this.
   - D10-7 plugin write-guard hook does not load on this platform (nonce probe echoed). **Recommend option (a): accept convention-only enforcement** (allowlist + doctor + independent recon) for this demo run.

## Recommendation
Approve as-is with the recommended options for D10-1 (freeze-and-load rehearsal), D10-3 (keep), D10-4 (a), D10-6 (rotate), D10-7 (a).

## Exact approving reply
`Approve STOP A as written: freeze-and-load rehearsal, Debezium on the existing host, PAT identity accepted, convention-only write guard, cdc_lag_max_s 60.`

To amend, reply with the row number/ID and the new value; nothing proceeds until a reply is recorded in `06_decisions.md`.

## After approval
`!dbx_migrate_pipeline` continues in this session: inventory (`2-inventory`) of the 19 tables, 5 packages, 7 triggers, 5 sequences, 2 jobs, and the D4 connection census; STOP B is the next message.

## Doctor summary (`09_capabilities.json`)
12 ok, 1 fail (`hook_platform_loaded`), 2 warn (`databricks_auth_kind`, `databricks_identity`), 2 skipped (no unit mapping yet). CLI v1.12.1, warehouse `565cd2fd713738c4`, harness selftest PASS, adapters `databricks`, `postgres`.
