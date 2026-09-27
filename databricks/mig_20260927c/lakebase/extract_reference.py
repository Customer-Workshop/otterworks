"""Wave 0 reference extract, stage 1 of 2: Oracle OW_BILLING -> JSON lines on stdout.

Whole-table read of CODES, PLANS, TENANTS, USAGE_EVENTS with python-oracledb (thin, one
read-only transaction). Every `ns::` demo tenant is carried; nothing is filtered. The stream
is consumed by load_reference.py (stage 2, psycopg COPY):

    extract_reference.py | load_reference.py

Line format: {"table": "<target table>", "row": [<text values>]} per source row, then one
{"end": {"<target table>": <row count>, ...}} trailer the loader checks before committing.
Values travel as text so nothing is rounded: NUMBER is fetched as Decimal (never float) and
rendered with str(), TIMESTAMP(6) as ISO 8601 with microseconds, CHAR(1) with trailing
spaces stripped, NULL as JSON null.

Secret by name only: --source-secret names the env var holding
oracle://user:pass@host:port/service (default OW_BILLING_RO_DSN).
"""
from __future__ import annotations

import argparse
import decimal
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import unquote

import oracledb

from reference_tables import CHAR1_COLUMNS, SOURCE_SCHEMA, TABLES

_ORACLE_DSN_RE = re.compile(
    r"^(?:oracle://)?(?P<user>[^:/@\s]+)[:/](?P<password>[^@\s]*)@(?P<host>[^:/@\s]+)"
    r":(?P<port>\d+)/(?P<service>[^\s/]+)\s*$")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"secret {name} is not set in the environment")
    return value


def oracle_connect(secret_name: str) -> oracledb.Connection:
    m = _ORACLE_DSN_RE.match(_env(secret_name))
    if not m:
        raise SystemExit(f"secret {secret_name} is not an oracle://user:pass@host:port/service DSN")
    return oracledb.connect(user=unquote(m["user"]), password=unquote(m["password"]),
                            dsn=f"{m['host']}:{m['port']}/{m['service']}")


def render(column: str, value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if column in CHAR1_COLUMNS:
            value = value.rstrip(" ")
        return None if value == "" else value
    if isinstance(value, bool):
        raise SystemExit(f"{column}: unexpected source type bool")
    if isinstance(value, (int, decimal.Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="microseconds")
    if isinstance(value, float):  # never: fetch_decimals keeps NUMBER exact
        raise SystemExit(f"{column}: NUMBER arrived as float; exactness lost")
    raise SystemExit(f"{column}: unexpected source type {type(value).__name__}")


def read_table(ora: oracledb.Connection, table: str, columns: list[tuple[str, str]]):
    cols = ", ".join(src for src, _ in columns)
    with ora.cursor() as cur:
        cur.arraysize = 5000
        cur.execute(f"SELECT {cols} FROM {SOURCE_SCHEMA}.{table}")
        for row in cur:
            yield [render(src, v) for (src, _), v in zip(columns, row)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-secret", default="OW_BILLING_RO_DSN")
    args = ap.parse_args(argv)

    oracledb.defaults.fetch_decimals = True
    ora = oracle_connect(args.source_secret)
    ora.begin()
    with ora.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")

    out = sys.stdout
    counts: dict[str, int] = {}
    for src_table, tgt_table, columns in TABLES:
        n = 0
        for row in read_table(ora, src_table, columns):
            out.write(json.dumps({"table": tgt_table, "row": row}, separators=(",", ":")))
            out.write("\n")
            n += 1
        counts[tgt_table] = n
    out.write(json.dumps({"end": counts}, separators=(",", ":")))
    out.write("\n")
    out.flush()
    ora.rollback()
    ora.close()
    for tgt_table, n in counts.items():
        print(f"{SOURCE_SCHEMA}.{tgt_table.upper()}: {n} rows read", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
