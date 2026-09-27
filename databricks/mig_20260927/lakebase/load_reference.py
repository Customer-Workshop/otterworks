"""Wave 0 reference load: Oracle OW_BILLING -> Lakebase ow_tp.billing (branch mig-20260927-w0).

Whole-table copy of CODES, PLANS, TENANTS, USAGE_EVENTS through the session bridge:
python-oracledb (thin, read-only transaction) -> psycopg COPY. Every `ns::` demo tenant is
carried; nothing is filtered. Rerunnable: the four target tables are truncated and reloaded
inside one transaction, so a rerun lands the identical rows.

Secrets by name only:
  --source-secret  env var holding oracle://user:pass@host:port/service (default OW_BILLING_RO_DSN)
  --target-secret  env var holding the Lakebase libpq DSN (default LAKEBASE_MIGRATION_DSN)

Type mapping is .migration/units/lakebase_scaffold/mapping_spec.json: NUMBER(p) -> bigint,
NUMBER(p,s) -> numeric(p,s) (fetched as Decimal, never float), VARCHAR2 -> varchar,
CHAR(1) -> char(1) with trailing spaces stripped, TIMESTAMP(6) -> timestamp(6) without zone.
"""
from __future__ import annotations

import argparse
import decimal
import os
import re
import sys
from datetime import datetime

import oracledb
import psycopg

SOURCE_SCHEMA = "OW_BILLING"
TARGET_SCHEMA = "billing"
TARGET_DATABASE = "ow_tp"

# (oracle table, target table, [(source column, target column)]) in the mapping spec's order;
# usage_events last so the FK to tenants is satisfied.
TABLES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("CODES", "codes", [("CODE_TYPE", "code_type"), ("CODE_VAL", "code_val"), ("CODE_DESC", "code_desc")]),
    ("PLANS", "plans", [("ID", "id"), ("CODE", "code"), ("TIER_CD", "tier_cd"), ("MONTHLY_FEE", "monthly_fee"),
                        ("INCLUDED_UNITS", "included_units"), ("OVERAGE_RATE", "overage_rate"),
                        ("ACTIVE_YN", "active_yn")]),
    ("TENANTS", "tenants", [("ID", "id"), ("NAME", "name"), ("TAX_EXEMPT_YN", "tax_exempt_yn"),
                            ("STATUS_CD", "status_cd")]),
    ("USAGE_EVENTS", "usage_events", [("ID", "id"), ("TENANT_ID", "tenant_id"), ("OCCURRED_AT", "occurred_at"),
                                      ("UNITS", "units"), ("KIND_CD", "kind_cd")]),
]
CHAR1_COLUMNS = {"ACTIVE_YN", "TAX_EXEMPT_YN"}

_ORACLE_DSN_RE = re.compile(
    r"^(?:oracle://)?(?P<user>[^:/@\s]+)[:/](?P<password>[^@\s]*)@(?P<host>[^:/@\s]+)"
    r":(?P<port>\d+)/(?P<service>[^\s/]+)\s*$")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"secret {name} is not set in the environment")
    return value


def oracle_connect(secret_name: str) -> oracledb.Connection:
    from urllib.parse import unquote
    m = _ORACLE_DSN_RE.match(_env(secret_name))
    if not m:
        raise SystemExit(f"secret {secret_name} is not an oracle://user:pass@host:port/service DSN")
    return oracledb.connect(user=unquote(m["user"]), password=unquote(m["password"]),
                            dsn=f"{m['host']}:{m['port']}/{m['service']}")


def normalize(column: str, value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        if column in CHAR1_COLUMNS:
            value = value.rstrip(" ")
        return None if value == "" else value
    if isinstance(value, (int, decimal.Decimal, datetime)):
        return value
    if isinstance(value, float):  # never: fetch_decimals keeps NUMBER exact
        raise SystemExit(f"{column}: NUMBER arrived as float; exactness lost")
    raise SystemExit(f"{column}: unexpected source type {type(value).__name__}")


def read_table(ora: oracledb.Connection, table: str, columns: list[tuple[str, str]]):
    cols = ", ".join(src for src, _ in columns)
    with ora.cursor() as cur:
        cur.arraysize = 5000
        cur.execute(f"SELECT {cols} FROM {SOURCE_SCHEMA}.{table}")
        for row in cur:
            yield tuple(normalize(src, v) for (src, _), v in zip(columns, row))


def _scalar(row: tuple[object, ...] | None) -> object:
    if row is None or len(row) != 1:
        raise SystemExit(f"expected a single-column row, got {row!r}")
    return row[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-secret", default="OW_BILLING_RO_DSN")
    ap.add_argument("--target-secret", default="LAKEBASE_MIGRATION_DSN")
    args = ap.parse_args(argv)

    oracledb.defaults.fetch_decimals = True
    ora = oracle_connect(args.source_secret)
    ora.begin()
    with ora.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")

    counts: dict[str, int] = {}
    with psycopg.connect(_env(args.target_secret)) as pg:
        with pg.cursor() as cur:
            cur.execute("SELECT current_database()")
            db = _scalar(cur.fetchone())
            if db != TARGET_DATABASE:
                raise SystemExit(f"target DSN landed in {db}, not {TARGET_DATABASE}; refusing to write")
            targets = ", ".join(f"{TARGET_SCHEMA}.{tgt}" for _, tgt, _ in TABLES)
            cur.execute(f"TRUNCATE TABLE {targets}")
            for src_table, tgt_table, columns in TABLES:
                tgt_cols = ", ".join(tgt for _, tgt in columns)
                n = 0
                with cur.copy(f"COPY {TARGET_SCHEMA}.{tgt_table} ({tgt_cols}) FROM STDIN") as copy:
                    for row in read_table(ora, src_table, columns):
                        copy.write_row(row)
                        n += 1
                counts[tgt_table] = n
            for _, tgt_table, _ in TABLES:
                cur.execute(f"SELECT count(*) FROM {TARGET_SCHEMA}.{tgt_table}")
                landed = _scalar(cur.fetchone())
                if landed != counts[tgt_table]:
                    raise SystemExit(f"{tgt_table}: copied {counts[tgt_table]} rows but {landed} landed")
        pg.commit()
    ora.rollback()
    ora.close()
    for tgt_table, n in counts.items():
        print(f"{TARGET_DATABASE}.{TARGET_SCHEMA}.{tgt_table}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
