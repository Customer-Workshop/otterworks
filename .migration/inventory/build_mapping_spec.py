"""Build .migration/03_mapping_spec.json from the live column census plus the phase-2 model decisions.

Deterministic: same census.json in, same spec out. Model decisions are the constants below;
the evidence for each is in .migration/inventory/model.md.
"""
import json
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CENSUS = HERE / "census.json"
OUT = HERE.parent / "03_mapping_spec.json"

VERSION = "map-1"
SOURCE_SCHEMA = "OW_BILLING"

LINE_HAS_HEADER = ("EXISTS (SELECT 1 FROM ow_billing.invoice_header h "
                   "WHERE h.invoice_id = invoice_line.invoice_id)")
LINE_ORPHAN = ("NOT EXISTS (SELECT 1 FROM ow_billing.invoice_header h "
               "WHERE h.invoice_id = invoice_line.invoice_id)")
# INVOICE_LINE columns carried by the parent invoice: 0 mismatches over 149,963 joined rows
# (census_model.json line_vs_header_denorm).
LINE_PARENT_COLUMNS = {"INVOICE_ID", "INVOICE_NO", "CUST_ID", "TENANT_ID"}

CANON = {
    "version": "map-1-canon",
    "rules": [
        {"rule": "decimal_round", "applies_to": "decimal", "params": {}},
        {"rule": "datetime_utc_truncate_ms", "applies_to": "date", "params": {}},
        {"rule": "rstrip_spaces", "applies_to": "string", "params": {}},
        {"rule": "empty_string_is_null", "applies_to": "string", "params": {}},
        {"rule": "null_missing_equiv", "applies_to": "*", "params": {}},
    ],
}

# collection, root table, key columns, key targets, root_where, indexes, bucket
SIMPLE = [
    ("codes", "CODES", ["CODE_TYPE", "CODE_VAL"], ["code_type", "code_val"],
     [{"keys": {"code_type": 1, "code_val": 1}, "unique": True, "why": "PK_CODES; report status labels"}]),
    ("tenants", "TENANTS", ["ID"], ["_id"],
     [{"keys": {"name": 1}, "unique": True, "why": "UQ_TENANTS_NAME"}]),
    ("plans", "PLANS", ["ID"], ["_id"],
     [{"keys": {"code": 1}, "unique": True, "why": "UQ_PLANS_CODE; plan-change by code"}]),
    ("subscriptions", "SUBSCRIPTIONS", ["ID"], ["_id"],
     [{"keys": {"tenant_id": 1, "starts_on": -1}, "why": "latest covering subscription (PKG_PLANS/RATING/INVOICING)"}]),
    ("subscriptions_hist", "SUBSCRIPTIONS_HIST", ["HIST_ID"], ["_id"],
     [{"keys": {"id": 1, "hist_dt": 1}, "why": "history by subscription"}]),
    ("usage_events", "USAGE_EVENTS", ["ID"], ["_id"],
     [{"keys": {"tenant_id": 1, "occurred_at": 1}, "why": "PKG_RATING usage by tenant and window"}]),
    ("rating_periods", "RATING_PERIODS", ["ID"], ["_id"],
     [{"keys": {"tenant_id": 1, "period_start": 1}, "unique": True, "why": "UQ_RATING_PERIODS; upsert target"}]),
    ("rating_results", "RATING_RESULTS", ["ID"], ["_id"],
     [{"keys": {"period_id": 1, "subscription_id": 1}, "why": "PKG_RATING upsert by period+subscription"}]),
    ("credit_notes", "CREDIT_NOTES", ["ID"], ["_id"],
     [{"keys": {"tenant_id": 1, "issued_on": 1}, "why": "PKG_INVOICING open credits in issue order"}]),
    ("dunning_attempts", "DUNNING_ATTEMPTS", ["ID"], ["_id"],
     [{"keys": {"invoice_id": 1, "attempt_no": 1}, "unique": True, "why": "UQ_DUNNING_ATTEMPTS"}]),
    ("notifications", "NOTIFICATIONS", ["ID"], ["_id"],
     [{"keys": {"tenant_id": 1, "kind_cd": 1, "sent_at": 1}, "unique": True, "why": "UQ_NOTIFICATIONS; suspend-notice dedupe"}]),
    ("billing_audit_log", "BILLING_AUDIT_LOG", ["LOG_ID"], ["_id"], []),
]


def columns():
    census = json.loads(CENSUS.read_text())
    out = OrderedDict()
    for c in census["columns"]:
        out.setdefault(c["table_name"], []).append(c)
    return out


def source_type(c):
    t = c["data_type"]
    if t == "NUMBER":
        return f"NUMBER({c['data_precision']},{c['data_scale']})"
    if t in ("VARCHAR2", "CHAR"):
        return f"{t}({c['data_length']})"
    return t


def field(c):
    t, nullable = c["data_type"], c["nullable"] == "Y"
    if t == "VARCHAR2":
        bson, rules = "string", ["empty_string_is_null"]
    elif t == "CHAR":
        bson, rules = "string", ["rstrip_spaces", "empty_string_is_null"]
    elif t == "NUMBER" and (c["data_scale"] or 0) > 0:
        bson, rules = "decimal", ["decimal_round"]
    elif t == "NUMBER":
        bson, rules = ("int" if (c["data_precision"] or 38) <= 9 else "long"), []
    elif t == "DATE" or t.startswith("TIMESTAMP"):
        bson, rules = "date", ["datetime_utc_truncate_ms"]
    else:
        raise SystemExit(f"unmapped type {t} on {c['table_name']}.{c['column_name']}")
    if nullable:
        rules = rules + ["null_missing_equiv"]
    return {"source": c["column_name"], "target": c["column_name"].lower(),
            "source_type": source_type(c), "bson_type": bson, "rules": rules}


def fields(cols, exclude=()):
    return [field(c) for c in cols if c["column_name"] not in exclude]


def main():
    cols = columns()
    spec = OrderedDict(version=VERSION, source_family="oracle", target_db="ow_tp_mmp_live",
                       collections=[], canonicalization=CANON)
    coll = spec["collections"]
    coll.append({
        "collection": "customers", "root_table": "CUSTOMER_MASTER", "unit": "U1-customers",
        "key": {"source": ["CUST_ID"], "target": "_id"},
        "fields": fields(cols["CUSTOMER_MASTER"], {"CUST_ID"}),
        "embeds": [{
            "array_path": "attributes", "shape": "array", "child_table": "ENTITY_ATTR_VALUE",
            "child_where": "entity_type = 'CUSTOMER'", "target_where": "{}",
            "parent_key": ["ENTITY_ID"], "parent_ref": ["CUST_ID"],
            "key": {"source": ["EAV_ID"], "target": "eav_id"},
            "fields": fields(cols["ENTITY_ATTR_VALUE"], {"EAV_ID", "ENTITY_TYPE", "ENTITY_ID"}),
            "order_by": ["eav_id"], "cardinality": "1:N bounded", "max_observed": 5,
            "duplicates": "kept: one element per EAV row (187 duplicate-name groups, 379 rows)",
        }],
        "indexes": [
            {"keys": {"tenant_id": 1, "cust_seq_no": 1}, "why": "GET /customer: first customer of tenant by cust_seq_no"},
            {"keys": {"conversion_batch_no": 1}, "why": "balances report filters on batch"},
        ],
        "render": {"all_columns": True, "omitted_as_null": True,
                   "attributes_add": {"entity_type": "CUSTOMER", "entity_id": "$_id"}},
    })
    coll.append({
        "collection": "invoices", "root_table": "INVOICE_HEADER", "unit": "U2-invoices",
        "key": {"source": ["INVOICE_ID"], "target": "_id"},
        "fields": fields(cols["INVOICE_HEADER"], {"INVOICE_ID"}),
        "embeds": [{
            "array_path": "lines", "shape": "array", "child_table": "INVOICE_LINE",
            "child_where": LINE_HAS_HEADER, "target_where": "{}",
            "parent_key": ["INVOICE_ID"], "parent_ref": ["INVOICE_ID"],
            "key": {"source": ["LINE_ID"], "target": "line_id"},
            "fields": fields(cols["INVOICE_LINE"], {"LINE_ID"} | LINE_PARENT_COLUMNS),
            "order_by": ["line_no", "line_id"], "cardinality": "1:N bounded", "max_observed": 23,
            "parent_columns_dropped": sorted(LINE_PARENT_COLUMNS),
        }],
        "indexes": [
            {"keys": {"batch_no": 1, "status_cd": 1}, "why": "month-end report by batch and status"},
            {"keys": {"cust_id": 1}, "why": "invoices of a customer"},
        ],
    })
    coll.append({
        "collection": "quarantine_invoice_line", "root_table": "INVOICE_LINE", "unit": "U2-invoices",
        "root_where": LINE_ORPHAN, "target_where": "{}",
        "key": {"source": ["LINE_ID"], "target": "_id"},
        "fields": fields(cols["INVOICE_LINE"], {"LINE_ID"}),
        "quarantine": {"reason": "orphan_invoice_id", "expected_rows": 37,
                       "added_fields": ["quarantine_reason", "source_table"]},
        "indexes": [{"keys": {"invoice_id": 1}, "why": "orphan triage by missing invoice"}],
    })
    coll.append({
        "collection": "billing_invoices", "root_table": "INVOICES", "unit": "U3-billing-core",
        "key": {"source": ["ID"], "target": "_id"},
        "fields": fields(cols["INVOICES"], {"ID"}),
        "embeds": [{
            "array_path": "lines", "shape": "array", "child_table": "INVOICE_LINES",
            "parent_key": ["INVOICE_ID"], "parent_ref": ["ID"],
            "key": {"source": ["ID"], "target": "id"},
            "fields": fields(cols["INVOICE_LINES"], {"ID", "INVOICE_ID"}),
            "order_by": ["line_no"], "cardinality": "1:N bounded", "max_observed": 2,
        }],
        "indexes": [
            {"keys": {"tenant_id": 1, "issued_at": -1}, "why": "GET /invoices for a tenant"},
            {"keys": {"status_cd": 1, "issued_at": 1}, "why": "overdue / dunning scan in issue order"},
        ],
    })
    for name, table, ksrc, ktgt, indexes in SIMPLE:
        exclude = set(ksrc) if ktgt == ["_id"] else set()
        coll.append({
            "collection": name, "root_table": table, "unit": "U3-billing-core",
            "key": {"source": ksrc, "target": ktgt if len(ktgt) > 1 else ktgt[0]},
            "fields": fields(cols[table], exclude),
            "indexes": indexes,
            **({"id_format": "<code_type>:<code_val>"} if len(ksrc) > 1 else {}),
        })
    spec["excluded"] = [
        {"table": "CUSTOMER_MASTER_HIST", "bucket": "proposed-unused",
         "evidence": "0 rows; only writer is TRG_CUSTOMER_MASTER_HIST; no app path updates or deletes CUSTOMER_MASTER"},
        {"table": "FIXTURE_META", "bucket": "excluded",
         "evidence": "demo seeder bookkeeping (schema/04_upgrade_static.sql); not billing data; no app reader"},
    ]
    spec["app_support"] = [
        {"collection": "sequences", "unit": "U3-billing-core",
         "why": "replaces SEQ_BILLING_AUDIT_LOG / SEQ_SUBSCRIPTIONS_HIST for ids the Mongo backend mints; seeded from DBA_SEQUENCES.last_number",
         "graded": False},
    ]
    spec["load"] = {
        "method": "one read-only Oracle pass per unit; pymongo bulk ReplaceOne(upsert) by _id, then delete target docs whose _id is not in the loaded key set",
        "idempotent": True,
        "embed_order": "arrays written in order_by order; ties impossible (order_by ends in the element key)",
        "nulls": "NULL and '' are omitted from documents (tolerances v1: null == missing == '')",
        "text_columns": "VARCHAR2/CHAR values are stored verbatim (CHAR right-trimmed); text dates, Y/N flags and CSV lists are not re-typed",
    }
    for c in coll:
        c["root_table"] = f"{SOURCE_SCHEMA}.{c['root_table']}"
        for e in c.get("embeds", []):
            e["child_table"] = f"{SOURCE_SCHEMA}.{e['child_table']}"
    OUT.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"{OUT}: {len(coll)} collections, "
          f"{sum(len(c['fields']) for c in coll)} root fields, "
          f"{sum(len(e['fields']) for c in coll for e in c.get('embeds', []))} embedded fields")


if __name__ == "__main__":
    main()
