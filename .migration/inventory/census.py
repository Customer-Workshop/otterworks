"""Read-only Oracle census for OW_BILLING (profile discovery_commands + aggregate probes).

Writes metadata and aggregates only (no production rows) to .migration/inventory/census.json.
"""
import json
import os
from pathlib import Path

import oracledb
from recon.adapters import parse_oracle_secret

OUT = Path(__file__).resolve().parent / "census.json"
S = {"schema": "OW_BILLING"}


def rows(cur):
    names = [d[0].lower() for d in cur.description]
    return [dict(zip(names, [str(v) if v is not None and not isinstance(v, (int, float, str)) else v for v in r])) for r in cur.fetchall()]


def main():
    user, password, dsn = parse_oracle_secret(os.environ["OW_TP_ORACLE_RO_DSN"])
    out = {}
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cur = conn.cursor()
        cur.execute("SELECT owner, table_name, num_rows FROM all_tables WHERE owner = :schema ORDER BY num_rows DESC", S)
        out["tables"] = rows(cur)
        cur.execute("SELECT table_name, column_name, data_type, data_length, data_precision, data_scale, nullable, char_used FROM all_tab_columns WHERE owner = :schema ORDER BY table_name, column_id", S)
        out["columns"] = rows(cur)
        cur.execute("SELECT c.table_name, c.constraint_name, c.constraint_type, cc.column_name, c.r_constraint_name, c.delete_rule FROM all_constraints c JOIN all_cons_columns cc ON c.constraint_name = cc.constraint_name AND c.owner = cc.owner WHERE c.owner = :schema AND c.constraint_type IN ('P','R','U') ORDER BY c.table_name, cc.position", S)
        out["constraints"] = rows(cur)
        cur.execute("SELECT i.index_name, i.table_name, i.uniqueness, i.index_type, ic.column_name, ic.column_position FROM all_indexes i JOIN all_ind_columns ic ON ic.index_owner = i.owner AND ic.index_name = i.index_name WHERE i.owner = :schema ORDER BY i.table_name, i.index_name, ic.column_position", S)
        out["indexes"] = rows(cur)
        cur.execute("SELECT object_name, object_type, status FROM all_objects WHERE owner = :schema AND object_type IN ('PACKAGE','PACKAGE BODY','PROCEDURE','FUNCTION','TRIGGER','MATERIALIZED VIEW','VIEW','SEQUENCE','TYPE') ORDER BY object_type, object_name", S)
        out["objects"] = rows(cur)
        cur.execute("SELECT name, type, referenced_name, referenced_type FROM all_dependencies WHERE owner = :schema AND referenced_owner = :schema ORDER BY name, referenced_name", S)
        out["dependencies"] = rows(cur)
        cur.execute("SELECT sequence_name, last_number, increment_by FROM all_sequences WHERE sequence_owner = :schema", S)
        out["sequences"] = rows(cur)
        cur.execute("SELECT DISTINCT name, type FROM all_source WHERE owner = :schema AND UPPER(text) LIKE '%ROWID%'", S)
        out["rowid_usage"] = rows(cur)
        cur.execute("SELECT DISTINCT name, type FROM all_source WHERE owner = :schema AND (UPPER(text) LIKE '%NLS_SORT%' OR UPPER(text) LIKE '%NLS_COMP%' OR UPPER(text) LIKE '%COLLATE%')", S)
        out["nls_usage"] = rows(cur)
        cur.execute("SELECT job_name, job_type, enabled, state, repeat_interval FROM all_scheduler_jobs WHERE owner = :schema", S)
        out["scheduler_jobs"] = rows(cur)
        cur.execute("SELECT trigger_name, table_name, triggering_event, status FROM all_triggers WHERE owner = :schema ORDER BY table_name, trigger_name", S)
        out["triggers"] = rows(cur)
        cur.execute("SELECT grantee, table_name, privilege FROM all_tab_privs WHERE table_schema = :schema ORDER BY grantee, table_name, privilege", S)
        out["grants"] = rows(cur)

        probes = {}
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT tenant_id), COUNT(tenant_id), COUNT(DISTINCT cust_no), COUNT(DISTINCT conversion_batch_no), MIN(conversion_batch_no), MAX(conversion_batch_no) FROM ow_billing.customer_master")
        probes["customer_master"] = dict(zip(["rows", "distinct_tenant", "nonnull_tenant", "distinct_cust_no", "distinct_batch", "min_batch", "max_batch"], cur.fetchone()))
        cur.execute("SELECT COUNT(*) FROM (SELECT tenant_id FROM ow_billing.customer_master WHERE tenant_id IS NOT NULL GROUP BY tenant_id HAVING COUNT(*) > 1)")
        probes["customer_master"]["tenants_with_multiple_customers"] = cur.fetchone()[0]
        cur.execute("SELECT entity_type, attr_type, COUNT(*) FROM ow_billing.entity_attr_value GROUP BY entity_type, attr_type ORDER BY 1, 2")
        probes["eav_by_type"] = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN c.cust_id IS NULL THEN 1 ELSE 0 END) FROM ow_billing.entity_attr_value e LEFT JOIN ow_billing.customer_master c ON c.cust_id = e.entity_id WHERE e.entity_type = 'CUSTOMER'")
        probes["eav_customer_resolution"] = dict(zip(["customer_rows", "unresolved"], cur.fetchone()))
        cur.execute("SELECT COUNT(*), SUM(n) FROM (SELECT entity_id, attr_name, COUNT(*) n FROM ow_billing.entity_attr_value WHERE entity_type = 'CUSTOMER' GROUP BY entity_id, attr_name HAVING COUNT(*) > 1)")
        probes["eav_duplicate_name_groups"] = dict(zip(["groups", "rows"], cur.fetchone()))
        cur.execute("SELECT COUNT(DISTINCT entity_id), MAX(n) FROM (SELECT entity_id, COUNT(*) n FROM ow_billing.entity_attr_value WHERE entity_type = 'CUSTOMER' GROUP BY entity_id)")
        probes["eav_per_customer"] = dict(zip(["customers_with_attrs", "max_attrs"], cur.fetchone()))
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN attr_value IS NULL THEN 1 ELSE 0 END), MAX(LENGTH(attr_value)), SUM(CASE WHEN attr_value <> RTRIM(attr_value) THEN 1 ELSE 0 END) FROM ow_billing.entity_attr_value")
        probes["eav_values"] = dict(zip(["rows", "null_value", "max_len", "trailing_space"], cur.fetchone()))
        cur.execute("SELECT COUNT(created_dt), SUM(CASE WHEN created_dt IS NOT NULL AND VALIDATE_CONVERSION(created_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END) FROM ow_billing.entity_attr_value")
        probes["eav_created_dt"] = dict(zip(["nonnull", "unparseable"], cur.fetchone()))
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT l.invoice_id), SUM(CASE WHEN h.invoice_id IS NULL THEN 1 ELSE 0 END) FROM ow_billing.invoice_line l LEFT JOIN ow_billing.invoice_header h ON h.invoice_id = l.invoice_id")
        r = cur.fetchone()
        probes["invoice_line"] = {"rows": r[0], "orphans": r[2]}
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN invoice_id IS NULL THEN 1 ELSE 0 END), COUNT(DISTINCT invoice_id) FROM ow_billing.invoice_line l WHERE NOT EXISTS (SELECT 1 FROM ow_billing.invoice_header h WHERE h.invoice_id = l.invoice_id)")
        probes["invoice_line"]["orphan_detail"] = dict(zip(["rows", "null_invoice_id", "distinct_missing_invoice_ids"], cur.fetchone()))
        cur.execute("SELECT MAX(n), MIN(n) FROM (SELECT invoice_id, COUNT(*) n FROM ow_billing.invoice_line GROUP BY invoice_id)")
        probes["invoice_line"]["lines_per_invoice_max_min"] = list(cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM (SELECT invoice_id, line_no FROM ow_billing.invoice_line GROUP BY invoice_id, line_no HAVING COUNT(*) > 1)")
        probes["invoice_line"]["dup_invoice_line_no"] = cur.fetchone()[0]
        cur.execute("SELECT SUM(CASE WHEN line_no IS NULL THEN 1 ELSE 0 END), COUNT(invoice_dt), SUM(CASE WHEN invoice_dt IS NOT NULL AND VALIDATE_CONVERSION(invoice_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END), COUNT(gl_acct_csv), SUM(CASE WHEN gl_acct_csv LIKE '%,,%' OR gl_acct_csv LIKE ',%' OR gl_acct_csv LIKE '%,' THEN 1 ELSE 0 END), SUM(CASE WHEN posted_yn IS NULL THEN 1 ELSE 0 END), SUM(CASE WHEN posted_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), SUM(CASE WHEN cust_id IS NULL THEN 1 ELSE 0 END) FROM ow_billing.invoice_line")
        probes["invoice_line"]["domains"] = dict(zip(["null_line_no", "invoice_dt_nonnull", "invoice_dt_unparseable", "gl_csv_nonnull", "gl_csv_malformed", "posted_null", "posted_other", "null_cust_id"], cur.fetchone()))
        cur.execute("SELECT line_type_cd, COUNT(*) FROM ow_billing.invoice_line GROUP BY line_type_cd ORDER BY 1")
        probes["invoice_line"]["line_type_cd"] = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT posted_yn, COUNT(*) FROM ow_billing.invoice_line GROUP BY posted_yn ORDER BY 1")
        probes["invoice_line"]["posted_yn"] = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN c.cust_id IS NULL THEN 1 ELSE 0 END), COUNT(DISTINCT h.batch_no), SUM(CASE WHEN VALIDATE_CONVERSION(h.invoice_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN VALIDATE_CONVERSION(h.due_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN h.invoice_dt IS NULL THEN 1 ELSE 0 END), SUM(CASE WHEN h.due_dt IS NULL THEN 1 ELSE 0 END) FROM ow_billing.invoice_header h LEFT JOIN ow_billing.customer_master c ON c.cust_id = h.cust_id")
        probes["invoice_header"] = dict(zip(["rows", "unresolved_cust", "distinct_batch", "invoice_dt_unparseable", "due_dt_unparseable", "invoice_dt_null", "due_dt_null"], cur.fetchone()))
        cur.execute("SELECT status_cd, COUNT(*) FROM ow_billing.invoice_header GROUP BY status_cd ORDER BY 1")
        probes["invoice_header"]["status_cd"] = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT code_type, COUNT(*) FROM ow_billing.codes GROUP BY code_type ORDER BY 1")
        probes["codes"] = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT SUM(CASE WHEN signup_dt IS NOT NULL AND VALIDATE_CONVERSION(signup_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN last_invoice_dt IS NOT NULL AND VALIDATE_CONVERSION(last_invoice_dt AS DATE, 'DD-MON-RR', 'NLS_DATE_LANGUAGE=AMERICAN') = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN related_acct_ids LIKE '%,,%' OR related_acct_ids LIKE ',%' OR related_acct_ids LIKE '%,' THEN 1 ELSE 0 END), SUM(CASE WHEN promo_codes_csv LIKE '%,,%' OR promo_codes_csv LIKE ',%' OR promo_codes_csv LIKE '%,' THEN 1 ELSE 0 END), SUM(CASE WHEN tax_exempt_yn NOT IN ('Y','N') THEN 1 ELSE 0 END), SUM(CASE WHEN cust_name <> RTRIM(cust_name) THEN 1 ELSE 0 END) FROM ow_billing.customer_master")
        probes["customer_master"]["traps"] = dict(zip(["signup_dt_unparseable", "last_invoice_dt_unparseable", "related_ids_malformed", "promo_csv_malformed", "tax_exempt_other", "cust_name_trailing_space"], cur.fetchone()))
    out["probes"] = probes
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(probes, indent=1, default=str))


if __name__ == "__main__":
    main()
