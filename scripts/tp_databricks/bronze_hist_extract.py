#!/usr/bin/env python3
"""Land the OW_BILLING history tables in the bronze_hist namespace slice.

Reads CUSTOMER_MASTER_HIST and SUBSCRIPTIONS_HIST out of Oracle in full -- the
whole history, not a recent window -- and writes them to
`/Volumes/ow_tp/bronze/landing/<ns>/bronze_hist/` as newline-delimited JSON
alongside a manifest describing the source schema and row counts.

Every value lands as text exactly as Oracle reports it, so the notebook, not
this extractor, decides types: NUMBER keeps its full digits, DATE keeps its
seconds, NULL stays null and a zero-length string stays a zero-length string
(T9). Nothing is parsed, trimmed, coalesced or reordered here.

The live CUSTOMER_MASTER key set is landed next to the history so the load can
count history rows whose customer no longer exists. It is reference data for
that count only: the load never joins it as a filter, because a deleted
customer's last known state exists only in the history table (D-17).

    uv run --with oracledb==2.5.1 python3 \
        scripts/tp_databricks/bronze_hist_extract.py --ns demo

Databricks credentials come from DATABRICKS_DEMO_HOST / DATABRICKS_DEMO_TOKEN;
no credential is written to disk or into the manifest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import hashlib
import json
import os
import sys
from pathlib import Path

import oracledb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_dbx.client import Databricks, require_ns  # noqa: E402

UNIT = "bronze_hist"
CATALOG = "ow_tp"
LANDING_ROOT = f"/Volumes/{CATALOG}/bronze/landing"
HIST_TABLES = ("customer_master_hist", "subscriptions_hist")


def target_type(data_type: str, precision: int | None, scale: int | None, length: int | None) -> str:
    """Pin an explicit Databricks type for every source column (D-23, T6).

    Nothing is allowed to fall through to DOUBLE: an unpinned Oracle NUMBER
    silently becomes a float in most translation paths and rounds money where
    no type check can see it.
    """
    if data_type in ("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "CLOB"):
        return "STRING"
    if data_type in ("DATE", "TIMESTAMP") or data_type.startswith("TIMESTAMP"):
        return "TIMESTAMP"
    if data_type == "NUMBER":
        if precision is None:
            # An unbounded NUMBER never reaches this unit's tables; if the
            # source ever grows one, the load must stop rather than guess.
            return "DECIMAL(38,0)" if not scale else f"DECIMAL(38,{scale})"
        return f"DECIMAL({precision},{scale or 0})"
    raise SystemExit(f"no pinned target type for Oracle type {data_type!r}: stop and extend the dictionary")


def describe(cur, table: str) -> list[dict]:
    cur.execute(
        """SELECT column_name, data_type, data_precision, data_scale, char_length, nullable, column_id
             FROM user_tab_columns
            WHERE table_name = :t
            ORDER BY column_id""",
        t=table.upper(),
    )
    columns = []
    for name, data_type, precision, scale, char_len, nullable, _ in cur.fetchall():
        columns.append({
            "name": name.lower(),
            "oracle_type": data_type,
            "precision": int(precision) if precision is not None else None,
            "scale": int(scale) if scale is not None else None,
            "char_length": int(char_len) if char_len else None,
            "nullable": nullable == "Y",
            "target_type": target_type(data_type, precision, scale, char_len),
        })
    if not columns:
        raise SystemExit(f"{table} does not exist in this schema")
    return columns


def as_text(value) -> str | None:
    """Oracle value -> the text the landing file carries.

    NULL stays null. A zero-length string stays a zero-length string. Numbers
    keep every digit they were stored with, and DATE keeps its time component
    to the second (T7); neither is routed through a float.
    """
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%dT00:00:00")
    if isinstance(value, bytes):
        # Declared encoding is AL32UTF8; an undecodable byte is a correctness
        # event for the load to quarantine as ENC_INVALID, not something to
        # paper over here.
        return value.decode("utf-8", errors="strict")
    return str(value)


def dump_table(cur, table: str, columns: list[dict], out_dir: Path) -> dict:
    names = [c["name"] for c in columns]
    projection = ", ".join(names)
    cur.execute(f"SELECT {projection} FROM {table} ORDER BY hist_id")  # noqa: S608 - names come from the data dictionary
    path = out_dir / f"{table}.json"
    digest = hashlib.sha256()
    rows = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in cur:
            line = json.dumps(dict(zip(names, (as_text(v) for v in record))), ensure_ascii=False) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
            rows += 1
    return {
        "file": path.name,
        "source_rows": rows,
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "columns": columns,
    }


def dump_customer_keys(cur, out_dir: Path) -> dict:
    cur.execute("SELECT cust_id FROM customer_master ORDER BY cust_id")
    path = out_dir / "customer_master_keys.json"
    digest = hashlib.sha256()
    rows = 0
    with path.open("w", encoding="utf-8") as handle:
        for (cust_id,) in cur:
            line = json.dumps({"cust_id": as_text(cust_id)}, ensure_ascii=False) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
            rows += 1
    return {"file": path.name, "source_rows": rows, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--out", default=str(REPO_ROOT / ".tp-preflight" / "landing"),
                    help="local staging directory beneath the ignored .tp-preflight sandbox")
    ap.add_argument("--no-upload", action="store_true", help="stage locally without touching the volume")
    ap.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--password", default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    args = ap.parse_args()

    ns = require_ns(args.ns)
    out_dir = Path(args.out) / ns / UNIT
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "unit": UNIT,
        "ns": ns,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"kind": "oracle", "service": args.service, "schema": args.user.upper()},
        "tolerances_version": "03_recon_tolerances.md v1 (2026-08-28)",
        "tables": {},
    }

    dsn = f"{args.host}:{args.port}/{args.service}"
    with oracledb.connect(user=args.user, password=args.password, dsn=dsn) as conn:
        cur = conn.cursor()
        cur.arraysize = 500
        for table in HIST_TABLES:
            manifest["tables"][table] = dump_table(cur, table, describe(cur, table), out_dir)
        manifest["customer_master_keys"] = dump_customer_keys(cur, out_dir)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for table, info in manifest["tables"].items():
        print(f"[extract] {table}: {info['source_rows']} rows, {info['bytes']} bytes")
    print(f"[extract] customer_master keys: {manifest['customer_master_keys']['source_rows']}")

    if args.no_upload:
        print(f"[extract] staged in {out_dir} (upload skipped)")
        return 0

    dbx = Databricks()
    landing = f"{LANDING_ROOT}/{ns}/{UNIT}"
    for name in [f"{t}.json" for t in HIST_TABLES] + ["customer_master_keys.json", "manifest.json"]:
        dbx.put_file(f"{landing}/{name}", (out_dir / name).read_bytes())
        print(f"[extract] uploaded {landing}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
