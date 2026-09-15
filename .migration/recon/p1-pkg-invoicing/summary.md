# p1-pkg-invoicing (U-23, wave 4 / batch w4-b) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter; every tier, tolerance and canonicalization rule is still the
harness's own. See `DEGRADED.md`, `result.json`, `recon.summary.md`,
`p1-pkg-invoicing.recon.json`.

Wave 3 ran this unit inside w3-b and halted on `undeclared_write_target`. D-009 declared the
writes and moved it here. Every declared runtime target was found on branch `mig-p1-w2` and
written by DML only — no DDL, no reload, no re-reconciliation of a table another unit owns.

Merge-evidence run: `--mode transactional --depth full --seed 0`, one live source read, the
command in the batch brief unchanged. A fixture run (`fixture/`) came first and is
development evidence only, never a merge verdict. Two full runs of the three-run cap used
(fixture + live); neither failed.

## Tiers

| tier | result | scope |
|---|---|---|
| 0–3, 5–7 | PASS | `billing.invoices`, `billing.invoice_lines` (the tables this package writes) |

Tiers 5–7 report source-side constraint, index and identity parity as **unverified**: the
JDBC adapter reads no catalog metadata. That is why `merge_eligible` is `false`.

## Write-path behaviour (fixture, controlled)

Split across two programs so no single program both reads Oracle and writes a target:

1. `databricks/migration/transport/pkg_invoicing_expected_fixture.py` calls Oracle
   `pkg_invoicing.fn_invoice_preview` and `sp_issue_invoice` on the fixture inside a
   transaction and rolls it back (`fixture/oracle_fixture_expected.json`).
2. `databricks/migration/lakebase/pkg_invoicing_behaviour_check.py` replays the same calls
   against Lakebase inside a transaction that is also rolled back, and diffs
   (`fixture/lakebase_behaviour_check.json`).

Five scenarios, all PASS: `credit_burn_down` (tenant 4), `burn_down_split` (tenant 9),
`tax_exempt` (tenant 3), `rollover` (tenant 1), `no_subscription`. Each compares the derived
period id and invoice id, the five preview rows, the invoice header, the lines through
`fn_invoice_lines`, credit-note balances before and after, the `rating_state` overage
hand-off, the audit rows `log_msg` writes in order, and a second `sp_issue_invoice` call.

The quirks that had to match exactly, and do:

- the burn-down decrements its running counter by each note's **original** `remaining_amount`
  (source :180-190), so tenant 4's two 30.00 notes end at 0.00 and 6.96, not 0.00 and 3.04;
- per-line rounding *and* total rounding: preview tax rows are `2.02125` unrounded, the
  stored lines are `2.02`, the header tax is `4.04`;
- the tax-exempt tenant gets zero tax rows, not absent ones;
- a tenant with no subscription previews NULL plan, NULL usage and NULL tax rather than
  raising (`WHEN NO_DATA_FOUND THEN NULL`, P1-D2);
- the audit trail is four rows in source order — two from `sp_finalize_rating`, one from the
  `compute_rating` call inside the preview, then `INVOICING issued invoice=… total=…` with
  Oracle's unformatted `TO_CHAR` (`total=0`, not `total=0.00`).

Neither program leaves a row behind: both transactions roll back.

## Idempotency, proven by rerun

`databricks/migration/lakebase/w4b_issue_invoice_digest.py` issues the four scenario invoices
against Lakebase, digests all seven declared write targets and rolls back. Two runs from the
same delivered state (`idempotency/run1.json`, `idempotency/run2.json`, distinct run ids)
produce identical row counts and content hashes.

Scope of that claim: **re-running the routine over the same input state is idempotent.** Two
calls back-to-back are a *different* input state the second time, because the first burns the
credit notes down — Oracle behaves identically, and that path is compared against Oracle in
the behaviour check (scenario `*_rerun` fields), not asserted here. Two columns are excluded
from the hashes and named in the digest files: `billing_audit_log.log_id`/`logged_at` (serial
and clock) and `billing.rating_state.updated_at` (`localtimestamp`); Oracle writes the same
fields from the same non-deterministic sources.

## Conversion decisions this evidence covers

- `compute_preview` is inlined into `fn_invoice_preview`, the way Oracle's own function
  reaches it; the five package globals are the columns the preview projects, so no session
  state survives (P1-D4).
- The overage the invoice is built from is `fn_usage_rating`'s result, not the finalize-time
  `billing.rating_state` value. Oracle's `compute_preview` assigns
  `g_overage := pkg_rating.g_overage_amount` unconditionally after its own `compute_rating`
  call, so the second computation always wins; preferring the stored value would bill a stale
  overage if usage lands between the two statements. `billing.rating_state` remains the
  explicit form of the hand-off (P1-D4), written by `sp_finalize_rating` in unit
  p1-pkg-rating. First revision of this unit read it back and preferred it; corrected after
  review, see "Evidence recomputed after the review fix" below.
- `sp_finalize_rating` is CALLed, never re-converted; its rating-table and audit writes are
  declared (D-009).
- The 0.0825 tax rate keeps its value as a named constant.
- `EXECUTE IMMEDIATE` line delete becomes a plain parameterised DELETE (constant SQL text in
  the source, identical rows removed).
- `INSERT` + `DUP_VAL_ON_INDEX` stays insert-then-catch on `unique_violation` rather than
  `ON CONFLICT`: the source's UPDATE branch sets `status_cd` only and must not reset the
  amounts.
- `ROWNUM <= 1` over `ORDER BY starts_on DESC` becomes `ORDER BY … LIMIT 1`.
- Oracle `LEAST`/`GREATEST` return NULL on a NULL argument and Postgres ignores NULLs: the
  source's own `NVL(v_charge_cap, g_credit)` is kept verbatim, and the burn-down's `GREATEST`
  is written so a NULL credit still propagates (the source would then fail ORA-01400 on a
  NOT NULL column; the conversion fails the same way instead of silently writing 0).
- Money is `numeric`, never float. Status code 20 stays a magic number.
- `CAST(p_period_end AS TIMESTAMP)` and every other timestamp is zoneless (D-010).
- `log_msg`'s audit write is kept, including the message text, which reproduces Oracle's
  unformatted `TO_CHAR(number)` (`0`, `46.08`, `.5`).

## Evidence recomputed after the review fix

The merge-evidence run below was taken against the first revision of
`w4b_pkg_invoicing.sql`, which preferred the stored `billing.rating_state` overage over the
recomputation. That precedence was corrected afterwards. The two values are equal in every
fixture and recon scenario — one transaction, no concurrent usage between the finalize and
the preview — so no compared value moves, and re-running the live read would have breached
the one-live-read-per-unit cap. What was re-run on the corrected code: the SQL was reapplied
to `mig-p1-w2`, all five fixture scenarios were re-compared against the Oracle expectations
(`fixture/lakebase_behaviour_check.json`, five PASS), and both target-state digests were
retaken (`idempotency/run1.json`, `idempotency/run2.json`, identical). The live tier results
themselves are carried forward, not recomputed; that is listed as an unverified path.

## NOT DATA-PROVEN / unverified paths

- **The live merge-evidence run predates the review fix** described above; only the fixture
  comparison and the target digests were recomputed on the shipped code.
- **Tiers 5–7 source-side metadata** are unverified on the JDBC route — structural, not a
  failure of this unit, and the reason `merge_eligible` is false.
- **Live Oracle invocation of the package is not exercised.** The read-only user has no
  EXECUTE on `pkg_invoicing` (same finding as U-20/U-21/U-22), and granting it would be DDL
  on a read-only source. Behavioural equality of the package *call* is proven on the fixture
  only. This unit takes no `--ops` tier-4 diff: the brief's gate command defines none, and a
  second live read would breach the one-read-per-unit cap.
- **No row this unit writes is left on the wave branch.** `billing.invoices` and
  `billing.invoice_lines` are the tables recon compares against Oracle, so every behaviour
  run and every digest run is rolled back. What a committed production run would leave is
  therefore not reconciled here.
- `log_msg` inherits declared divergence P1-D1a: Oracle's `PRAGMA AUTONOMOUS_TRANSACTION` has
  no Lakebase equivalent, so a caller that rolls back keeps its audit row on Oracle and loses
  it here. The call and its message text are preserved; audit-row parity is not claimed.
- `billing.rating_state` has no Oracle counterpart — it is the explicit form of package
  state, so there is nothing to reconcile it against. Its contents are checked against the
  Oracle package variable in the fixture behaviour check only.
