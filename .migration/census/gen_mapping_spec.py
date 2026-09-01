#!/usr/bin/env python3
"""Generate .migration/03_mapping_spec.json from the census column inventory.

Deterministic, review-audited rules (lead-authored):
- target field name = lowercase(source column); root key column maps to `_id`.
- Oracle type -> BSON type per the oracle profile + STOP-A-approved tolerances v1.0:
    NUMBER(p,0) p<=9  -> int
    NUMBER(p,0) p<=18 -> long
    NUMBER scaled or unbounded -> decimal (Decimal128), half-even canonicalization
    VARCHAR2 -> string  [empty_string_is_null]
    CHAR     -> string  [rstrip_spaces, empty_string_is_null]
    DATE / TIMESTAMP(6) -> date [datetime_utc_truncate_ms]
- VARCHAR2 columns that hold formatted dates (e.g. INVOICE_DT, HIST_DT, CREATED_DT)
  migrate verbatim as strings in v1 (parity-first; typed-date normalization is a
  recorded backlog item, not part of this migration's contract).
NULL and missing stay distinct: null_missing_equiv is intentionally NOT applied,
EXCEPT the v1.1 amendment (approved 2026-09-01, 05_decisions.md): 19 NULL-bearing numeric
CUSTOMER_MASTER columns carry null_missing_equiv solely to defer their Tier-2 native
aggregates (Oracle excludes NULLs; Mongo counts the null group) to the Tier-3 keyed diff;
the 17 all-NULL columns among them also drop the bson_type assertion (SUM of all-NULL is
Oracle NULL vs Mongo 0). Loaded data is unchanged: source NULL -> explicit BSON null.
v1.2 amendment (approved 2026-09-01, 05_decisions.md): same Tier-2 deferral for the two
all-NULL DATE columns SUBSCRIPTIONS.ENDS_ON and SUBSCRIPTIONS.SUSPENDED_ON
(COUNT(DISTINCT)=0 in Oracle vs the Mongo null group). Grading-only; bson_type stays date.
"""
import json
import re
from pathlib import Path

RAW = Path(__file__).parent / "raw" / "columns.txt"
OUT = Path(__file__).parent.parent / "03_mapping_spec.json"

def parse_columns():
    cols = {}  # table -> [(col, dtype, precision, scale)]
    for line in RAW.read_text().splitlines():
        t = line.split()
        if len(t) < 3:
            continue
        table, col, dtype = t[0], t[1], t[2]
        rest = t[3:]
        p = s = None
        if dtype == "NUMBER":
            if rest and re.fullmatch(r"\d+", rest[0]):
                p = int(rest[0])
                if len(rest) > 1 and re.fullmatch(r"\d+", rest[1]):
                    s = int(rest[1])
        cols.setdefault(table, []).append((col, dtype, p, s))
    return cols

def bson_and_rules(dtype, p, s):
    if dtype == "NUMBER":
        if s == 0 and p is not None:
            return ("int" if p <= 9 else "long" if p <= 18 else "decimal",
                    [] if p <= 18 else ["decimal_round"])
        return "decimal", ["decimal_round"]
    if dtype == "VARCHAR2":
        return "string", ["empty_string_is_null"]
    if dtype == "CHAR":
        return "string", ["rstrip_spaces", "empty_string_is_null"]
    if dtype == "DATE" or dtype.startswith("TIMESTAMP"):
        return "date", ["datetime_utc_truncate_ms"]
    raise ValueError(f"unmapped Oracle type {dtype}")

# v1.1 amendment: CUSTOMER_MASTER columns whose Tier-2 aggregates are deferred to Tier 3.
AGG_DEFERRED = {
    "CHANNEL_CD", "CREDIT_LIMIT_AMT", "LTD_BILLED_AMT", "PHONE3_TYPE_CD",
    "PHONE4_TYPE_CD", "RATE_CLASS_CD", "SUB_STATUS_CD", "TERRITORY_CD",
    "UDF_AMT_01", "UDF_AMT_02", "UDF_AMT_03", "UDF_AMT_04", "UDF_AMT_05",
    "UDF_AMT_06", "UDF_AMT_07", "UDF_AMT_08", "UDF_AMT_09", "UDF_AMT_10",
    "YTD_PAID_AMT",
}
# The all-NULL subset also drops the bson_type assertion so Tier 2 skips SUM.
ALL_NULL = AGG_DEFERRED - {"SUB_STATUS_CD", "CREDIT_LIMIT_AMT"}

# v1.2 amendment: SUBSCRIPTIONS all-NULL DATE columns, same Tier-2 deferral (no SUM on dates).
SUBS_AGG_DEFERRED = {"ENDS_ON", "SUSPENDED_ON"}

def fields(cols, table, exclude=()):
    out = []
    for col, dtype, p, s in cols[table]:
        if col in exclude:
            continue
        bson, rules = bson_and_rules(dtype, p, s)
        if table == "CUSTOMER_MASTER" and col in AGG_DEFERRED:
            rules = rules + ["null_missing_equiv"]
            if col in ALL_NULL:
                bson = ""
        if table == "SUBSCRIPTIONS" and col in SUBS_AGG_DEFERRED:
            rules = rules + ["null_missing_equiv"]
        out.append({"source": col, "target": col.lower(),
                    "source_type": dtype if p is None else f"{dtype}({p},{s})",
                    "bson_type": bson, "rules": rules})
    return out

# (collection, root_table, key_col, root_where, embeds)
DESIGN = [
    ("tenants", "TENANTS", "ID", None, []),
    ("plans", "PLANS", "ID", None, []),
    ("codes", "CODES", "CODE_TYPE || '#' || CODE_VAL", None, []),
    ("customers", "CUSTOMER_MASTER", "CUST_ID", None, [
        {"array_path": "attributes", "child_table": "ENTITY_ATTR_VALUE",
         "child_where": "ENTITY_TYPE = 'CUSTOMER'",
         "parent_key": ["ENTITY_ID"],
         "key": {"source": ["EAV_ID"], "target": "eav_id"},
         "exclude": ["ENTITY_TYPE", "ENTITY_ID"]},
    ]),
    ("customer_master_hist", "CUSTOMER_MASTER_HIST", "HIST_ID", None, []),
    ("invoice_feed", "INVOICE_HEADER", "INVOICE_ID", None, [
        {"array_path": "lines", "child_table": "INVOICE_LINE",
         "child_where": ("EXISTS (SELECT 1 FROM invoice_header h "
                         "WHERE h.invoice_id = invoice_line.invoice_id)"),
         "parent_key": ["INVOICE_ID"],
         "key": {"source": ["LINE_ID"], "target": "line_id"},
         "exclude": ["INVOICE_ID"]},
    ]),
    ("subscriptions", "SUBSCRIPTIONS", "ID", None, []),
    ("subscriptions_hist", "SUBSCRIPTIONS_HIST", "HIST_ID", None, []),
    ("usage_events", "USAGE_EVENTS", "ID", None, []),
    ("rating_periods", "RATING_PERIODS", "ID", None, []),
    ("rating_results", "RATING_RESULTS", "ID", None, []),
    ("invoices", "INVOICES", "ID", None, [
        {"array_path": "lines", "child_table": "INVOICE_LINES",
         "child_where": None, "parent_key": ["INVOICE_ID"],
         "key": {"source": ["LINE_NO"], "target": "line_no"},
         "exclude": ["INVOICE_ID"]},
        {"array_path": "dunning_attempts", "child_table": "DUNNING_ATTEMPTS",
         "child_where": None, "parent_key": ["INVOICE_ID"],
         "key": {"source": ["ATTEMPT_NO"], "target": "attempt_no"},
         "exclude": ["INVOICE_ID"]},
    ]),
    ("credit_notes", "CREDIT_NOTES", "ID", None, []),
    ("notifications", "NOTIFICATIONS", "ID", None, []),
    ("billing_audit_log", "BILLING_AUDIT_LOG", "LOG_ID", None, []),
    ("fixture_meta", "FIXTURE_META", "INITIALIZED_AT", None, []),
]

def main():
    cols = parse_columns()
    collections = []
    for name, root, key_col, where, embeds in DESIGN:
        c = {
            "collection": name,
            "root_table": root,
            "key": {"source": [key_col], "target": "_id"},
            "fields": fields(cols, root, exclude=(key_col,)),
        }
        if where:
            c["root_where"] = where
        if name == "fixture_meta":
            c["parity"] = "count_only"
            c["declared_unexercised"] = ["INITIALIZED_AT"]
        es = []
        for e in embeds:
            key_srcs = e["key"]["source"]
            excl = tuple(e["exclude"]) + tuple(key_srcs)
            em = {
                "array_path": e["array_path"],
                "child_table": e["child_table"],
                "parent_key": e["parent_key"],
                "key": e["key"],
                "fields": fields(cols, e["child_table"],
                                 exclude=excl + tuple(e["parent_key"])),
            }
            if e["child_where"]:
                em["child_where"] = e["child_where"]
            es.append(em)
        if es:
            c["embeds"] = es
        collections.append(c)
    spec = {"version": "1.2", "collections": collections}
    OUT.write_text(json.dumps(spec, indent=2) + "\n")
    n_fields = sum(len(c["fields"]) for c in collections)
    n_embed_fields = sum(len(e["fields"]) for c in collections for e in c.get("embeds", []))
    print(f"wrote {OUT}: {len(collections)} collections, "
          f"{n_fields} root fields, {n_embed_fields} embedded fields")

if __name__ == "__main__":
    main()
