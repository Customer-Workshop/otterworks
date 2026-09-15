# p1-pkg-rating (U-22, wave 4 / batch w4-d) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter; every tier, tolerance and canonicalization rule is still the
harness's own. See `DEGRADED.md`, `result.json`, `recon.summary.md`.

Wave 3 ran this unit and reported BLOCKED: `billing.usage_events` did not exist yet. This is
the D-011 retry. The table was found on branch `mig-p1-w2` with 814 rows and was read only —
not created, reloaded or re-reconciled — and the Delta copy `ow_tp.silver.usage_events` was
never read.

Merge-evidence run: `--mode transactional --depth full --seed 0`, one live source read, with
`--ops databricks/migration/recon/ops/p1_pkg_rating_ops.json`. A fixture run (`fixture/`)
came first and is development evidence only, never a merge verdict. Two full runs used of the
three-run cap (one earlier attempt aborted before any comparison with ORA-00923, because the
op SQL aliased a column `prior`, an Oracle reserved word; renamed and rerun on the fixture).

## Tiers

| tier | result | scope |
|---|---|---|
| 0–3, 5–7 | PASS | `billing.rating_periods`, `billing.rating_results` (the tables this package writes) |
| 4 app_level_parity | PASS, 2 ops | entrypoint diff below |

Ops (source SQL is Oracle dialect with quoted lower-case aliases; target SQL calls the
converted functions, so the function itself is exercised, not a copy of its body):

| op | compares |
|---|---|
| `usage_summary_all_tenants_2026_02` | Oracle's `fn_usage_summary` projection per tenant and kind for 2026-02 vs `billing.fn_usage_summary` |
| `usage_rating_projection_all_tenants_2026_02` | the ten-column `compute_rating` projection for every tenant vs `billing.fn_usage_rating` |

The Oracle side inlines the package body's own logic because the read-only user has no
EXECUTE on the package (ORA-41900, same finding as U-20/U-21), and granting it would be DDL
on a read-only source. Money is compared as exact text (`FM99999999990.00`), unit counts as
exact text, so nothing is rounded into agreement.

## Write-path behaviour (fixture, controlled)

Split across two programs so no single program both reads Oracle and writes a target:

1. `databricks/migration/transport/pkg_rating_expected_fixture.py` runs Oracle
   `pkg_rating.fn_usage_rating`, `fn_usage_summary` and `sp_finalize_rating` on the fixture
   inside a transaction and rolls it back (`fixture/oracle_fixture_expected.json`).
2. `databricks/migration/lakebase/pkg_rating_behaviour_check.py` replays the same calls
   against Lakebase inside a transaction that is also rolled back, and diffs
   (`fixture/lakebase_behaviour_check.json`).

Four scenarios, all PASS: `rollover`, `suspended`, `tier_two`, `no_subscription`. Each one
checks the rating projection, the summary projection, the `rating_periods` and
`rating_results` rows `sp_finalize_rating` writes, the explicit `rating_state` overage
hand-off, the audit rows `log_msg` writes, and a second `sp_finalize_rating` call
(idempotency proven by rerun, not inferred: the rerun updates in place and adds no row).

Neither program leaves a row behind: both transactions roll back. The recon runs likewise
left nothing — `billing.billing_audit_log` holds 0 rows on the branch after both runs — so
the wave branch keeps exactly the state earlier waves put there.

## Conversion decisions this evidence covers

- Package globals become explicit: `fn_usage_rating` returns the nine `g_*` values in band,
  and `sp_finalize_rating` writes the `g_overage_amount` hand-off to `pkg_invoicing` into
  `billing.rating_state` with `updated_at` zoneless (P1-D4, D-010).
- `log_msg`'s audit write is kept, not dropped; declaring it is the fix (D-009).
- Per-row and per-tier rounding stays where the source puts it: usage is summed row by row
  over the cursor, the 101-unit tier break and the 1.5 second-tier multiplier are unchanged,
  and `ROUND(..., 2)` stays on the same expressions.
- Usage is date-filtered by `TO_CHAR(occurred_at, 'YYYYMMDD')` string comparison, as the
  source does, not by a timestamp range.
- `WHEN NO_DATA_FOUND THEN NULL` around the subscription and plan lookups stays swallowed
  (P1-D2): a tenant with no subscription rates to NULL quota and NULL overage, not an error.
- `ROWNUM <= 1` over `ORDER BY starts_on DESC` becomes `ORDER BY ... LIMIT 1`.
- Oracle `ADD_MONTHS(-3)` is month-end aware; the rollover window reproduces that rather
  than subtracting an interval.
- `LEAST`/`GREATEST` return NULL on a NULL argument in Oracle but ignore NULLs in Postgres,
  so the NULL-included-units path is reproduced explicitly.
- Date subtraction on an Oracle DATE yields days; the suspension proration converts the
  Postgres interval back to days before dividing.
- Money is `numeric`, never float, on both the target and the comparison.

## NOT DATA-PROVEN / unverified paths

- **`TRG_USAGE_EVENTS_CHECK` is not converted here.** The Oracle BEFORE INSERT trigger on
  `usage_events` rejects `units <= 0` and unknown `kind_cd`. `pkg_rating` only reads
  `usage_events`, and creating the trigger would be DDL on `billing.usage_events`, which
  unit `p1-usage-events-oltp` (w4-c) owns and which is outside this batch's declared write
  targets. Carried forward as a coverage gap for that owner, not routed around. No converted
  writer of `usage_events` exists yet, so nothing is unprotected today.
- **Live Oracle package invocation is not exercised.** The read-only user cannot EXECUTE the
  package, so the live op compares the package's logic inlined in Oracle SQL against the
  converted function. Behavioural equality of the package *call* is proven on the fixture
  only.
- `log_msg` inherits declared divergence P1-D1a: Oracle's `PRAGMA AUTONOMOUS_TRANSACTION`
  has no in-database equivalent, so a caller that rolls back keeps its audit row on Oracle
  and loses it on Lakebase. The call and its message text are preserved; parity for the
  audit row is not claimed by this unit.
- **`billing.rating_state` has no Oracle counterpart** — it is the explicit form of package
  state, so there is nothing to reconcile it against. Its contents are verified against the
  Oracle package variable in the fixture behaviour check only.
- Tiers 5–7 source-side metadata are unverified on the JDBC route, which is why
  `merge_eligible` is `false` — structural, not a failure of this unit.
