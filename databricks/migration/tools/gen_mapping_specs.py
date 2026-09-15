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
# D10-01 (port 1521 to the Databricks serverless NAT range) was DENIED, so there is no
# Lakehouse Federation. Source-side op SQL runs on ORACLE, over JDBC from the Devin CIDRs
# through databricks/migration/recon/oracle_jdbc_adapter.py, and must therefore be Oracle
# dialect. Aliases are quoted lowercase because Oracle folds unquoted names to upper case and
# the harness's tier-4 diff matches result columns by exact name against a lowercase target.
SRC = "ow_billing"  # Oracle schema, read-only


def md5_uuid(expr: str) -> str:
    """Oracle SQL for pkg_ow_util.f_md5_uuid applied to `expr`, inlined from the package body.

    The read-only user cannot EXECUTE the package (ORA-41900) and granting it would be DDL on
    the source, so the gate compares this expression with billing.f_md5_uuid. Same inputs,
    same algorithm, both sides computed rather than recalled.
    """
    h = f"LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({expr}), 'MD5')))"
    return (f"SUBSTR({h},1,8)||'-'||SUBSTR({h},9,4)||'-'||SUBSTR({h},13,4)||'-'||"
            f"SUBSTR({h},17,4)||'-'||SUBSTR({h},21,12)")


CODE_UNITS: dict[str, tuple[list[tuple[str, list[str], str]], list[tuple[str, str, str]]]] = {
    # U-20's parity ops compare the hash ORACLE COMPUTES for an input against the hash the
    # converted function computes for the same input. Neither side calls the Oracle package:
    # the read-only user has no EXECUTE on it (ORA-41900) and granting it is source DDL, so
    # the source side inlines the package body's own expression (01_pkg_util.sql).
    #
    # It deliberately does NOT compare against the ids stored in rating_results / invoices /
    # invoice_lines. Those rows were loaded, not produced by the package, so their ids are not
    # hashes of their inputs; comparing them would fail the gate on data provenance rather
    # than on the algorithm. Stored-id provenance is the informational check in
    # databricks/migration/lakebase/w0a_md5_parity.py, not a merge gate.
    "p1-pkg-ow-util": (
        [("billing_audit_log", ["log_id"], "lakebase")],
        [("f_md5_uuid_vs_oracle_rating_result_inputs",
          f'SELECT period_id AS "input", {md5_uuid("period_id")} AS "hashed" '
          f"FROM {SRC}.rating_results ORDER BY period_id",
          "SELECT input AS input, billing.f_md5_uuid(input) AS hashed "
          "FROM billing.md5_parity_input WHERE vector = 'rating_result' ORDER BY input"),
         ("f_md5_uuid_vs_oracle_invoice_inputs",
          f'SELECT period_id || \'invoice\' AS "input", '
          f"""{md5_uuid("period_id || 'invoice'")} AS "hashed" """
          f"FROM {SRC}.invoices ORDER BY 1",
          "SELECT input AS input, billing.f_md5_uuid(input) AS hashed "
          "FROM billing.md5_parity_input WHERE vector = 'invoice' ORDER BY input"),
         ("f_md5_uuid_vs_oracle_invoice_line_inputs",
          f'SELECT invoice_id || TO_CHAR(line_no) AS "input", '
          f'{md5_uuid("invoice_id || TO_CHAR(line_no)")} AS "hashed" '
          f"FROM {SRC}.invoice_lines ORDER BY 1",
          "SELECT input AS input, billing.f_md5_uuid(input) AS hashed "
          "FROM billing.md5_parity_input WHERE vector = 'invoice_line' ORDER BY input")]),
    # The other four packages have NO ops file, deliberately. Their entrypoints are PL/SQL, and
    # the only way to put an Oracle-side result next to a target-side one would be an Oracle
    # view over the package - source DDL, which is forbidden. Their merge
    # evidence is the live row parity of the tables they write (below) plus the fixture-run
    # behavioural diff the plan specifies; the plan records the live-entrypoint comparison as a
    # declared unverified path rather than pretending a gate exists.
    "p1-pkg-plans": ([("subscriptions", ["id"], "lakebase")], []),
    "p1-pkg-rating": (
        [("rating_periods", ["id"], "lakebase"), ("rating_results", ["id"], "lakebase")], []),
    "p1-pkg-invoicing": (
        [("invoices", ["id"], "lakebase"), ("invoice_lines", ["id"], "lakebase")], []),
    "p1-pkg-dunning": (
        [("dunning_attempts", ["id"], "lakebase"), ("notifications", ["id"], "lakebase")], []),
    "p1-job-nightly-dunning": ([("dunning_attempts", ["id"], "lakebase")], []),
    "p1-job-purge-audit-log": ([("billing_audit_log", ["log_id"], "delta")], []),
    "p1-cdc-transport": (
        [("customer_master", ["cust_id"], "delta"), ("invoice_header", ["invoice_id"], "delta"),
         ("invoice_line", ["line_id"], "delta")], []),
}

# Ops that belong to a DATA unit because they need that unit's migrated table.
# f_code_desc is a lookup of codes.code_desc, so the Oracle row IS the expected value.
DATA_UNIT_OPS: dict[str, list[tuple[str, str, str]]] = {
    "p1-codes": [(
        "f_code_desc_all",
        f'SELECT code_type AS "code_type", code_val AS "code_val", code_desc AS "d" '
        f"FROM {SRC}.codes ORDER BY code_type, code_val",
        "SELECT code_type, code_val, billing.f_code_desc(code_type, code_val) AS d "
        "FROM billing.codes ORDER BY code_type, code_val")],
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
        # Fixed-width: Oracle blank-pads, so trailing spaces carry no information. VARCHAR2
        # keeps whatever was written, so stripping there would hide real data loss.
        lb, dl, rules = f"char({p})", "STRING", ["rstrip_spaces", "empty_string_is_null"]
    elif base == "VARCHAR2":
        lb, dl, rules = f"varchar({p})", "STRING", ["empty_string_is_null"]
    elif base == "DATE":
        lb, dl, rules = "timestamp(0)", "TIMESTAMP", []
    elif base == "TIMESTAMP":
        lb, dl, rules = "timestamptz", "TIMESTAMP", ["datetime_utc_truncate_ms"]
    else:
        raise SystemExit(f"unmapped Oracle type {otype} on column {col}")
    return lb, dl, rules


LEGACY_TABLES = ("invoice_header", "invoice_line", "customer_master", "entity_attr_value",
                 "customer_master_hist")

# The string-date columns of the analysis dictionary (section 3): DD-MON-YY text in a
# VARCHAR2(9). They migrate RAW (byte-exact) PLUS a parsed date column, so an explicit list
# is required - not every VARCHAR2(9) is a date and not every date column is 9 wide.
# `hist_dt` is VARCHAR2(20) in a different, undocumented format: it migrates raw only and the
# parse is an open item in the plan, because a parser that guesses is worse than none.
DDMONYY_WIDTH = "VARCHAR2(9)"
PARSED_SUFFIX = "_parsed"
DDMONYY_COLUMNS = frozenset({
    "signup_dt", "last_activity_dt", "last_invoice_dt", "last_payment_dt", "terminate_dt",
    "udf_dt_01", "udf_dt_02", "udf_dt_03", "udf_dt_04", "udf_dt_05",
    "udf_dt_06", "udf_dt_07", "udf_dt_08", "udf_dt_09", "udf_dt_10",
    "created_dt", "invoice_dt", "due_dt",
})
# VARCHAR2(20), a different and undocumented format: raw only, no parse. Guessing a parser
# here would silently mint wrong dates.
RAW_ONLY_DATE_COLUMNS = frozenset({"hist_dt", "service_period"})


def is_ddmonyy(col: str, otype: str) -> bool:
    return otype == DDMONYY_WIDTH and col.lower() in DDMONYY_COLUMNS


def check_date_columns(tables: dict[str, list[tuple[str, str]]]) -> None:
    """Fail if the DDL grew a VARCHAR2(9) column the approved list does not name.

    The list is explicit on purpose: a width is not a type. A new one is a dictionary
    decision (parse it or keep it raw), not something this generator should infer."""
    unknown = sorted({c for cols in tables.values() for c, t in cols
                      if t == DDMONYY_WIDTH and c.lower() not in DDMONYY_COLUMNS
                      and c.lower() not in RAW_ONLY_DATE_COLUMNS})
    if unknown:
        raise SystemExit(f"VARCHAR2(9) columns not in the approved string-date list: {unknown}. "
                         "Add them to DDMONYY_COLUMNS (parsed companion) or "
                         "RAW_ONLY_DATE_COLUMNS (raw only) with a dictionary decision.")


def date_columns(src: str, tables: dict[str, list[tuple[str, str]]]) -> list[str]:
    return [c for c, t in tables[src] if is_ddmonyy(c, t)]


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
    # Parsed companions for the DD-MON-YY string dates. They are NOT graded fields: there is
    # no source column to compare them with (Oracle parses on read, in f_str2dt), so grading
    # one against its raw string would fail every row. The contract is declared here and
    # proved by the unit's `str_date_parse` op, which compares the target's parsed column
    # against the same raw bytes parsed on the source side.
    parsed = [{"raw": c, "target": c + PARSED_SUFFIX,
               "target_type": "date" if track == "lakebase" else "DATE",
               "semantics": "f_str2dt: TO_DATE(raw,'DD-MON-YY') with NLS_DATE_LANGUAGE=ENGLISH, "
                            "NULL on anything else"}
              for c, t in tables[src] if is_ddmonyy(c, t)]
    if parsed:
        obj["derived_fields"] = parsed
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


def date_ops(unit_id: str, tables: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """Tier-4 op proving the parsed date column and the unparseable set, for one data unit.

    Both sides read the SAME raw bytes: the source side is the Oracle column parsed in Oracle,
    the target side is the column the conversion wrote. That proves the target parse and pins
    the NULL (unparseable) set as data, which is what the tolerance record compares as an exact
    set.

    The source parse is `TO_DATE(col DEFAULT NULL ON CONVERSION ERROR, 'DD-MON-YY',
    'NLS_DATE_LANGUAGE=ENGLISH')`, which is what `f_str2dt` does: a malformed date yields NULL
    rather than raising. A bare TO_DATE would abort the whole op on the first bad string, and
    malformed strings are a declared anomaly class here, not an error. The month names are
    English in the data and `f_str2dt` pins NLS_DATE_LANGUAGE explicitly; without that third
    argument the parse inherits the session's NLS language, and a non-English session would
    turn valid dates into NULLs that look exactly like the declared anomaly set.

    It still does not execute `f_str2dt` itself (that needs an Oracle view over the package,
    i.e. source DDL), so the plan carries the entrypoint comparison as an unverified path.
    """
    src, tgt, key, _, _, track = UNITS_SPEC[unit_id]
    cols = date_columns(src, tables)
    if not cols:
        return []
    keys = ", ".join(key)
    src_keys = ", ".join(f'{k} AS "{k}"' for k in key)
    src_cols = ", ".join(
        f"TO_DATE({c} DEFAULT NULL ON CONVERSION ERROR, 'DD-MON-YY', "
        f"'NLS_DATE_LANGUAGE=ENGLISH') AS \"{c}{PARSED_SUFFIX}\""
        for c in cols)
    tgt_cols = ", ".join(f"{c}{PARSED_SUFFIX}" for c in cols)
    tgt_table = f"billing.{tgt}" if track == "lakebase" else f"ow_tp.silver.{tgt}"
    return [{
        "name": f"str_date_parse_{tgt}",
        "object": unit_id,
        "source_sql": (f"SELECT {src_keys}, {src_cols} FROM {SRC}.{src} ORDER BY {keys}"),
        "target_sql": (f"SELECT {keys}, {tgt_cols} FROM {tgt_table} ORDER BY {keys}"),
        "rules": ["null_missing_equiv"],
    }]


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
                "rules": ["decimal_round", "empty_string_is_null", "null_missing_equiv"]}
               for name, ssql, tsql in ops]
    return spec, ops_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    tables = parse_tables()
    check_date_columns(tables)
    drift: list[str] = []
    wanted: list[tuple[Path, str]] = []
    for unit_id in UNITS_SPEC:
        wanted.append((UNITS / unit_id / "mapping_spec.json",
                       json.dumps(build(unit_id, tables), indent=2) + "\n"))
        ops = date_ops(unit_id, tables) + [
            {"name": name, "object": unit_id, "source_sql": ssql, "target_sql": tsql,
             "rules": ["empty_string_is_null", "null_missing_equiv"]}
            for name, ssql, tsql in DATA_UNIT_OPS.get(unit_id, [])]
        if ops:
            wanted.append((UNITS / unit_id / "ops.json", json.dumps(ops, indent=2) + "\n"))
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
    # A unit that loses its ops must lose the file: a stale ops.json is a gate the recon
    # harness would still run.
    expected = {p for p, _ in wanted}
    for stale in sorted(UNITS.glob("*/ops.json")):
        if stale in expected:
            continue
        if args.check:
            drift.append(f"{stale.relative_to(UNITS)} (stale, should not exist)")
        else:
            stale.unlink()
    if args.check and drift:
        print("mapping artifacts differ from the DDL for: " + ", ".join(drift))
        return 1
    print(f"{len(wanted)} mapping artifacts {'checked' if args.check else 'written'} "
          f"({len(UNITS_SPEC)} data units, {len(CODE_UNITS)} code/transport units)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
