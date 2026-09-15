# p1-pkg-plans (U-21, wave 2 / batch w2-a) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter; every tier, tolerance and canonicalization rule is still the
harness's own. See `DEGRADED.md`, `result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, one live source read, with
`--ops databricks/migration/recon/ops/p1_pkg_plans_ops.json`. A fixture run (`fixture/`)
came first and is development evidence only, never a merge verdict. Two full runs used of
the three-run cap (a third attempt aborted before any comparison with ORA-00942 because the
op SQL was not schema-qualified for the read-only user; fixed and rerun on the fixture).

## Tier-4 behavioural parity (the unit's own gate)

| tier | result | scope |
|---|---|---|
| 0–3, 5–7 | PASS | `billing.subscriptions`, the table this package writes (same 69 rows as U-03) |
| 4 app_level_parity | PASS, 2 ops | entrypoint diff below |

Ops (source SQL is Oracle dialect with quoted lower-case aliases; target SQL calls the
converted objects, so the function itself is exercised, not a copy of its body):

| op | compares |
|---|---|
| `fn_entitlement_projection_all_tenants_2026_06_01` | Oracle `fn_entitlement`'s projection for every tenant at 2026-06-01 vs `billing.fn_plan_entitlements` over the same tenants |
| `entitlement_keeps_orphan_plan_ids` | subscriptions whose `plan_id` has no plan row, both sides (D8-01 orphans survive the LEFT JOIN) |

The Oracle side inlines the package body's own query because the read-only user has no
EXECUTE on the package (ORA-41900, same finding as U-20) and granting it would be DDL on a
read-only source. The tie-break `ORDER BY starts_on DESC, id` is added on the source side of
the op only, to make the op deterministic; neither platform's own code orders past
`starts_on`, and no tenant in the estate has two covering subscriptions with equal
`starts_on`.

## Rows the package writes, and the write-path behaviour

`behaviour_check.json` is the controlled fixture run the batch brief asks for, split across
two programs so that no single program both reads Oracle and writes a target:

1. `databricks/migration/transport/pkg_plans_expected_fixture.py` runs Oracle
   `pkg_plans.sp_change_plan` on the fixture inside a transaction and rolls it back,
   recording the subscription rows before and after, the entitlement projection before and
   after, and an un-cancel probe (`expected_fixture.json`).
2. `databricks/migration/lakebase/pkg_plans_behaviour_check.py` replays the same call
   against Lakebase inside a transaction that is also rolled back, and diffs.

All five checks match (`verdict: PASS`):

- `starting_rows_match_source` — the target rows for the tenant equal the fixture's.
- `fn_plan_entitlements_before_change` / `..._after_change` — the seven-column projection
  matches, including the `GREATEST(starts_on, p_on)` effective date and the `DECODE` →
  `CASE` tier/status strings.
- `sp_assign_plan_written_rows` — the close-out row (`ends_on = p_effective_on - 1 day`,
  status preserved) and the new status-10 row match, **including the generated id**:
  `billing.f_md5_uuid` produces the same `4b9647f7-...` as Oracle's
  `pkg_ow_util.f_md5_uuid` over the same concatenated input.
- `trg_sub_no_uncancel` — updating a cancelled row to status 10 raises nothing on either
  platform and leaves the row at 30.

Neither program leaves a row behind: both transactions roll back, so the wave branch keeps
exactly the state the loader put there, and no `billing_audit_log` row from the procedure's
audit call persists.

## Conversion decisions this evidence covers

- `(+)` outer joins become ANSI `LEFT JOIN` with subscriptions as the preserved side, so an
  orphan `plan_id` still returns a row with NULL plan fields (D8-01).
- `EXECUTE IMMEDIATE` around a static INSERT becomes a plain INSERT with the same column
  list, bind order and literal status 10.
- The cursor keeps `FOR UPDATE` and the row-by-row `WHERE CURRENT OF` close-out, so the
  locking semantics are the source's rather than a faster set-based rewrite's.
- `WHEN OTHERS THEN NULL` around the cache lookup stays swallowed (P1-D2): a failed lookup
  yields NULL, never an error.
- Package globals become explicit output columns `last_tenant_id` / `last_plan_code`
  (P1-D4): what Oracle stashed in package state, the caller now receives in band. Their
  values are recorded in `behaviour_check.json` under `package_state_returned`.
- `p_effective_on - 1` on an Oracle DATE is minus one **day**, so it is `INTERVAL '1 day'`.

## NOT DATA-PROVEN / unverified paths

- **Cache staleness is not reproduced.** Oracle's `g_last_plan_code` survives the call, so a
  later caller in the same session can read an earlier caller's plan code, and nothing
  invalidates it. Reproducing that needs a state row, and a state table is outside this
  batch's declared write targets. Recorded as a coverage gap for the owner rather than
  written to an undeclared object. Two consequences of the same gap, both unverified:
  a call that returns no entitlement row returns no state values either, where Oracle
  still updates `g_last_tenant_id`; and a failed cache lookup yields NULL here, where
  Oracle's swallowed exception leaves the *previous* `g_last_plan_code` in place. The
  cross-call read is the part with consumer impact, and it needs the state row.
- **`fn_list_plans` is not converted.** The third package entrypoint is a plans-only
  projection and is not in this batch's declared write targets. Coverage gap, not a failure.
- `log_msg` inherits declared divergence P1-D1a: Oracle's `PRAGMA AUTONOMOUS_TRANSACTION`
  has no in-database equivalent here, so a caller that rolls back keeps its audit row on
  Oracle and loses it on Lakebase. `sp_assign_plan` keeps the audit call and the source's
  exact message text; parity for it is not claimed by this unit.
- `SUBSCRIPTIONS_HIST`: Oracle's `TRG_SUBSCRIPTIONS_HIST` writes a history row for every
  update this procedure makes. That table belongs to a later unit and has no target rows
  yet.
- Tiers 5–7 source-side metadata are unverified on the JDBC route, which is why
  `merge_eligible` is `false` — structural, not a failure of this unit.
