# Wave and dependency plan — OW_BILLING → Databricks

Framework: Workflows + notebook tasks with Delta `MERGE` (STOP B). Run branch
`tp-run/databricks-20260828T221250Z`; `ns=demo`. Every unit is one job `ow_tp_<unit>`, accepts `ns`,
and contributes exactly one file `infrastructure/terraform-databricks/jobs_<unit>.tf`. Children never
run `terraform apply`/`destroy`, never run DDL against a shared table, and never write outside their
own unit. A unit counts as done only when it is **merged into the run branch** with a green
`*.recon.json`.

Waves are dependency-ordered, not size-ordered. No wave N+1 starts before wave N is green and merged,
and the shared Terraform plan must be clean at every wave boundary.

## Wave 0 — serial, parent-owned

`dict` (`09_semantic_dictionary.md`), shared Terraform and workspace state, catalog/schema/volume
bootstrap, the golden baselines recon compares against, and the contracts that settle the ambiguity
classes (quarantine reason codes, trigger/batch granularity, surrogate-key exclusions).

Wave 0 is serial by construction: it is the only wave whose output every other unit reads, and 25
dictionary entries decided in parallel by different children is exactly the failure this run exists
to avoid.

## Wave 1 — bronze ingest (fan-out candidate)

`bronze_core`, `bronze_wide`, `bronze_hist`, `bronze_custbill`.

Write targets are disjoint (four different bronze table sets; `bronze_custbill` also owns
`/Volumes/ow_tp/bronze/landing/<ns>/custbill/`), so these four can run concurrently without a
collision. They share only the federated JDBC connection and the one `Serverless Starter Warehouse`
(`565cd2fd713738c4`, auto-stop 10 min — the first query of each run pays a cold start, which is not
a capability failure).

## Wave 2 — pilot: `silver_rating`, then `silver_invoicing`

Two units, as fixed at intake — the critical path and the two slowest-converting units in the estate.
Deliberately narrow: this is where the dictionary gets its first contact with real data and where the
true quarantine rate on `CUSTOMER_MASTER`'s `VARCHAR2(9)` dates becomes known for the first time.

Ordering inside the wave: rating lands first. Invoicing recomputes rating inline rather than reading
`RATING_RESULTS` (D-10), so it consumes rating's converted logic as a shared helper, not its output
table. Running them concurrently would fork that helper.

Pilot exit criteria, all four required before wave 3 is briefed:
1. Both units green and merged, each with a rerun proving idempotency (`MERGE` on the D-14 keys plus `ns`).
2. Observed quarantine rate recorded per source table, and under 5%.
3. Money exact to the cent against source over the surviving population, with quarantine counts
   printed beside every money figure.
4. Dictionary feedback harvested: every entry the pilot corrected or added is written back to
   `09_semantic_dictionary.md` **before** any wave-3 child starts. A pilot that produces no
   dictionary changes has almost certainly not looked hard enough.

## Wave 3 — `silver_plans`

Held out of wave 2 because it writes `SUBSCRIPTIONS`, and out of wave 4 because dunning writes the
same table. Serial with respect to both.

## Wave 4 — `silver_dunning`

The estate's one genuine **write-target collision**: `sp_suspend_overdue` mutates `TENANTS` and
`SUBSCRIPTIONS`, which `bronze_core` loads and `silver_plans` writes. It runs alone. If a child in
any wave discovers a second write-target collision, fan-out halts for that wave rather than being
resolved locally.

## Wave 5 — `gold_finance` + recon rollup

The finance report is the only consumer we can actually see, so it is the closest thing to a
business-recognisable acceptance test. It is also a PII egress point: gold must carry no unmasked
`CUSTOMER_MASTER` column, and a PR that copies cleartext PII into gold or an export is rejected.

## Fan-out shape (STOP C — approved)

Wave 1 runs at **width 4**: all four bronze units concurrently (customer STOP C decision,
2026-08-28). Waves 2–4 stay serial; that is a correctness constraint, not a width choice.

| Wave | Units | Concurrency | Constraint |
| --- | --- | --- | --- |
| 0 | 1 (parent) | serial | everything depends on it |
| 1 | 4 | **4 (approved)** | disjoint write targets |
| 2 | 2 | serial (rating → invoicing) | pilot, fixed at intake |
| 3 | 1 | serial | shares `SUBSCRIPTIONS` with wave 4 |
| 4 | 1 | serial | write-target collision |
| 5 | 2 | up to 2 | gold + rollup |

Wave 1 is the only wave where fan-out width changes the schedule. Waves 2–4 are serial for
correctness reasons that width cannot buy back, which means the estate's critical path is
`dict → bronze → rating → invoicing → plans → dunning → gold` regardless of how wide wave 1 runs.

Halt conditions, in every wave: a write-target collision, a systematic failure (the same dictionary
entry wrong in more than one unit), or a quarantine rate above 5% of source rows. Each wave is
reconciled independently; a green rollup does not substitute for a per-unit `*.recon.json`.

What width 4 costs, recorded so it is not a surprise later: four children land at once against a
dictionary that has not yet met real data, so a wrong dictionary entry is discovered four times
in parallel instead of once. The mitigation is wave 0, not narrower fan-out — the dictionary, the
per-unit contracts, and the capability manifest are all landed and approved before any of the four
start, and a systematic failure halts the whole wave rather than being patched per unit.

## Carried centrally — cross-unit target-architecture items

- **Multi-table publication atomicity (opened by wave 2, `silver_invoicing`).** `sp_issue_invoice`
  issues a header, its lines, and the credit burn-down inside one Oracle transaction. The target
  writes each Delta table in its own commit (plus the scoped line-rebuild delete), so a failure
  between commits leaves a state the source can never produce: a visible invoice header with no
  lines, or lines without their credit applications. Every unit's rerun converges to the correct end
  state, so this is a *visibility* window, not permanent corruption — but it is a real divergence and
  it applies to every silver and gold unit, so no single unit invents its own protocol for it.
  Resolution options (batch marker with readers switched atomically vs. explicit run state that
  consumers filter on) are a pre-cutover design decision, and gold's finance report is the consumer
  that makes it matter. Decided before cutover, not per unit.

- **Retraction of publications the current drivers no longer produce (opened by wave 2,
  `silver_invoicing`).** `sp_issue_invoice` issues and re-issues but never unpublishes, so an invoice
  of an earlier period stands after its tenant loses its subscription, is deleted from bronze, or
  would now fail the preview. The port keeps that behaviour — every reconciliation is scoped to the
  invoices the run issues — so this is *declared parity, not a target divergence*, and it is recorded
  separately from the atomicity item above for that reason. `PARITY-NO-RETRACTION` measures the
  surviving population (invoices, tenants, lines, applications, money) on every run. If the business
  ever wants retraction, the answer is a period-scoped or full-refresh reconciliation decided
  estate-wide; no unit invents one, because a unit-level sweep would delete rows the source still
  considers issued.

## Unresolved, and deliberately so

- **STOP E** — cutover authorization and how long the Oracle source stays readable through
  federation afterwards. With the consumer population declared unmapped and no audit observation
  window (D4-2), source retention is the only remaining hedge against a reader nobody knew about.
