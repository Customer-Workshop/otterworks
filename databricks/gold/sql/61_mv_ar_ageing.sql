-- ow_tp.gold.mv_ar_ageing — open receivable by ageing bucket.
-- The bucket stored on the fact is the one computed at the table's as_of_date; the view
-- also exposes a bucket recomputed against today so the same rows can be aged live without
-- rebuilding the table. Both keep the 'unknown' bucket: an invoice with a date that will
-- not parse stays in the balance instead of disappearing from AR.
CREATE OR REPLACE VIEW ow_tp.gold.mv_ar_ageing
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Open accounts receivable (invoice status issued or overdue) bucketed 0-30/31-60/61-90/90+ by days past due. Balance is the invoice header total; the estate has no payment table, so an invoice is open in full until its status becomes paid."
source: ow_tp.gold.fct_ar_open_invoice
dimensions:
  - name: Ageing Bucket
    expr: ageing_bucket
    comment: "not yet due / 0-30 / 31-60 / 61-90 / 90+ / unknown (unparseable due date)"
  - name: Ageing Bucket Today
    expr: CASE
        WHEN due_ts IS NULL THEN 'unknown'
        WHEN DATEDIFF(current_date(), CAST(due_ts AS DATE)) <= 0 THEN 'not yet due'
        WHEN DATEDIFF(current_date(), CAST(due_ts AS DATE)) <= 30 THEN '0-30'
        WHEN DATEDIFF(current_date(), CAST(due_ts AS DATE)) <= 60 THEN '31-60'
        WHEN DATEDIFF(current_date(), CAST(due_ts AS DATE)) <= 90 THEN '61-90'
        ELSE '90+'
      END
    comment: "Same rows aged against today rather than the table's as_of_date"
  - name: Invoice Status
    expr: invoice_status
  - name: Customer
    expr: cust_name
  - name: Invoice Month
    expr: DATE_TRUNC('MONTH', invoice_ts)
  - name: Due Month
    expr: DATE_TRUNC('MONTH', due_ts)
  - name: As Of Date
    expr: as_of_date
  - name: Has Date Exception
    expr: dq_due_date_unparseable OR dq_due_before_invoice
measures:
  - name: Open Balance
    expr: SUM(open_amount)
    comment: "Open receivable in decimal currency"
  - name: Open Invoices
    expr: COUNT(1)
  - name: Customers With Balance
    expr: COUNT(DISTINCT cust_id)
  - name: Average Days Past Due
    expr: AVG(days_past_due)
    comment: "NULL-dated invoices are excluded from the average but not from the balance"
  - name: Balance Past Due
    expr: SUM(CASE WHEN days_past_due > 0 THEN open_amount ELSE 0 END)
  - name: Balance With Unknown Ageing
    expr: SUM(CASE WHEN due_ts IS NULL THEN open_amount ELSE 0 END)
    comment: "Money that could not be aged; always reported, never dropped"
$$
