"""Generate .migration/03_mapping_spec.json from census/discovery.json + the Oracle profile type table.

Model decisions (embed/reference, keys) are declared in MODEL below; field lists and BSON types
are derived from the catalog so all 434 columns are graded. Re-run after any census change.
"""
import json, re, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
d = json.load(open(ROOT / ".migration/census/discovery.json"))
cols = {}
for t, c, ty, p, s, n, cu in d["columns"]["rows"]:
    cols.setdefault(t, []).append((c, ty, int(p) if p else None, int(s) if s else None, n == "Y"))


def camel(c):
    parts = c.lower().split("_")
    return parts[0] + "".join(x.title() for x in parts[1:])


def bson(ty, p, s):
    if ty.startswith("NUMBER"):
        if p is None:
            return "decimal", "NUMBER"
        if (s or 0) == 0 and p <= 18:
            return ("int" if p <= 9 else "long"), f"NUMBER({p},0)"
        return "decimal", f"NUMBER({p},{s})"
    if ty in ("VARCHAR2", "NVARCHAR2", "CHAR", "CLOB"):
        return "string", ty
    if ty == "DATE" or ty.startswith("TIMESTAMP"):
        return "date", ty
    if ty in ("BLOB", "RAW"):
        return "binData", ty
    if ty in ("FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE"):
        return "double", ty
    raise SystemExit(f"unmapped type {ty}")


def field(t, c, ty, p, s, nullable):
    b, st = bson(ty, p, s)
    rules = []
    if ty == "CHAR":
        rules.append("rstrip_spaces")
        if c.endswith("_YN"):
            b = "bool"; rules.append("yn_to_bool")
    if b == "string" and ty != "CHAR":
        rules.append("empty_string_is_null")
    if b == "date":
        rules.append("datetime_utc_truncate_ms")
    if b == "decimal":
        rules.append("decimal_round")
    if nullable:
        rules.append("null_missing_equiv")
    f = {"source": c, "target": camel(c), "source_type": st, "bson_type": b, "rules": rules}
    # Traps kept as-is in v1 (see 05_decisions / STOP B): *_DT text dates and *_CSV/*_IDS lists
    # stay strings because the seed plants unparseable values (50 dirty dates, 31 malformed CSVs).
    if ty == "VARCHAR2" and (c.endswith("_DT") or c.endswith("_CSV") or c.endswith("_IDS")):
        f["note"] = "trap column kept as string in v1 (PROPOSED conversion after cutover)"
    return f


def fields(t, exclude=()):
    return [field(t, *c) for c in cols[t] if c[0] not in exclude]


def coll(name, table, key_src, key_tgt="_id", embeds=None, root_where=None, target_where=None, **extra):
    c = {"collection": name, "root_table": "OW_BILLING." + table,  # schema-qualified: ow_billing_ro has no synonyms
         "key": {"source": key_src, "target": key_tgt},
         "fields": fields(table), "cardinality": f"docs = count({table}{' WHERE ' + root_where if root_where else ''})"}
    if root_where:
        c["root_where"] = root_where
        c["target_where"] = target_where
    if embeds:
        c["embeds"] = embeds
    c.update(extra)
    return c


def embed(path, child, parent_key, key_src, key_tgt, cardinality, child_where=None, **extra):
    e = {"array_path": path, "shape": "array", "child_table": "OW_BILLING." + child, "parent_key": parent_key,
         "key": {"source": key_src, "target": key_tgt}, "fields": fields(child), "cardinality": cardinality}
    if child_where:
        e["child_where"] = child_where
        e.setdefault("target_where", "{}")  # harness scopes both sides or neither; all loaded elems are in scope
    e.update(extra)
    return e


HAS_HDR = "EXISTS (SELECT 1 FROM OW_BILLING.INVOICE_HEADER h WHERE h.INVOICE_ID = INVOICE_LINE.INVOICE_ID)"
ORPHAN = "NOT " + HAS_HDR

MODEL = [
    # wave 0: shared / reference
    coll("codes", "CODES", ["CODE_TYPE", "CODE_VAL"], ["codeType", "codeVal"], unit="shared-reference", wave=0,
         access_pattern="facade.py:114,215,245,342,394 LEFT JOIN codes on (code_type, code_val); read-only lookup"),
    coll("tenants", "TENANTS", ["ID"], unit="shared-reference", wave=0,
         access_pattern="facade.py:113 tenant list; backends/oracle.py:136,141 ensure-tenant; FK target of 8 tables"),
    coll("plans", "PLANS", ["ID"], unit="shared-reference", wave=0,
         access_pattern="pkg_plans.fn_list_plans; backends/oracle.py:150; 3 rows, referenced by subscriptions"),
    # wave 1
    coll("customers", "CUSTOMER_MASTER", ["CUST_ID"], unit="customers", wave=1, size_class="XL (155 columns)",
         access_pattern="facade.py:287-297 reads customer_master then entity_attr_value for the same cust_id in one request -> embed attributes",
         embeds=[embed("attributes", "ENTITY_ATTR_VALUE", ["ENTITY_ID"], ["EAV_ID"], "eavId",
                       "sum(attributes[].length) = count(ENTITY_ATTR_VALUE WHERE ENTITY_TYPE='CUSTOMER') = 8337; element key EAV_ID because (ENTITY_ID, ATTR_NAME) repeats 181 times",
                       )]),  # unscoped: census shows every ENTITY_ATTR_VALUE row is ENTITY_TYPE='CUSTOMER'; a scoped embed can never be merge-eligible in the harness
    coll("invoice_headers", "INVOICE_HEADER", ["INVOICE_ID"], unit="invoice_batch", wave=1,
         access_pattern="reports.py:46-67 header x line aggregates by batch_no; lines referenced via invoice_lines.invoiceId (halt fix A: harness zeroes merge_eligible on any where-scoped embed, and 37 orphans forbid an unscoped one)"),
    coll("invoice_lines", "INVOICE_LINE", ["LINE_ID"], unit="invoice_batch", wave=1,
         access_pattern="all 150000 INVOICE_LINE rows as a referenced root collection; orphan:true flag (derived, ungraded) on the 37 rows without an INVOICE_HEADER; reports join by invoiceId via $lookup",
         derived_fields=[{"target": "orphan", "bson_type": "bool", "rule": "NOT EXISTS INVOICE_HEADER for INVOICE_ID", "graded": False}]),
    coll("subscriptions", "SUBSCRIPTIONS", ["ID"], unit="subscriptions_rating", wave=1,
         access_pattern="pkg_plans.fn_entitlement/sp_change_plan; backends/oracle.py:68,161; RATING_RESULTS references subscription_id"),
    coll("usage_events", "USAGE_EVENTS", ["ID"], unit="subscriptions_rating", wave=1,
         access_pattern="facade.py:214 paged list by tenant; facade.py:401 insert; pkg_rating aggregates by tenant+period -> reference (append-only, unbounded)"),
    coll("rating_periods", "RATING_PERIODS", ["ID"], unit="subscriptions_rating", wave=1,
         access_pattern="pkg_rating.sp_finalize_rating writes period+results together; facade.py:244 join invoices->rating_periods -> embed results",
         embeds=[embed("results", "RATING_RESULTS", ["PERIOD_ID"], ["ID"], "id",
                       "sum(results[].length) = count(RATING_RESULTS) = 3")]),
    coll("invoices", "INVOICES", ["ID"], unit="invoicing", wave=1,
         access_pattern="pkg_invoicing.fn_invoice_lines(invoice_id); facade.py:243; UQ(invoice_id,line_no) -> embed lines",
         embeds=[embed("lines", "INVOICE_LINES", ["INVOICE_ID"], ["ID"], "id",
                       "sum(lines[].length) = count(INVOICE_LINES) = 4")]),
    coll("credit_notes", "CREDIT_NOTES", ["ID"], unit="invoicing", wave=1,
         access_pattern="pkg_invoicing.compute_preview consumes remaining_amount per tenant -> reference"),
    coll("dunning_attempts", "DUNNING_ATTEMPTS", ["ID"], unit="dunning", wave=1,
         access_pattern="facade.py:341 paged list; pkg_dunning.sp_schedule_dunning inserts; UQ(invoice_id, attempt_no) -> unique index"),
    coll("notifications", "NOTIFICATIONS", ["ID"], unit="dunning", wave=1,
         access_pattern="pkg_dunning.sp_suspend_overdue inserts; UQ(tenant_id, kind_cd, sent_at) -> unique index"),
]

spec = {
    "version": "1.1.0",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "generator": ".migration/census/gen_mapping.py over .migration/census/discovery.json",
    "source": {"family": "oracle", "schema": "OW_BILLING"},
    "target": {"database": "mmp_rt_billing"},
    "collections": MODEL,
    "canonicalization": {"rules": [
        {"rule": "decimal_round", "applies_to": "NUMBER->Decimal128", "params": {"mode": "half_even"}},
        {"rule": "datetime_utc_truncate_ms", "applies_to": "DATE,TIMESTAMP*->date", "params": {"precision": "ms"}},
        {"rule": "rstrip_spaces", "applies_to": "CHAR->string", "params": {}},
        {"rule": "empty_string_is_null", "applies_to": "VARCHAR2,NVARCHAR2,CHAR->string", "params": {"target_policy": "missing"}},
        {"rule": "null_missing_equiv", "applies_to": "*", "params": {"policy": "null_missing_equiv"}},
        {"rule": "yn_to_bool", "applies_to": "CHAR(1) *_YN->bool", "params": {}},
    ]},
    "key_strategy": {
        "VARCHAR2 ids": "natural key copied to _id (app-generated UUIDs; pkg_ow_util.f_md5_uuid)",
        "CODES": "composite _id {codeType, codeVal}",
        "seq_customer_master / seq_entity_attr_value / seq_billing_audit_log / seq_subscriptions_hist": "surrogate numbers copied as long; new inserts after cutover use a counters collection (PROPOSED)",
    },
    "index_plan": {
        "customers": ["{tenantId:1, custSeqNo:1}", "{custNo:1}"],
        "invoice_headers": ["{batchNo:1, statusCd:1}", "{custId:1}", "{tenantId:1}"],
        "invoice_lines": ["{invoiceId:1, lineNo:1}", "{orphan:1}"],
        "usage_events": ["{tenantId:1, occurredAt:-1}"],
        "rating_periods": ["{tenantId:1, periodStart:1} unique"],
        "dunning_attempts": ["{invoiceId:1, attemptNo:1} unique", "{tenantId:1, scheduledFor:-1}"],
        "notifications": ["{tenantId:1, kindCd:1, sentAt:1} unique"],
        "plans": ["{code:1} unique"], "tenants": ["{name:1} unique"],
    },
}
out = ROOT / ".migration/03_mapping_spec.json"
out.write_text(json.dumps(spec, indent=1) + "\n")
n = sum(len(c["fields"]) + sum(len(e["fields"]) for e in c.get("embeds", [])) for c in MODEL)
print(f"wrote {out} collections={len(MODEL)} graded_fields={n}")
