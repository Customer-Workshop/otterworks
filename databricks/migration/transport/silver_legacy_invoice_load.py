#!/usr/bin/env python3
"""Materialize a legacy pipeline-1 invoice unit from ow_tp.bronze into ow_tp.silver.

Generation: LEGACY (D9-01). INVOICE_HEADER / INVOICE_LINE are the denormalized reporting
pair with string dates and no foreign keys; modern INVOICES / INVOICE_LINES are a different
generation and a different track, and nothing here touches them.

Bronze holds the lossless landing of the Oracle read (decimals exact, strings byte-exact),
so silver is built inside Databricks and costs the source nothing: the unit's one live
Oracle read is the recon gate, not this load.

Silver applies exactly what the unit's mapping_spec.json declares and nothing else:

  - declared target types, so NUMBER(4)/NUMBER(8) narrow to SMALLINT/INT and money stays
    DECIMAL(p,s) - never a float;
  - `DD-MON-YY` strings byte-exact, plus the mapping's derived parsed date columns, which
    reproduce `f_str2dt`: TO_DATE(raw,'DD-MON-YY') with NULL on anything unparseable, so a
    malformed legacy date stays a NULL and is not repaired;
  - a parsed column lands as TIMESTAMP_NTZ, not DATE: `f_str2dt` returns an Oracle DATE, and
    an Oracle DATE keeps its time part with no zone (the conversion rule the analysis fixed,
    and the type the dialect canonicalization profile maps Oracle DATE to). A DATE column
    hands the parity check a `date` against Oracle's midnight `datetime`, and a plain
    TIMESTAMP hands it a UTC-stamped one; neither compares equal to Oracle's naive value
    while the data is identical. The mapping's `derived_fields` annotate these columns
    `DATE`; that annotation is parent-owned, so it is raised as feedback, not edited here;
  - orphan invoice_line rows, magic status codes, and CHAR(1) Y/N are carried across as they
    are: reproducing legacy behaviour is the pass condition (D8-01).

The load is restart-safe and idempotent: the table is created once from the declared types,
then every run MERGEs the full bronze snapshot on the mapping's key and deletes target keys
bronze no longer has, so a rerun converges instead of duplicating.

    python3 silver_legacy_invoice_load.py --mapping .migration/units/p1-invoice-header/mapping_spec.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from databricks import sql as dbsql

CATALOG = "ow_tp"
BRONZE = "bronze"
SILVER = "silver"
WAREHOUSE = "565cd2fd713738c4"
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# f_str2dt: Oracle TO_DATE(raw,'DD-MON-YY','NLS_DATE_LANGUAGE=ENGLISH'), NULL on error.
# Spark's `yy` pivots on 2000-2099, which is Oracle's current-century rule for this run.
PARSE_DATE = "try_to_timestamp({col}, 'dd-MMM-yy')"

# Oracle DATE keeps its time part and carries no zone, so a column derived through f_str2dt
# is a zoneless timestamp on the target side. See the module docstring.
DERIVED_TYPE = {"DATE": "TIMESTAMP_NTZ"}


def ident(name: str) -> str:
    if not IDENT.match(name or ""):
        raise SystemExit(f"refusing non-identifier {name!r}")
    return name


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def field_expr(field: dict) -> str:
    """One bronze column rendered as its declared silver column."""
    col = ident(field["source"])
    rules = field.get("rules", [])
    expr = col
    if "rstrip_spaces" in rules:
        # CHAR(1) keeps its semantics; only padding the fixed width added is removed.
        expr = f"regexp_replace({expr}, ' +$', '')"
    if "empty_string_is_null" in rules:
        expr = f"nullif({expr}, '')"
    return f"cast({expr} AS {field['target_type']}) AS {ident(field['target'])}"


def derived_type(derived: dict) -> str:
    return DERIVED_TYPE.get(derived["target_type"], derived["target_type"])


def select_sql(table: dict) -> str:
    cols = [field_expr(f) for f in table["fields"]]
    cols += [f"cast({PARSE_DATE.format(col=ident(d['raw']))} AS {derived_type(d)}) "
             f"AS {ident(d['target'])}"
             for d in table.get("derived_fields", [])]
    src = ident(table["target_table"])
    return f"SELECT {', '.join(cols)} FROM {CATALOG}.{BRONZE}.{src}"


def create_sql(table: dict, generation: str) -> str:
    cols = [(ident(f["target"]), f["target_type"]) for f in table["fields"]]
    cols += [(ident(d["target"]), derived_type(d)) for d in table.get("derived_fields", [])]
    body = ", ".join(f"{name} {typ}" for name, typ in cols)
    target = ident(table["target_table"])
    comment = (f"{generation} generation (D9-01) pipeline-1 reporting table, "
               f"materialized from {CATALOG}.{BRONZE}.{target}; "
               "raw DD-MON-YY strings plus f_str2dt-equivalent parsed dates")
    return (f"CREATE TABLE IF NOT EXISTS {CATALOG}.{SILVER}.{target} ({body}) "
            f"COMMENT '{comment}'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recreate", action="store_true",
                    help="drop this unit's silver table first so its column types are "
                         "rebuilt: a MERGE never changes an existing column's type")
    args = ap.parse_args()

    with open(args.mapping) as fh:
        spec = json.load(fh)
    generation = spec.get("generation", "legacy")
    out = []
    statements = []
    for table in spec["tables"]:
        target = ident(table["target_table"])
        keys = [ident(k) for k in table["key"]["target"]]
        on = " AND ".join(f"t.{k} <=> s.{k}" for k in keys)
        merge = (f"MERGE INTO {CATALOG}.{SILVER}.{target} t "
                 f"USING ({select_sql(table)}) s ON {on} "
                 "WHEN MATCHED THEN UPDATE SET * "
                 "WHEN NOT MATCHED THEN INSERT * "
                 "WHEN NOT MATCHED BY SOURCE THEN DELETE")
        statements.append((table, create_sql(table, generation), merge))
    if args.dry_run:
        for _, create, merge in statements:
            print(create)
            print(merge)
        return 0

    with sql_conn() as conn, conn.cursor() as cur:
        for table, create, merge in statements:
            target = ident(table["target_table"])
            if args.recreate:
                cur.execute(f"DROP TABLE IF EXISTS {CATALOG}.{SILVER}.{target}")
            cur.execute(create)
            cur.execute(merge)
            cur.execute(f"SELECT count(*) FROM {CATALOG}.{BRONZE}.{target}")
            bronze_rows = cur.fetchone()[0]
            cur.execute(f"SELECT count(*) FROM {CATALOG}.{SILVER}.{target}")
            silver_rows = cur.fetchone()[0]
            out.append({"unit": spec["unit"], "generation": generation,
                        "target": f"{CATALOG}.{SILVER}.{target}",
                        "bronze_rows": bronze_rows, "silver_rows": silver_rows})
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
