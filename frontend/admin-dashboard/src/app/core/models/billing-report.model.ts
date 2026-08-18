export interface BillingReportSource {
  engine: 'oracle' | 'mongodb' | string;
  system: string;
  detail: string;
}

export interface BillingStatusRow {
  status: string;
  invoice_count: number;
  header_total_amt: string;
}

export interface BillingLineRow {
  status: string;
  line_type: string;
  line_count: number;
  line_amount: string;
  line_tax: string;
  invoices_touched: number;
}

export interface MonthEndReport {
  report: string;
  namespace: string;
  batch_no: number;
  source: BillingReportSource;
  generated_at: string;
  by_status: BillingStatusRow[];
  by_status_line_type: BillingLineRow[];
}

export interface ReconciliationCheck {
  name: string;
  status: 'pass' | 'fail' | string;
  expected?: string;
  actual?: string;
}

export interface ReconciliationReport {
  namespace: string;
  batch_no: number;
  source: BillingReportSource;
  generated_at: string;
  balances: {
    customer_count: number;
    current_balance_total: string;
    past_due_total: string;
  };
  status: 'baseline' | 'pass' | 'fail' | string;
  checks: ReconciliationCheck[];
}
