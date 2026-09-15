# OtterWorks finance gold layer — metric definitions

Every metric below is defined once, in a Unity Catalog metric view over a Delta table in
`ow_tp.gold`. The definition travels with the metric, so a number in the dashboard, in a
notebook and in a SQL query is the same number computed the same way.

Money is `DECIMAL` end to end. Timestamps are `TIMESTAMP_NTZ`: the Oracle source keeps a
time part on `DATE` and its `TIMESTAMP` carries no zone, so anything else would either drop
a time or invent an offset.

Where the source data is dirty, the rule says what the metric does with it, and the row is
written to `ow_tp.gold.dq_exceptions` with the treatment recorded. Nothing is dropped
quietly.

## Objects

| Object | What it is |
|---|---|
| `ow_tp.gold.dim_plan`, `dim_tenant`, `fct_subscription`, `fct_credit_note`, `fct_rating_result` | Reference copies of the Lakebase billing tables the application writes |
| `ow_tp.gold.fct_subscription_mrr` | One row per subscription, priced at an as-of moment |
| `ow_tp.gold.fct_ar_open_invoice` | One row per open invoice, aged at an as-of date |
| `ow_tp.gold.fct_usage_period` | Usage rated against plan entitlement, tenant × month |
| `ow_tp.gold.fct_storage_cost_tenant` | Storage cost per tenant × month |
| `ow_tp.gold.dq_exceptions` | Every source row the layer could not take at face value |
| `ow_tp.gold.mv_arr_mrr`, `mv_ar_ageing`, `mv_overage`, `mv_storage_cost` | The metric views |

## ARR and MRR

**MRR** is the list monthly fee of the plan on each subscription that counts. **ARR** is
MRR × 12. Both are run-rate metrics: what the book bills per month if nothing changes, not
revenue earned in a period.

**Active — the definition, written down.** A subscription counts towards MRR when all three
hold at `as_of_ts`:

1. `status_cd = 10` (active). Suspended (20) and cancelled (30) never count, not even for
   the part of the month they were active.
2. Its period covers the moment: `starts_on <= as_of_ts AND (ends_on IS NULL OR ends_on >= as_of_ts)`.
   A null `ends_on` is open-ended, as the legacy `PKG_PLANS` lookup treats it.
3. It is the **latest-starting** of that tenant's overlapping subscriptions. This is how
   `PKG_RATING` and `PKG_PLANS` resolve a tenant to one subscription, and it is what stops
   a tenant with overlapping rows being counted twice.

Subscriptions that fail any test stay in the table with `mrr_amount = 0.00`, so churn and
suspensions are visible instead of missing.

**Mid-period plan change: not prorated.** The new subscription is latest-starting, so its
full monthly fee replaces the old one from the instant it starts. Run rate is a snapshot,
not an earned-revenue figure, so there is no part-month blend. If the two subscriptions
overlap, only the newer one is counted.

**Credit notes do not reduce ARR or MRR.** A credit note adjusts an invoice that was already
issued; run rate prices the forward-looking contract. Reducing ARR by a past credit would
mix two different questions. The credit notes are loaded (`ow_tp.gold.fct_credit_note`) and
available for a net-revenue metric, but they are deliberately outside ARR.

**Usage overage does not go into MRR either.** Overage is variable consumption revenue, and
mixing it into a subscription run rate makes MRR move with traffic.

`as_of_ts` is a job parameter. Left empty it prices at the moment of the run; a backdated
rebuild is a parameter on a run, not an edit to the SQL.

## AR ageing

**Open balance** is the invoice header `total_amt` of every invoice with status 20 (issued)
or 40 (overdue). Status 30 is paid, 10 is draft and not a receivable.

**Balances are all-or-nothing, because the source has no payment table.** The migrated
estate records no payments or allocations, so an invoice is either fully open or paid. This
is a limit of the source, not a modelling decision, and it means the open balance is an
upper bound: a partly paid invoice still shows its full value.

**Invoice lines are deliberately not summed.** 150,000 lines exist, but the line sum ties to
the header total on **0 of 18,745** invoices with lines, and 37 lines point at an
`invoice_id` with no header. Summing lines would restate the receivable on every invoice, so
the header is the single authority for money and the line problems go to `dq_exceptions`
(`orphan_invoice_line`, `line_total_ne_header_total`).

**Buckets** are by days past due at `as_of_date`: `not yet due` (≤ 0), `0-30`, `31-60`,
`61-90`, `90+`.

**An unparseable date never makes money disappear.** Ageing reads the **due date** only. If
the due date is null or does not parse as the legacy `DD-MON-YY`, the invoice goes to the
`unknown` bucket and stays in the open balance total. It is never aged to 90+ (which would
overstate collections risk) and never dropped (which would understate the receivable). An
unparseable **invoice** date does not change the bucket at all: the invoice ages normally
from its due date, but it drops out of the due-before-invoice check and out of the default
as-of date. The two failures are separate `dq_exceptions` rules, `unparseable_due_date` and
`unparseable_invoice_date`, because their consequences differ. Today all 18,750 headers
parse on both dates, so both rules are empty — they exist so that stops being silently true.

A due date **earlier** than the invoice date parses fine and ages normally, but the invoice
is past due on issue, so the bucket is a poor collections signal. 4,184 open invoices are
like this and each is flagged (`due_before_invoice_date`).

`as_of_date` left empty ages the ledger at its own latest open-invoice date (2025-12-28)
rather than today. Defaulting to today would put the entire book in 90+ and hide its shape.
Only an **empty** value means "derive it": a value that is present but not a date fails the
run rather than falling back to the default, and the same rule applies to `as_of_ts` on
ARR/MRR. A typo in a backdated rebuild is an error, not a silently different number.

**Customer names come from `ow_tp.bronze.customer_master`**, one row per `cust_id`, not from
the denormalised copy on invoice lines: an invoice with no lines would otherwise be
nameless, and a renamed customer would be labelled by whichever line copy sorted highest.
Line copies that disagree with the master, and open invoices whose customer is missing from
it, are recorded (`customer_name_disagrees_with_master`, `customer_missing_from_master`).
The disagreement check compares every distinct `(cust_id, cust_name)` pair on the lines, so
a customer carrying one correct name and one stale one is still reported. Today all 8,252
open invoices resolve a name, every customer carries exactly one line name, and no copy
disagrees.

**AR is not joined to tenants.** The invoice ledger's `tenant_id` values come from the legacy
customer master and do not intersect the Lakebase billing tenant ids at all. AR is therefore
reported by invoice and customer only, never rolled up to a tenant next to ARR or usage.
Every open invoice carries the `tenant_id_not_in_billing_domain` exception so the gap is on
the record rather than hidden behind an empty join.

## Overage

**Overage** is the amount billed for usage above plan entitlement, per tenant per calendar
month. It reproduces the legacy `PKG_RATING.compute_rating` arithmetic, including the parts
nobody would design today:

- All usage kinds (api, storage, compute) consume one shared entitlement.
- The tenant's subscription for a period is the latest-starting one overlapping it
  (`starts_on <= period_end AND (ends_on IS NULL OR ends_on >= period_start)`).
- Rollover is the banked units of the prior three periods, capped at 2× entitlement.
- `billable = GREATEST(used − rollover − entitlement, 0)`.
- **The price break is at 101 units, not 100.** The first 101 billable units go at the plan
  overage rate, everything above at 1.5×. The legacy source leaves the 101 unexplained;
  changing it would change the bill, so it stays, and the amount is rounded to cents at the
  same two points the legacy code rounds.
- A subscription suspended inside the period prorates both billable units and the amount by
  the fraction of the period after the suspension date.

**A period that cannot be rated is NULL, not zero.** No covering subscription or no plan
gives 0 billable units and a NULL overage amount, recorded as `usage_without_rateable_plan`.
"Not rateable" must never read as "free".

## Storage cost per tenant

The estate has no storage price. Plans price exactly one thing — units above entitlement, at
the plan overage rate — and storage events consume the same entitlement as everything else.
So storage cost has to be stated as a rule, and two are published side by side:

- **`storage_cost_allocated`** — the tenant's actually-billed overage for the period, split
  across usage kinds in proportion to units. This is the only figure that ties back to money
  the business bills: storage + api + compute = the period's overage amount. A tenant inside
  its entitlement has 0.00 storage cost even with real storage usage, because nothing was
  billed for it.
- **`storage_cost_at_list`** — storage units × plan overage rate, ignoring entitlement,
  rollover and tiering. A unit-economics view of storage on its own. It does **not** tie to
  billed revenue and is always the smaller, simpler number.

Allocation is by raw unit share. The legacy engine has no notion of ordering within a
period, so any "storage arrived last" rule would be invented here. Cent-rounding residual is
carried on the largest usage kind so the three allocations add back to the period overage
exactly.

## Malformed lists, and other dirty data

`invoice_line.gl_acct_csv` is a comma-separated list of GL accounts. **No gold metric splits
it.** Nothing here posts to the GL, so parsing it would only create a chance to mis-post.
Values that are not a clean `n,n,n` list are carried through unchanged and recorded as
`malformed_gl_account_list`, so the eventual GL feed does not inherit them unnoticed.

Every rule that changes a number — or that is a known trap — writes a row to
`ow_tp.gold.dq_exceptions` naming the entity, the rule, the treatment and the money at
stake. The difference between a gold number and a raw source number can always be accounted
for line by line.

## Refresh

`ow_tp_finance_gold` (Lakeflow) rebuilds the gold tables on the existing serverless
warehouse, 2 retries per task, 5 minutes apart. Its schedule (06:15 UTC daily) is **created
paused**.

    build_subscription_mrr ─┬─> build_usage_period ──> build_storage_cost ─┬─> build_dq_exceptions
    build_ar_open_invoice ──┴───────────────────────────────────────────────┘

The Lakebase reference load (`ingest_lakebase_reference.py`) is not a job task: it needs
Python compute to reach Postgres and no new clusters may be created here, so it is run
deliberately. Those tables (plans, tenants, subscriptions, credit notes, rating results)
change rarely; the ones the job rebuilds are the ones that move.

That is a real staleness window: a plan change or a suspension in the OLTP system does not
reach ARR until the load is run. Rather than leave it implicit, `dq_exceptions` raises
`reference_snapshot_stale` once a reference snapshot is more than 7 days old, so the
dashboard shows the run rate is being priced from an old snapshot. Closing the window
properly needs the load to run on job compute that can reach Postgres.

**A reference snapshot is all-or-nothing.** The load reads all five Lakebase tables inside
one `REPEATABLE READ READ ONLY` transaction and writes nothing until every read has
succeeded, so a Postgres error cannot leave half the reference set replaced. The five writes
are still five statements, so every row carries a `snapshot_id` from the run that produced
it and `fct_subscription_mrr` refuses to build when the five reference tables disagree on
it. It checks all five, not only the three it reads: it is the first task in the refresh
graph, so failing it also stops the usage and storage builds, which read rating results. A
load that dies between writes fails the next refresh instead of pricing new plans against
old subscriptions.

It reads Lakebase branch `mig-p1-w2`, which is where pipeline 1's data landed. `mig-p1-w0`
is the intake-era branch name still quoted in older briefs and holds only
`billing_audit_log`, `md5_parity_input` and `rating_state`.
