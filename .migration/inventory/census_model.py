"""Read-only model probes for OW_BILLING: value domains and precision checks that decide BSON types.

Aggregates only (no production rows) -> .migration/inventory/census_model.json.
"""
import json
import os
from pathlib import Path

import oracledb
from recon.adapters import parse_oracle_secret

OUT = Path(__file__).resolve().parent / "census_model.json"



def _vals(row):
    return [int(v) if v is not None else None for v in row]


def main():
    user, password, dsn = parse_oracle_secret(os.environ["OW_TP_ORACLE_RO_DSN"])
    out = {}
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cur = conn.cursor()
        cur.execute("SELECT SUM(CASE WHEN tax_exempt_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), SUM(CASE WHEN credit_hold_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), SUM(CASE WHEN dunning_exempt_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), SUM(CASE WHEN vip_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), COUNT(tax_exempt_yn), COUNT(credit_hold_yn), COUNT(dunning_exempt_yn), COUNT(vip_yn) FROM ow_billing.customer_master")
        out["yn_domain_customer_master"] = _vals(cur.fetchone())
        cur.execute("SELECT SUM(CASE WHEN posted_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), COUNT(posted_yn) FROM ow_billing.invoice_line")
        out["yn_domain_invoice_line"] = _vals(cur.fetchone())
        cur.execute("SELECT (SELECT SUM(CASE WHEN tax_exempt_yn NOT IN ('Y','N') THEN 1 ELSE 0 END) FROM ow_billing.tenants), (SELECT SUM(CASE WHEN active_yn NOT IN ('Y','N') THEN 1 ELSE 0 END) FROM ow_billing.plans) FROM dual")
        out["yn_domain_tenants_plans"] = _vals(cur.fetchone())
        cur.execute("SELECT (SELECT COUNT(*) FROM ow_billing.usage_events WHERE occurred_at <> CAST(occurred_at AS TIMESTAMP(3))), (SELECT COUNT(*) FROM ow_billing.invoices WHERE issued_at <> CAST(issued_at AS TIMESTAMP(3))), (SELECT COUNT(*) FROM ow_billing.rating_results WHERE created_at <> CAST(created_at AS TIMESTAMP(3))), (SELECT COUNT(*) FROM ow_billing.notifications WHERE sent_at <> CAST(sent_at AS TIMESTAMP(3))) FROM dual")
        out["ts_submillisecond"] = _vals(cur.fetchone())
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN NVL(l.cust_id,'~') <> NVL(h.cust_id,'~') THEN 1 ELSE 0 END), SUM(CASE WHEN NVL(l.tenant_id,'~') <> NVL(h.tenant_id,'~') THEN 1 ELSE 0 END), SUM(CASE WHEN NVL(l.invoice_no,'~') <> NVL(h.invoice_no,'~') THEN 1 ELSE 0 END) FROM ow_billing.invoice_line l JOIN ow_billing.invoice_header h ON h.invoice_id = l.invoice_id")
        out["line_vs_header_denorm"] = _vals(cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM (SELECT invoice_id, line_no, line_id FROM ow_billing.invoice_line GROUP BY invoice_id, line_no, line_id HAVING COUNT(*) > 1)")
        out["line_dup_key_full"] = _vals(cur.fetchone())
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT invoice_no), COUNT(invoice_no) FROM ow_billing.invoice_header")
        out["header_invoice_no_distinct"] = _vals(cur.fetchone())
        cur.execute("SELECT SUM(CASE WHEN signup_dt IS NOT NULL AND VALIDATE_CONVERSION(signup_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN last_activity_dt IS NOT NULL AND VALIDATE_CONVERSION(last_activity_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN last_invoice_dt IS NOT NULL AND VALIDATE_CONVERSION(last_invoice_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN last_payment_dt IS NOT NULL AND VALIDATE_CONVERSION(last_payment_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN terminate_dt IS NOT NULL AND VALIDATE_CONVERSION(terminate_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END) FROM ow_billing.customer_master")
        out["text_date_parse_customer_master"] = _vals(cur.fetchone())
        cur.execute("SELECT (SELECT SUM(CASE WHEN invoice_dt IS NOT NULL AND VALIDATE_CONVERSION(invoice_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END) FROM ow_billing.invoice_header), (SELECT SUM(CASE WHEN due_dt IS NOT NULL AND VALIDATE_CONVERSION(due_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END) FROM ow_billing.invoice_header), (SELECT SUM(CASE WHEN invoice_dt IS NOT NULL AND VALIDATE_CONVERSION(invoice_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END) FROM ow_billing.invoice_line), (SELECT SUM(CASE WHEN created_dt IS NOT NULL AND VALIDATE_CONVERSION(created_dt AS DATE, 'DD-MON-RR') = 0 THEN 1 ELSE 0 END) FROM ow_billing.entity_attr_value) FROM dual")
        out["text_date_parse_invoices"] = _vals(cur.fetchone())
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT code_type) FROM ow_billing.codes")
        out["codes_count"] = _vals(cur.fetchone())
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
