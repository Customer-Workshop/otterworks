"""Read-only Oracle recount against oracle_counts.json (static per-table COUNT queries)."""
import json, os, sys
import oracledb
creds = json.loads(os.environ["OW_TP_ORACLE_RO_DSN"])
baseline = json.loads(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_counts.json")).read())
tables = {}
with oracledb.connect(user=creds["user"], password=creds["password"], dsn=creds["dsn"]) as con:
    cur = con.cursor()
    cur.execute("SELECT table_name FROM all_tables WHERE owner = 'OW_BILLING' ORDER BY table_name")
    names = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM ow_billing.BILLING_AUDIT_LOG")
    tables["BILLING_AUDIT_LOG"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.CODES")
    tables["CODES"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.CREDIT_NOTES")
    tables["CREDIT_NOTES"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.CUSTOMER_MASTER")
    tables["CUSTOMER_MASTER"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.CUSTOMER_MASTER_HIST")
    tables["CUSTOMER_MASTER_HIST"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.DUNNING_ATTEMPTS")
    tables["DUNNING_ATTEMPTS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.ENTITY_ATTR_VALUE")
    tables["ENTITY_ATTR_VALUE"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.FIXTURE_META")
    tables["FIXTURE_META"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.INVOICES")
    tables["INVOICES"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.INVOICE_HEADER")
    tables["INVOICE_HEADER"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.INVOICE_LINE")
    tables["INVOICE_LINE"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.INVOICE_LINES")
    tables["INVOICE_LINES"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.NOTIFICATIONS")
    tables["NOTIFICATIONS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.PLANS")
    tables["PLANS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.RATING_PERIODS")
    tables["RATING_PERIODS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.RATING_RESULTS")
    tables["RATING_RESULTS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.SUBSCRIPTIONS")
    tables["SUBSCRIPTIONS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.SUBSCRIPTIONS_HIST")
    tables["SUBSCRIPTIONS_HIST"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.TENANTS")
    tables["TENANTS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.USAGE_EVENTS")
    tables["USAGE_EVENTS"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ow_billing.invoice_line l WHERE NOT EXISTS (SELECT 1 FROM ow_billing.invoice_header h WHERE h.invoice_id = l.invoice_id)")
    orphans = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM all_tab_columns WHERE owner = 'OW_BILLING' AND table_name = 'CUSTOMER_MASTER'")
    columns = cur.fetchone()[0]
now = {"table_count": len(names), "checks": {"invoice_line_orphans": orphans, "customer_master_columns": columns}, "tables": tables}
diffs = []
if now["table_count"] != baseline["table_count"]: diffs.append({"key": "table_count", "baseline": baseline["table_count"], "now": now["table_count"]})
for key in sorted(set(baseline["checks"]) | set(now["checks"])):
    if baseline["checks"].get(key) != now["checks"].get(key): diffs.append({"key": f"checks.{key}", "baseline": baseline["checks"].get(key), "now": now["checks"].get(key)})
for key in sorted(set(baseline["tables"]) | set(tables)):
    if baseline["tables"].get(key) != tables.get(key): diffs.append({"key": f"tables.{key}", "baseline": baseline["tables"].get(key), "now": tables.get(key)})
print(json.dumps({"match": not diffs, "diffs": diffs, "now": now}, indent=2, sort_keys=True))
sys.exit(0 if not diffs else 1)
