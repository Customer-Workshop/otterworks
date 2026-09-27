"""Wave 0 extract: dump OW_BILLING reference tables to CSV (one file per table) under --out."""
from __future__ import annotations

import argparse
import csv
import decimal
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import oracledb

SOURCE_SCHEMA = "OW_BILLING"
DEFAULT_SPEC = (
    Path(__file__).resolve().parents[3] / ".migration/units/lakebase_scaffold/mapping_spec.json"
)

_ORACLE_DSN_RE = re.compile(
    r"^(?:oracle://)?(?P<user>[^:/@\s]+)[:/](?P<password>[^@\s]*)@(?P<host>[^:/@\s]+)"
    r":(?P<port>\d+)/(?P<service>[^\s/]+)\s*$")


def _load_spec(path: Path) -> list[tuple[str, str, list[tuple[str, str, list[str]]]]]:
    spec = json.loads(path.read_text())
    tables = []
    for obj in spec["objects"]:
        root = obj["root_table"].split(".")[-1]
        target = obj["object"].split(".")[-1]
        fields = [
            (f["source"], f["target"], f.get("rules", []))
            for f in obj["fields"]
        ]
        tables.append((root, target, fields))
    return tables


def _oracle_connect(secret_name: str) -> oracledb.Connection:
    dsn_env = os.environ.get(secret_name)
    if not dsn_env:
        raise SystemExit(f"secret {secret_name} is not set in the environment")
    m = _ORACLE_DSN_RE.match(dsn_env)
    if not m:
        raise SystemExit(f"secret {secret_name} is not an oracle://user:pass@host:port/service DSN")
    return oracledb.connect(
        user=unquote(m["user"]), password=unquote(m["password"]),
        dsn=f"{m['host']}:{m['port']}/{m['service']}")


def _csv_value(column: str, rules: list[str], value: object) -> str:
    if value is None:
        return r"\N"
    if isinstance(value, str):
        if "rstrip_spaces" in rules:
            value = value.rstrip(" ")
        if value == "" and "empty_string_is_null" in rules:
            return r"\N"
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(value, float):  # never: fetch_decimals keeps NUMBER exact
        raise SystemExit(f"{column}: NUMBER arrived as float; exactness lost")
    raise SystemExit(f"{column}: unexpected source type {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-secret", default="OW_BILLING_RO_DSN",
                    help="env var holding oracle://user:pass@host:port/service")
    ap.add_argument("--out", required=True, help="output directory for per-table CSVs")
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC,
                    help="mapping spec JSON driving table/column order")
    args = ap.parse_args(argv)

    tables = _load_spec(args.spec)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    oracledb.defaults.fetch_decimals = True
    ora = _oracle_connect(args.source_secret)
    ora.begin()
    with ora.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")

    try:
        for src_table, tgt_table, fields in tables:
            cols = ", ".join(src for src, _, _ in fields)
            n = 0
            path = out_dir / f"{tgt_table}.csv"
            with ora.cursor() as cur, path.open("w", newline="") as fh:
                cur.arraysize = 5000
                cur.execute(f"SELECT {cols} FROM {SOURCE_SCHEMA}.{src_table}")
                writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
                writer.writerow([tgt for _, tgt, _ in fields])
                for row in cur:
                    writer.writerow(
                        [_csv_value(src, rules, v) for (src, _, rules), v in zip(fields, row)])
                    n += 1
            print(f"{src_table} -> {path.name}: {n} rows")
    finally:
        ora.rollback()
        ora.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
