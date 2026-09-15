# ow_tp dunning risk

**This ranks the overdue queue by invoice age and outstanding exposure. It is not a
validated predictor of who will default or who will pay** — its non-aging signals score at
chance against the only label this data has, and there is no dunning-outcome history to
test them against at all (see "How honest the validation is").

Even so, ordering is worth having. `pkg_dunning.sp_schedule_dunning` walks every status-40
invoice in one undifferentiated loop, schedules the next attempt, and hides any failure
behind `WHEN OTHERS THEN NULL`. This adds the missing input: a number and a list of reasons
per open invoice, so the queue can be worked worst-first.

**It is an input, not an instruction.** Nothing here schedules, sends, skips, suspends or
writes off anything. The tables are read-only facts; the dunning process and the people
running it still decide. The tests enforce that the SQL never touches `dunning_attempts`,
`notifications`, `subscriptions` or `tenants`.

## What the score means

A points total from 0 to 100, and a band. It is **not** a probability of default, and not a
predicted recovery. Read it as "this invoice has more of the things we treat as worrying
than that one". Every point is traceable: `reason_codes` lists the rules that fired and
`ow_tp.gold.dunning_risk_rules` holds their points, so any row can be reconstructed by hand.

| band | score |
| --- | --- |
| LOW | 0-19 |
| MEDIUM | 20-39 |
| HIGH | 40-59 |
| CRITICAL | 60-100 |
| EXEMPT | the account is flagged dunning-exempt; scored 0 and excluded |
| NO_OPEN_ITEMS | account grain only: nothing open to chase |

Where the thresholds come from: aging is 14/28/56/84 days, multiples of the one interval the
legacy estate actually declares (`sp_suspend_overdue` suspends at 14 days overdue). The rest
are round numbers chosen so that no single signal can reach a band on its own and so that
age plus one other concern reaches HIGH. **They were not fitted.** See below.

## How honest the validation is

Short version: the aging part of the score is sound because it is arithmetic, and the rest
is not validated.

- There is no dunning-outcome label, and that is a gap in the data, not a choice made
  here. `billing.dunning_attempts` holds **one row**, it exists only on Lakebase, and its
  tenant keys do not intersect the migrated invoice history, so nothing joins. "Did chasing
  this invoice recover the money" cannot be asked here at all. The recon report records
  that coverage as 0 rows rather than quietly substituting something else.

  Three things would have to exist before the non-aging signals could be tested: a dunning
  attempt history over a meaningful span (one row per attempt, with invoice, attempt time,
  channel and level), an outcome per attempt (paid after contact, promised, disputed,
  escalated, no response) with the payment date so recovery can be timed, and a key that
  joins those attempts to the invoices in Delta. With about a year of that, the points
  could be fitted rather than chosen.
- The closest available label is "the invoice ended status 40". Against it, on the 13,246
  closed invoices, the non-aging rules give **AUC 0.5012**, and on the 2021-onward holdout
  **0.4946**. Chance is 0.5. They do not discriminate.
- Aging rules are excluded from that test on purpose: days-since-issue is most of what makes
  an invoice status 40, so scoring it and then testing against it would produce a strong
  number that means nothing.
- Baseline overdue rate is 20.7%. Band rates land on top of it: LOW 20.7% (n=12,661),
  MEDIUM 21.0% (n=582). The bands are not separating anything the data can see.

So: the score is a **defensible ordering of the queue**, mostly by age and exposure, with its
reasoning printed. It is not evidence that a high-scoring invoice is more likely to go bad.
Anyone who wants that has to instrument the dunning process first and label real outcomes.

## Features that are NULL and why

Four of the requested signals are not built. Their sources reached Lakebase during pipeline 1
but not Delta, and they sit on the tenant key space that does not join to the invoice
history. They are NULL columns carrying the reason, never zero — a zero here would read as
"no prior attempts, no credit notes", which is good news the data does not support.

| signal | column | reason |
| --- | --- | --- |
| previous dunning attempts and outcomes | `prior_dunning_attempts` | `source_in_lakebase_only` |
| credit notes | `open_credit_note_amt` | `source_in_lakebase_only` |
| plan | `plan_tier_cd` | `source_in_lakebase_only` |
| usage trend | `usage_trend_ratio` | `tenant_key_space_disjoint` |

Payment lateness history is partly built: 90.5% of closed invoices have a prior-invoice
history, but no payment dates were migrated, so "late by how many days" is unavailable and
the proxy is "what share of this account's earlier invoices ended overdue".

## Tables

| table | grain |
| --- | --- |
| `ow_tp.silver.dunning_risk_features_invoice` | one row per migrated invoice, 18,750 |
| `ow_tp.silver.dunning_risk_features_account` | one row per billing account, 25,000 |
| `ow_tp.gold.dunning_risk_rules` | the model, 13 rules |
| `ow_tp.gold.dunning_risk_invoice` | one row per open invoice, 8,252 |
| `ow_tp.gold.dunning_risk_account` | one row per account, worst open invoice |
| `ow_tp.gold.dunning_risk_backtest` | the numbers above |

Mirrored to Lakebase `ow_tp` / `billing` on branch **`mig-p1-w0`** as
`dunning_risk_rules`, `dunning_risk_invoice` and `dunning_risk_account`. Accounts with
nothing open are not published.

## Running it

Rebuild in Databricks — the Lakeflow job `ow_tp_dunning_risk` does this, or run the six SQL
files in order on warehouse `565cd2fd713738c4`:

    python3 databricks/scoring/dunning_risk/deploy_job.py          # upsert the job, PAUSED

Publish to Lakebase (structure once, rows every time). Both steps are rerunnable, and the
row load replaces all three tables in one transaction, so a reader never sees half a queue:

    python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w0 \
        -- python3 databricks/migration/lakebase/apply_sql.py \
           databricks/migration/lakebase/ow_tp_dunning_risk_score.sql

    python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w0 \
        -- python3 databricks/scoring/dunning_risk/sync_to_lakebase.py

Regenerate the evidence, which reruns the whole pipeline to prove it is idempotent:

    python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w0 \
        -- python3 databricks/scoring/dunning_risk/emit_recon.py

Tests need no warehouse and no credentials:

    python3 -m pytest databricks/scoring/dunning_risk/tests

### The publish is not a job task

The Lakeflow job covers the six Delta tasks only. The publish goes through
`with_lakebase_dsn.py`, which mints a short-lived credential only after checking the branch
against `.migration/allowed_targets.json` in the repo checkout. Putting it in the job would
mean reissuing that credential inside the workspace, outside the allowlist check. It is run
as the step above instead, and this gap is recorded in `unverified_paths` of the recon report
rather than papered over.

### The clock

`as_of` defaults to the newest invoice date in the migrated history, not to `current_date()`.
The extract ends 2025-12-28; against a wall clock every open invoice is instantly past the
oldest aging band and the whole distribution collapses into one bucket. Pass `as_of` as a job
parameter to score as of a different day.

## Known data issues carried, not repaired

- 9,409 invoices have `due_dt` before `invoice_dt`. Surfaced as `due_before_invoice_dt` on
  every feature and score row. Age for those is measured from the invoice date.
- Usage events and invoices share no tenant ids (overlap: 0).
- `customer_master_hist`, `subscriptions_hist` and `billing_audit_log` are empty in silver, so
  nothing is point-in-time correct through them.
- `prior_overdue_rate` reads the *current* status of earlier invoices; no status history was
  migrated. The backtest can therefore see outcomes that were not knowable at the time. That
  bias flatters the score, and the score still does not discriminate.
