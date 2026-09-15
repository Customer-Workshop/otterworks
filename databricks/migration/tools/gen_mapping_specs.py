#!/usr/bin/env python3
"""Generate candidate recon mapping specs for the pipeline-1 data units.

Reads the OW_BILLING DDL in services/legacy-billing/db/oracle/schema/ and writes one
.migration/units/<unit_id>/mapping_spec.json per data unit, applying the field/type
dictionary in docs/migration/Pipeline1_invoicing_analysis.md section 3.

The output is a candidate: the unit's child owns it from wave start and may add rules,
predicates or delete evidence. Regenerating is idempotent. Run from the repo root:

    python3 databricks/migration/tools/gen_mapping_specs.py [--check]

--check exits non-zero if the committed specs differ from what the DDL implies, so a
schema change that nobody folded into the mappings is visible in CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "services/legacy-billing/db/oracle/schema"
UNITS = ROOT / ".migration/units"
SOURCE_SCHEMA = "OW_BILLING"

# unit_id -> (source table, target table, comparison key, watermark, identity, track)
# track: lakebase (operational) | delta (analytical). Watermark None = graded strictly.
UNITS_SPEC = {
    "p1-tenants":              ("tenants", "tenants", ["id"], None, None, "lakebase"),
    "p1-plans":                ("plans", "plans", ["id"], None, None, "lakebase"),
    "p1-subscriptions":        ("subscriptions", "subscriptions", ["id"], None, None, "lakebase"),
    "p1-rating-periods":       ("rating_periods", "rating_periods", ["id"], None, None, "lakebase"),
    "p1-rating-results":       ("rating_results", "rating_results", ["id"], ("created_at", None), None, "lakebase"),
    "p1-invoices":             ("invoices", "invoices", ["id"], ("issued_at", None), None, "lakebase"),
    "p1-invoice-lines":        ("invoice_lines", "invoice_lines", ["id"], None, None, "lakebase"),
    "p1-credit-notes":         ("credit_notes", "credit_notes", ["id"], ("issued_on", None), None, "lakebase"),
    "p1-dunning-attempts":     ("dunning_attempts", "dunning_attempts", ["id"], None, None, "lakebase"),
    "p1-notifications":        ("notifications", "notifications", ["id"], ("sent_at", None), None, "lakebase"),
    "p1-codes":                ("codes", "codes", ["code_type", "code_val"], None, None, "lakebase"),
    "p1-customer-master":      ("customer_master", "customer_master", ["cust_id"], ("updated_dt", None), "cust_seq_no", "lakebase"),
    "p1-entity-attr-value":    ("entity_attr_value", "entity_attr_value", ["eav_id"], None, "eav_id", "lakebase"),
    "p1-customer-master-hist": ("customer_master_hist", "customer_master_hist", ["hist_id"], None, "hist_id", "delta"),
    "p1-subscriptions-hist":   ("subscriptions_hist", "subscriptions_hist", ["hist_id"], None, "hist_id", "delta"),
    "p1-invoice-header":       ("invoice_header", "invoice_header", ["invoice_id"], None, None, "delta"),
    "p1-invoice-line":         ("invoice_line", "invoice_line", ["line_id"], None, None, "delta"),
    "p1-usage-events":         ("usage_events", "usage_events", ["id"], ("occurred_at", None), None, "delta"),
    "p1-billing-audit-log":    ("billing_audit_log", "billing_audit_log", ["log_id"], ("logged_at", None), "log_id", "delta"),
}

# Code, orchestration and transport units. A package or job is reconciled by the rows it
# writes (tiers 1-3 over those tables) plus a Tier-4 op diff over its read-only entrypoints,
# so its mapping names the tables it mutates. Those tables are ALSO owned as data units by a
# different child: a mapping is not a write target, and the unit ids stay disjoint.
# unit_id -> ([(source table, key, track)], [(op name, source sql, target sql)])
FED = "ow_billing_fed.ow_billing"  # Lakehouse Federation catalog.schema, created in wave 0

CODE_UNITS: dict[str, tuple[list[tuple[str, list[str], str]], list[tuple[str, str, str]]]] = {
    "p1-pkg-ow-util": (
        [("billing_audit_log", ["log_id"], "delta")],
        [("f_md5_uuid_vector",
          f"SELECT v AS input, f_md5_uuid(v) AS id FROM {FED}.fixture_md5_vector ORDER BY v",
          "SELECT input AS input, billing.f_md5_uuid(input) AS id FROM billing.fixture_md5_vector ORDER BY input"),
         ("f_str2dt_vector",
          f"SELECT v AS input, f_str2dt(v) AS dt FROM {FED}.fixture_date_vector ORDER BY v",
          "SELECT input AS input, billing.f_str2dt(input) AS dt FROM billing.fixture_date_vector ORDER BY input"),
         ("f_code_desc_all",
          f"SELECT code_type, code_val, f_code_desc(code_type, code_val) AS d FROM {FED}.codes ORDER BY code_type, code_val",
          "SELECT code_type, code_val, billing.f_code_desc(code_type, code_val) AS d FROM billing.codes ORDER BY code_type, code_val")]),
    "p1-pkg-plans": (
        [("subscriptions", ["id"], "lakebase")],
        [("fn_plan_entitlements_all_tenants",
          f"SELECT tenant_id, plan_id, entitlement, qty FROM {FED}.v_plan_entitlements_all ORDER BY tenant_id, entitlement",
          "SELECT tenant_id, plan_id, entitlement, qty FROM billing.fn_plan_entitlements_all() ORDER BY tenant_id, entitlement")]),
    "p1-pkg-rating": (
        [("rating_periods", ["id"], "lakebase"), ("rating_results", ["id"], "lakebase")],
        [("fn_usage_rating_all",
          f"SELECT * FROM {FED}.v_usage_rating_all ORDER BY tenant_id, period_id",
          "SELECT * FROM billing.fn_usage_rating_all() ORDER BY tenant_id, period_id"),
         ("fn_usage_summary_all",
          f"SELECT * FROM {FED}.v_usage_summary_all ORDER BY tenant_id, kind",
          "SELECT * FROM billing.fn_usage_summary_all() ORDER BY tenant_id, kind")]),
    "p1-pkg-invoicing": (
        [("invoices", ["id"], "lakebase"), ("invoice_lines", ["id"], "lakebase")],
        [("fn_invoice_preview_all",
          f"SELECT * FROM {FED}.v_invoice_preview_all ORDER BY tenant_id",
          "SELECT * FROM billing.fn_invoice_preview_all() ORDER BY tenant_id"),
         ("fn_invoice_lines_all",
          f"SELECT * FROM {FED}.v_invoice_lines_all ORDER BY invoice_id, line_no",
          "SELECT * FROM billing.fn_invoice_lines_all() ORDER BY invoice_id, line_no")]),
    "p1-pkg-dunning": (
        [("dunning_attempts", ["id"], "lakebase"), ("notifications", ["id"], "lakebase")],
        [("fn_overdue_accounts",
          f"SELECT * FROM {FED}.v_overdue_accounts ORDER BY issued_at, id",
          "SELECT * FROM billing.fn_overdue_accounts() ORDER BY issued_at, id")]),
    "p1-job-nightly-dunning": ([("dunning_attempts", ["id"], "lakebase")], []),
    "p1-job-purge-audit-log": ([("billing_audit_log", ["log_id"], "delta")], []),
    "p1-cdc-transport": (
        [("customer_master", ["cust_id"], "delta"), ("invoice_header", ["invoice_id"], "delta"),
         ("invoice_line", ["line_id"], "delta")], []),
}

CREATE_RE = re.compile(r"CREATE TABLE (\w+) \((.*?)\n\);", re.S)
COL_RE = re.compile(r"^\s{4}(\w+)\s+([A-Z0-9_]+(?:\([\d,\s]+\))?)", re.M)


def parse_tables() -> dict[str, list[tuple[str, str]]]:
    tables: dict[str, list[tuple[str, str]]] = {}
    for f in ("01_tables.sql", "02_horror.sql"):
        text = (SCHEMA / f).read_text()
        for name, body in CREATE_RE.findall(text):
            cols = [(c, t.replace(" ", "")) for c, t in COL_RE.findall(body)
                    if c.upper() not in ("CONSTRAINT",)]
            tables[name.lower()] = cols
    return tables


def target_types(col: str, otype: str, track: str) -> tuple[str, str, list[str]]:
    """Oracle type -> (lakebase type, delta type, canonicalization rules)."""
    m = re.match(r"(\w+)(?:\((\d+)(?:,(\d+))?\))?", otype)
    base, p, s = m.group(1), m.group(2), m.group(3)
    if base == "NUMBER" and s:
        lb, dl, rules = f"numeric({p},{s})", f"DECIMAL({p},{s})", ["decimal_round"]
    elif base == "NUMBER":
        width = int(p or 38)
        lb = "smallint" if width <= 4 else ("integer" if width <= 9 else "bigint")
        dl = "SMALLINT" if width <= 4 else ("INT" if width <= 9 else "BIGINT")
        rules = []
    elif base == "CHAR":
        lb, dl, rules = f"char({p})", "STRING", ["rstrip_spaces", "empty_string_is_null"]
    elif base == "VARCHAR2":
        lb, dl, rules = f"varchar({p})", "STRING", ["rstrip_spaces", "empty_string_is_null"]
    elif base == "DATE":
        lb, dl, rules = "timestamp(0)", "TIMESTAMP", []
    elif base == "TIMESTAMP":
        lb, dl, rules = "timestamptz", "TIMESTAMP", ["datetime_utc_truncate_ms"]
    else:
        raise SystemExit(f"unmapped Oracle type {otype} on column {col}")
    return lb, dl, rules


LEGACY_TABLES = ("invoice_header", "invoice_line", "customer_master", "entity_attr_value",
                 "customer_master_hist")


def make_object(src: str, tgt: str, key: list[str], track: str,
                tables: dict[str, list[tuple[str, str]]],
                watermark=None, identity=None) -> dict:
    fields = []
    for col, otype in tables[src]:
        lb, dl, rules = target_types(col, otype, track)
        fields.append({
            "source": col, "target": col,
            "source_type": otype,
            "target_type": lb if track == "lakebase" else dl,
            "rules": rules,
        })
    obj = {
        "object": tgt,
        "source_table": f"{SOURCE_SCHEMA}.{src}",
        "target_table": tgt,
        "key": {"source": key, "target": key},
        "fields": fields,
    }
    if watermark:
        obj["watermark"] = {"source": watermark[0], "target": watermark[1] or watermark[0]}
    if identity:
        obj["identity"] = {"source": identity, "target": identity}
    return obj


def generation(src_tables: list[str]) -> str:
    return "legacy" if any(s in LEGACY_TABLES for s in src_tables) else "modern"


def build(unit_id: str, tables: dict[str, list[tuple[str, str]]]) -> dict:
    src, tgt, key, watermark, identity, track = UNITS_SPEC[unit_id]
    obj = make_object(src, tgt, key, track, tables, watermark, identity)
    return {
        "version": "map-p1-v1",
        "unit": unit_id,
        "track": track,
        "generation": generation([src]),
        "tables": [obj],
    }


def build_code(unit_id: str, tables: dict[str, list[tuple[str, str]]]) -> tuple[dict, list[dict]]:
    """A code/orchestration/transport unit: the tables it writes plus its Tier-4 ops."""
    written, ops = CODE_UNITS[unit_id]
    objs = [make_object(src, src, key, track, tables) for src, key, track in written]
    spec = {
        "version": "map-p1-v1",
        "unit": unit_id,
        "track": written[0][2],
        "generation": generation([s for s, _, _ in written]),
        "behavioural": True,
        "tables": objs,
    }
    ops_doc = [{"name": name, "object": unit_id, "source_sql": ssql, "target_sql": tsql,
                "rules": ["decimal_round", "rstrip_spaces", "empty_string_is_null",
                          "null_missing_equiv"]}
               for name, ssql, tsql in ops]
    return spec, ops_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    tables = parse_tables()
    drift: list[str] = []
    wanted: list[tuple[Path, str]] = []
    for unit_id in UNITS_SPEC:
        wanted.append((UNITS / unit_id / "mapping_spec.json",
                       json.dumps(build(unit_id, tables), indent=2) + "\n"))
    for unit_id in CODE_UNITS:
        spec, ops = build_code(unit_id, tables)
        wanted.append((UNITS / unit_id / "mapping_spec.json", json.dumps(spec, indent=2) + "\n"))
        if ops:
            wanted.append((UNITS / unit_id / "ops.json", json.dumps(ops, indent=2) + "\n"))
    for out, text in wanted:
        if args.check:
            if not out.exists() or out.read_text() != text:
                drift.append(str(out.relative_to(UNITS)))
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    if args.check and drift:
        print("mapping artifacts differ from the DDL for: " + ", ".join(drift))
        return 1
    print(f"{len(wanted)} mapping artifacts {'checked' if args.check else 'written'} "
          f"({len(UNITS_SPEC)} data units, {len(CODE_UNITS)} code/transport units)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
