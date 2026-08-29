#!/usr/bin/env python3
"""Extract the bronze_wide source surfaces from OW_BILLING and land them.

Reads the four wide/denormalised billing tables straight out of Oracle at their
declared width, writes one Parquet file per table preserving the source types
(NUMBER -> DECIMAL, CHAR -> blank-padded STRING, VARCHAR2(9) date text stays
text), and uploads them to the unit's landing area
`/Volumes/ow_tp/bronze/landing/<ns>/bronze_wide/`.

Nothing is cleaned, trimmed, typed or de-duplicated here: transport only.  All
parsing and quarantine decisions happen in the notebook so they are visible in
the lakehouse.

Usage:
    python3 extract_and_land.py --ns demo [--no-upload] [--out DIR]

Oracle connection comes from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_SERVICE.
Databricks upload uses DATABRICKS_HOST / DATABRICKS_TOKEN (never persisted).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unit_spec import TABLES, load_source_schema  # noqa: E402

BATCH = 5000
VOLUME_ROOT = "/Volumes/ow_tp/bronze/landing"


def arrow_type(col: dict) -> pa.DataType:
    if col["type"] in ("VARCHAR2", "CHAR"):
        return pa.string()
    if col["type"] == "NUMBER":
        return pa.decimal128(col.get("precision", 38), col.get("scale", 0))
    if col["type"] == "DATE":
        return pa.timestamp("us")
    raise SystemExit(f"unsupported source type {col['type']} on {col['name']}")


def live_schema(cur, table: str) -> list[dict]:
    cur.execute(
        """
        SELECT column_name, data_type, data_length, data_precision, data_scale,
               nullable, column_id
          FROM all_tab_columns
         WHERE owner = 'OW_BILLING' AND table_name = :t
         ORDER BY column_id
        """,
        t=table,
    )
    out = []
    for name, dtype, dlen, prec, scale, nullable, pos in cur.fetchall():
        col = {
            "name": name,
            "type": dtype,
            "length": int(dlen),
            "nullable": nullable == "Y",
            "position": int(pos),
        }
        if prec is not None:
            col["precision"] = int(prec)
        if scale is not None:
            col["scale"] = int(scale)
        out.append(col)
    return out


def check_drift(table: str, declared: list[dict], live: list[dict]) -> None:
    d = {c["name"]: c for c in declared}
    l = {c["name"]: c for c in live}
    missing = sorted(set(d) - set(l))
    extra = sorted(set(l) - set(d))
    changed = [
        n for n in sorted(set(d) & set(l))
        if (d[n]["type"], d[n]["length"], d[n].get("precision"), d[n].get("scale"))
        != (l[n]["type"], l[n]["length"], l[n].get("precision"), l[n].get("scale"))
    ]
    if missing or extra or changed:
        raise SystemExit(
            f"SCHEMA DRIFT on {table}: missing={missing} extra={extra} changed={changed}\n"
            "The committed source_schema.json no longer describes the source. "
            "Stop and report rather than landing a partial width."
        )


def extract_table(cur, table: str, columns: list[dict], out_dir: Path) -> dict:
    schema = pa.schema([pa.field(c["name"], arrow_type(c)) for c in columns])
    col_list = ", ".join(c["name"] for c in columns)
    cur.arraysize = BATCH
    cur.execute(f"SELECT {col_list} FROM OW_BILLING.{table}")  # noqa: S608 - fixed identifiers
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "data.parquet"
    rows = 0
    writer = pq.ParquetWriter(path, schema)
    try:
        while True:
            batch = cur.fetchmany(BATCH)
            if not batch:
                break
            cols = list(zip(*batch)) if batch else [()] * len(columns)
            arrays = [
                pa.array(list(cols[i]), type=schema.field(i).type)
                for i in range(len(columns))
            ]
            writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
            rows += len(batch)
    finally:
        writer.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"rows": rows, "bytes": path.stat().st_size, "sha256": digest, "path": str(path)}


def upload(local: Path, remote: str) -> None:
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    token = os.environ["DATABRICKS_TOKEN"]
    url = f"{host}/api/2.0/fs/files{remote}?overwrite=true"
    resp = requests.put(
        url,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/octet-stream"},
        data=local.read_bytes(),
        timeout=600,
    )
    if resp.status_code not in (200, 204):
        raise SystemExit(f"landing upload failed {resp.status_code} for {remote}: {resp.text[:400]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--out", default="/tmp/bronze_wide_landing")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    declared = load_source_schema()
    oracledb.defaults.fetch_decimals = True
    conn = oracledb.connect(
        user=os.environ.get("DB_USER", "ow_billing"),
        password=os.environ.get("DB_PASSWORD", "ow_billing"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "52521")),
        service_name=os.environ.get("DB_SERVICE", "FREEPDB1"),
    )
    cur = conn.cursor()
    cur.execute("SELECT banner_full FROM v$version")
    banner = cur.fetchone()[0].splitlines()[0]
    cur.execute("SELECT systimestamp FROM dual")
    extracted_at = cur.fetchone()[0]

    manifest = {
        "unit": "bronze_wide",
        "ns": args.ns,
        "source": {
            "system": "OW_BILLING (Oracle)",
            "banner": banner,
            "service": os.environ.get("DB_SERVICE", "FREEPDB1"),
            "extracted_at": extracted_at.astimezone(dt.timezone.utc).isoformat(),
        },
        "tables": {},
    }
    out_root = Path(args.out) / args.ns / "bronze_wide"
    for table in TABLES:
        cols = declared[table]
        check_drift(table, cols, live_schema(cur, table))
        info = extract_table(cur, table, cols, out_root / table.lower())
        info["columns"] = len(cols)
        info["schema"] = cols
        manifest["tables"][table] = info
        print(f"[extract] {table}: {info['rows']} rows, {info['columns']} columns, "
              f"{info['bytes']} bytes")
    cur.close()
    conn.close()

    manifest_path = out_root / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    if not args.no_upload:
        for table in TABLES:
            local = Path(manifest["tables"][table]["path"])
            upload(local, f"{VOLUME_ROOT}/{args.ns}/bronze_wide/{table.lower()}/data.parquet")
            print(f"[land] {table} -> {VOLUME_ROOT}/{args.ns}/bronze_wide/{table.lower()}/data.parquet")
        upload(manifest_path, f"{VOLUME_ROOT}/{args.ns}/bronze_wide/_manifest.json")
    print(json.dumps({t: manifest["tables"][t]["rows"] for t in manifest["tables"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
