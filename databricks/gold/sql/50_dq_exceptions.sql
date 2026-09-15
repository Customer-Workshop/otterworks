-- ow_tp.gold.dq_exceptions — one row per source record the gold layer could not take at
-- face value.
--
-- The point of this table is that nothing disappears quietly. Every rule below either
-- changes a metric or is a known trap in the legacy data; each exception names the entity,
-- the rule, how the metric treated it, and the money at stake, so the difference between a
-- gold number and a raw source number can always be accounted for line by line.
CREATE OR REPLACE TABLE ow_tp.gold.dq_exceptions
COMMENT 'Source records the gold layer could not take at face value: orphan invoice lines, line/header disagreement, unparseable or inverted dates, malformed GL account lists, cross-domain tenant ids, unrateable usage. Each row records the rule and what the metric did about it.'
AS
-- Orphan invoice lines: a line whose invoice_id has no header. Excluded from every metric,
-- because AR is built from headers; the line amount is recorded here so the gap is visible.
SELECT
  'invoice_line'                              AS entity,
  l.line_id                                   AS entity_id,
  l.invoice_id                                AS parent_id,
  l.tenant_id                                 AS tenant_id,
  'orphan_invoice_line'                       AS rule_name,
  'invoice line references an invoice_id with no header row'          AS detail,
  'excluded from AR ageing (AR is built from invoice headers)'        AS metric_treatment,
  CAST(l.amount AS DECIMAL(14,2))             AS amount_at_risk,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)  AS built_at
FROM ow_tp.silver.invoice_line l
LEFT ANTI JOIN ow_tp.silver.invoice_header h ON h.invoice_id = l.invoice_id

UNION ALL
-- Line/header disagreement: the sum of an invoice's lines (net of tax) does not equal the
-- header total. Recorded per invoice, with the difference as the amount at risk.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'line_total_ne_header_total',
  CONCAT('header total ', CAST(h.total_amt AS STRING),
         ' vs line sum ', CAST(COALESCE(l.line_sum, 0) AS STRING)),
  'header total is authoritative; line sum is not used for AR',
  CAST(h.total_amt - COALESCE(l.line_sum, 0) AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
LEFT JOIN (SELECT invoice_id, SUM(amount) AS line_sum
             FROM ow_tp.silver.invoice_line GROUP BY invoice_id) l
       ON l.invoice_id = h.invoice_id
WHERE h.total_amt <> COALESCE(l.line_sum, 0)

UNION ALL
-- Unparseable due date on an open invoice: ageing reads the due date only, so this is the
-- failure that sends the invoice to the 'unknown' bucket. The balance stays in the total
-- rather than being dropped or silently aged.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'unparseable_due_date',
  CONCAT('due_dt=', COALESCE(h.due_dt, '<null>')),
  'open balance kept, ageing bucket = unknown',
  CAST(h.total_amt AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
WHERE h.status_cd IN (20, 40)
  AND TRY_TO_TIMESTAMP(h.due_dt, 'dd-MMM-yy') IS NULL

UNION ALL
-- Unparseable invoice date on an open invoice. Ageing is unaffected — it is computed from
-- the due date — but the invoice drops out of the date-quality checks that compare the two
-- dates, and out of the default as-of date, which is the latest parsed invoice date.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'unparseable_invoice_date',
  CONCAT('invoice_dt=', COALESCE(h.invoice_dt, '<null>')),
  'aged normally from the due date; excluded from the due-before-invoice check and from the default as-of date',
  CAST(h.total_amt AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
WHERE h.status_cd IN (20, 40)
  AND TRY_TO_TIMESTAMP(h.invoice_dt, 'dd-MMM-yy') IS NULL

UNION ALL
-- Due date before invoice date: parses cleanly, so ageing still works, but the invoice is
-- born past due and the bucket is unreliable as a collections signal.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'due_before_invoice_date',
  CONCAT('invoice_dt=', h.invoice_dt, ' due_dt=', h.due_dt),
  'aged normally; flagged because the invoice is past due on issue',
  CAST(h.total_amt AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
WHERE h.status_cd IN (20, 40)
  AND TRY_TO_TIMESTAMP(h.due_dt, 'dd-MMM-yy') < TRY_TO_TIMESTAMP(h.invoice_dt, 'dd-MMM-yy')

UNION ALL
-- Malformed GL account list: gl_acct_csv is a comma-separated list of account numbers.
-- Empty entries, non-numeric entries and stray separators all appear in the source. No
-- metric here splits the list, so nothing is silently mis-posted, but the malformed values
-- are recorded so the eventual GL feed does not inherit them unnoticed.
SELECT
  'invoice_line', l.line_id, l.invoice_id, l.tenant_id,
  'malformed_gl_account_list',
  CONCAT('gl_acct_csv=', COALESCE(l.gl_acct_csv, '<null>')),
  'list not parsed by any gold metric; value carried through unchanged',
  CAST(l.amount AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_line l
WHERE l.gl_acct_csv IS NOT NULL
  AND NOT (l.gl_acct_csv RLIKE '^[0-9]+(,[0-9]+)*$')

UNION ALL
-- Customer name on an invoice line disagrees with the customer master. AR labels customers
-- from ow_tp.bronze.customer_master, so a stale denormalised copy on a line no longer
-- changes any reported name; it is recorded here rather than being resolved by picking one.
SELECT
  'customer', x.cust_id, NULL, NULL,
  'customer_name_disagrees_with_master',
  CONCAT('master=', COALESCE(m.cust_name, '<null>'),
         ' invoice_line=', COALESCE(x.line_name, '<null>')),
  'AR reports the customer master name; the invoice-line copy is ignored',
  NULL,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM (SELECT cust_id, MAX(cust_name) AS line_name
        FROM ow_tp.silver.invoice_line GROUP BY cust_id) x
JOIN ow_tp.bronze.customer_master m ON m.cust_id = x.cust_id
WHERE m.cust_name IS DISTINCT FROM x.line_name

UNION ALL
-- Open invoice whose customer is absent from the customer master: it would be reported
-- with no customer name at all, so the gap is recorded rather than left blank on a report.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'customer_missing_from_master',
  CONCAT('cust_id=', COALESCE(h.cust_id, '<null>')),
  'open balance kept; customer name reported as NULL',
  CAST(h.total_amt AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
LEFT ANTI JOIN ow_tp.bronze.customer_master m ON m.cust_id = h.cust_id
WHERE h.status_cd IN (20, 40)

UNION ALL
-- Cross-domain tenant id: the invoice ledger's tenant ids come from the legacy customer
-- master and do not intersect the Lakebase billing tenant ids at all, so AR cannot be
-- joined to subscriptions or usage by tenant. Recorded once per open invoice rather than
-- forcing a join that would invent tenant-level totals.
SELECT
  'invoice', h.invoice_id, NULL, h.tenant_id,
  'tenant_id_not_in_billing_domain',
  'invoice tenant_id does not exist in ow_tp.gold.dim_tenant',
  'AR is reported by invoice/customer only; never joined to ARR or usage by tenant',
  CAST(h.total_amt AS DECIMAL(14,2)),
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.silver.invoice_header h
LEFT ANTI JOIN ow_tp.gold.dim_tenant t ON t.tenant_id = h.tenant_id
WHERE h.status_cd IN (20, 40)

UNION ALL
-- Usage that cannot be rated: no covering subscription or no plan for the period. Overage
-- is NULL for these rows rather than 0.00, so "not rateable" never reads as "free".
SELECT
  'usage_period', CONCAT(u.tenant_id, '|', CAST(u.period_start AS STRING)), NULL, u.tenant_id,
  'usage_without_rateable_plan',
  CONCAT('period ', u.period_month, ' used_units=', CAST(u.used_units AS STRING)),
  'billable units 0, overage amount NULL (not rateable)',
  NULL,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.gold.fct_usage_period u
WHERE u.plan_id IS NULL OR u.overage_rate IS NULL

UNION ALL
-- Stale Lakebase reference snapshot. The scheduled job rebuilds the metric tables but
-- cannot reload Lakebase (that needs Python compute, and no cluster may be created here),
-- so a plan change or a suspension in the OLTP system reaches ARR only after someone runs
-- databricks/gold/python/ingest_lakebase_reference.py. This row makes that visible on the
-- dashboard instead of leaving a stale run rate to look current.
SELECT
  'reference_snapshot', x.table_name, NULL, NULL,
  'reference_snapshot_stale',
  CONCAT('ingested_at=', CAST(x.ingested_at AS STRING),
         ' branch=', COALESCE(x.source_lakebase_branch, '<null>')),
  'ARR/MRR and entitlements are priced from a snapshot older than 7 days',
  NULL,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM (
  SELECT 'dim_plan' AS table_name, MAX(ingested_at) AS ingested_at,
         MAX(source_lakebase_branch) AS source_lakebase_branch FROM ow_tp.gold.dim_plan
  UNION ALL
  SELECT 'fct_subscription', MAX(ingested_at), MAX(source_lakebase_branch)
    FROM ow_tp.gold.fct_subscription
  UNION ALL
  SELECT 'dim_tenant', MAX(ingested_at), MAX(source_lakebase_branch)
    FROM ow_tp.gold.dim_tenant
) x
WHERE x.ingested_at < current_timestamp() - INTERVAL 7 DAYS

UNION ALL
-- Subscription pointing at a plan that no longer exists: it would price at NULL, so it is
-- reported instead of quietly contributing 0.00 to MRR.
SELECT
  'subscription', s.subscription_id, s.plan_id, s.tenant_id,
  'subscription_plan_missing',
  'subscription references a plan_id absent from ow_tp.gold.dim_plan',
  'contributes 0.00 to MRR/ARR',
  NULL,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)
FROM ow_tp.gold.fct_subscription s
LEFT ANTI JOIN ow_tp.gold.dim_plan p ON p.plan_id = s.plan_id
