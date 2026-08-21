# Commission Pay — business rule ledger

Every business rule encoded in `db/oltp/03_commission_pkg.sql` (the pre-extraction
package body, 350 LOC), with the inputs it reads, the outputs/side effects it produces,
the confidence that the rule is fully understood, and the case in `db/tests/run_tests.sql`
that covers it.

Line ranges refer to the **original** `03_commission_pkg.sql` at the baseline commit
(`git show HEAD~1:services/industry-solutions/insurance/db/oltp/03_commission_pkg.sql`).
After extraction the same rule numbers appear as `# R<n>` markers in
`commission-service/app/domain.py`, and every rule has a `@pytest.mark.rule("R<n>")`
test in `commission-service/tests/`.

Confidence legend: **high** = behavior is fully determined by the source and exercised by
a test; **medium** = behavior is fully determined by the source but has no Oracle test,
so the extraction is pinned only by the new parity suite; **low** = behavior depends on
Oracle semantics that must be re-derived (numeric formatting, rounding, collation).

## Rate management — `upsert_commission_rate` / `end_commission_rate`

| # | Rule | Lines | Inputs | Outputs / side effects | Confidence | Oracle test |
|---|---|---|---|---|---|---|
| R1 | Rate percentage must be non-NULL and in `(0, 50]`, else `ORA-20001` | 131-134 | `p_rate_pct` | raises `-20001`, message `Rate must be in (0, 50]: <pct or NULL>` | high | **T2** (only the `> 50` side; `<= 0` and `NULL` are **UNCOVERED**) |
| R2 | The product must exist, else `ORA-20004` | 99-106, 135 | `p_product_code`, `products` | raises `-20004` | medium | **NONE — uncovered** |
| R3 | A named agent must exist, else `ORA-20002` | 108-116, 136-138 | `p_agent_id`, `agents` | raises `-20002` | medium | **NONE — uncovered** |
| R4 | A named agent must be `ACTIVE` (not `SUSPENDED`/`TERMINATED`), else `ORA-20003` | 117-119 | `agents.status` | raises `-20003`, message `Agent <id> is <status>` | high | **T3** (`SUSPENDED`; `TERMINATED` uncovered) |
| R5 | Same-day correction: an *open* rate whose `effective_from` already equals the new one is amended in place (`rate_pct`, `created_by`), producing no new row | 140-149 | scope `(product_code, NVL(agent_id,-1))`, `effective_from` | updates existing row, returns its `rate_id` | high | **T1b** |
| R6 | Otherwise the open rate for the same scope that *starts earlier* is closed the day before the new one begins (`effective_to = p_effective_from - 1`); history is never deleted | 151-160 | same scope | updates prior row's `effective_to` | high | **T1** |
| R7 | A new open rate row is inserted (`effective_to` NULL) and its id returned | 161-166 | all inputs | inserts `commission_rates`, sets `o_rate_id` | high | **T1** |
| R8 | Audit: `RATE_UPSERT` with detail `rate_id=<id> pct=<pct> from=<YYYY-MM-DD>` | 168-170 | `p_actor` | inserts `rate_audit_log` | high | **T12** (count-only, `>= 4` rows for actor `tester`) |
| R9 | The whole procedure is atomic: `COMMIT` on success, `ROLLBACK` + re-raise on any error | 171-175 | — | transaction boundary | medium | **NONE — uncovered** |
| R10 | `end_commission_rate` closes the open rate for a scope at `p_effective_to` | 185-189 | scope, `p_effective_to` | updates `commission_rates.effective_to` | medium | **NONE — the whole procedure is uncovered** |
| R11 | Closing a scope with no open rate raises `ORA-20007` (`No open rate for <product>/<agent or default>`) | 190-193 | scope | raises `-20007` | medium | **NONE — uncovered** |
| R12 | Audit: `RATE_END` with detail `to=<YYYY-MM-DD>` | 194-195 | `p_actor` | inserts `rate_audit_log` | medium | **NONE — uncovered** |

## Split allocation — `set_commission_splits`

| # | Rule | Lines | Inputs | Outputs / side effects | Confidence | Oracle test |
|---|---|---|---|---|---|---|
| R13 | The policy must exist, else `ORA-20005` | 212-217 | `p_policy_id`, `policies` | raises `-20005` | medium | **NONE — uncovered** |
| R14 | At least one allocation is required (NULL or empty collection → `ORA-20006`) | 219-221 | `p_splits` | raises `-20006` | high | **T11** |
| R15 | No duplicate agent in the allocation (`COUNT(DISTINCT agent_id) <> COUNT`) → `ORA-20006` | 223-226 | `p_splits` | raises `-20006` | high | **T5** |
| R16 | Each percentage must be non-NULL and in `(0, 100]`, checked in collection order, else `ORA-20006` | 228-234 | `p_splits(i).split_pct` | raises `-20006` | medium | **NONE — uncovered** (T4 trips the *sum* rule, not the per-item bound) |
| R17 | Every agent in the allocation must exist and be `ACTIVE` (per-item, checked after that item's percentage) → `-20002` / `-20003` | 235 | `agents.status` | raises `-20002`/`-20003` | medium | **NONE — uncovered** |
| R18 | Percentages must total exactly `100` (exact decimal comparison, not a tolerance) → `ORA-20006` | 239-242 | `p_splits` | raises `-20006`, message `Split percentages must total 100.00, got <total>` | high | **T4** (over 100; under 100 uncovered) |
| R19 | Replacement is wholesale: all existing rows for the policy are deleted, then the new allocation is inserted **in collection order** | 244-248 | `p_splits` | rewrites `commission_splits` | high | **T6** (row count and sum only; insertion order not asserted) |
| R20 | Audit: `SPLIT_SET` with detail `<n> agents`, `policy_id` set, `product_code`/`agent_id` NULL | 250-251 | `p_actor` | inserts `rate_audit_log` | high | **T12** (count-only) |
| R21 | Atomic: `COMMIT` on success, `ROLLBACK` + re-raise on any error (a rejected allocation leaves the previous one intact) | 252-256 | — | transaction boundary | medium | **NONE — uncovered** |

## Rate resolution — `resolve_rate`

| # | Rule | Lines | Inputs | Outputs / side effects | Confidence | Oracle test |
|---|---|---|---|---|---|---|
| R22 | Candidate rates are those for the product whose window contains `p_as_of` (`effective_from <= as_of AND (effective_to IS NULL OR effective_to >= as_of)`) and whose `agent_id` is the requested agent **or** NULL (the product default) | 267-275 | `commission_rates` | returns `rate_id` | high | **T7 / T7b** |
| R23 | Precedence is `ORDER BY agent_id NULLS LAST, effective_from DESC` → an agent-specific rate always wins over the default; within a scope the latest-starting rate wins | 274 | — | returns `rate_id` | high | **T7** (agent override); latest-starting tie-break **uncovered** |
| R24 | No rate in force raises `ORA-20007` | 277-282 | — | raises `-20007` | medium | **NONE — uncovered** |

## Commission calculation — `calculate_policy_commission`

| # | Rule | Lines | Inputs | Outputs / side effects | Confidence | Oracle test |
|---|---|---|---|---|---|---|
| R25 | The policy must exist, else `ORA-20005` | 297-302 | `p_policy_id` | raises `-20005` | medium | **NONE — uncovered** |
| R26 | The policy must be `IN_FORCE`; `LAPSED`/`CANCELLED` raise `ORA-20008` | 303-306 | `policies.status` | raises `-20008` | high | **T10** (`LAPSED`; `CANCELLED` uncovered) |
| R27 | The rate is resolved as of the **last day of the period month** (`LAST_DAY(TO_DATE(p_period_month,'YYYY-MM'))`), not the first day or today | 308, 317 | `p_period_month` | drives R22/R23 | high | **T8** (indirectly — the seeded rates make both dates resolve alike, so the *choice of day* is itself uncovered) |
| R28 | Re-running a policy/period deletes that period's ledger rows first, so recalculation replaces rather than duplicates | 310-311 | `p_policy_id`, `p_period_month` | deletes `commission_ledger` rows | high | **T9** |
| R29 | Splits are processed in `split_pct DESC, agent_id` order; each agent's row is computed independently in that order | 313-316 | `commission_splits` | insertion order of ledger rows | medium | **NONE — order is not asserted** |
| R30 | Per-agent amount = `ROUND(annual_premium / 12 * rate_pct / 100 * split_pct / 100, 2)` — Oracle `NUMBER` (decimal) arithmetic, rounded half-away-from-zero to cents **per agent row** | 320-322 | premium, rate, split | `commission_ledger.commission_amt` | high | **T8a / T8b / T8c** |
| R31 | No remainder redistribution: rows are rounded independently, so the sum of the agents' commissions may differ from the rounded policy-level commission by a cent. The residue is deliberately *not* allocated to anyone | 320-322 (absence of any adjustment) | — | ledger totals | medium | **NONE — uncovered** (the seeded T8 case divides evenly) |
| R32 | Each ledger row records the resolved `rate_id`, the agent's `split_pct` and the policy's full `annual_premium` as `base_premium` (not the monthly base) | 324-329 | — | inserts `commission_ledger` | high | **T8** (only `commission_amt` is asserted) |
| R33 | A policy with no split allocation raises `ORA-20006` (`Policy <id> has no split allocation`) — checked *after* the delete, so the rollback restores the previously calculated rows | 333-336 | `commission_splits` | raises `-20006` | medium | **NONE — uncovered** (T11 covers the empty-input guard in `set_commission_splits`, not this path) |
| R34 | Audit: `COMMISSION_CALC` with detail `<period> rows=<n>`, `product_code` set, `agent_id` NULL | 338-339 | `p_actor` | inserts `rate_audit_log` | high | **T12** (count-only) |
| R35 | Atomic: `COMMIT` on success, `ROLLBACK` + re-raise on any error | 340-344 | — | transaction boundary | medium | **NONE — uncovered** |

## Cross-cutting Oracle semantics the extraction must preserve

| # | Rule | Source | Confidence | Oracle test |
|---|---|---|---|---|
| R36 | Scope identity for a rate is `(product_code, NVL(agent_id, -1))`: the product default and an agent override are different scopes, and at most one row per scope may be open (`ux_rates_open` unique index in `01_tables.sql`) | 146, 157, 188 | high | **T1 / T1b** |
| R37 | All money and percentage arithmetic is Oracle `NUMBER` (exact decimal, 38 significant digits) — never binary floating point | schema types | low (must be re-derived outside Oracle) | implied by **T8a-c** |
| R38 | Numbers interpolated into audit details and error messages use Oracle's default `TO_CHAR`: trailing zeros dropped (`8.50` → `8.5`), no leading zero below one (`0.5` → `.5`) | 169, 241 | low (must be re-derived outside Oracle) | **NONE — uncovered** |

## Risk summary

Rules with **no Oracle test coverage at all** — these are the ones an extraction can
silently change: **R2, R3, R9, R10, R11, R12, R13, R16, R17, R21, R24, R25, R29, R31,
R33, R35, R38**, plus the uncovered halves of R1 (`<= 0` / NULL), R4 (`TERMINATED`),
R18 (under 100), R23 (latest-starting tie-break), R26 (`CANCELLED`) and R27 (which day
of the month the rate is resolved on).

`end_commission_rate` (R10-R12) is entirely untested by the Oracle suite, and the two
most consequential silent-drift risks are R31 (rounding remainder) and R38 (number
formatting inside audit details), because both would still produce green Oracle tests
while changing what the business sees.

Every rule above — covered or not — is pinned by the new suite: R1-R38 each carry a
`@pytest.mark.rule("R<n>")` test, `commission-service/tests/test_parity_oracle.py`
replays every `run_tests.sql` case against the fixture database
(`@pytest.mark.case("T<n>")`), and `test_rules.py` covers the rules the Oracle suite
never exercised. The three transaction rules (R9, R21, R35) can only be shown against a
real database, so they are marked on the parity cases that assert a rejected call left
no trace.
