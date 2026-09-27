#!/usr/bin/env python3
"""One-shot landing extract for the CUSTBILL Lakeflow unit.

Reads each OW_BILLING source table whole (SELECT *), writes one parquet file
per table to a local dir, then uploads to the bronze landing volume via
`databricks fs cp`. Oracle is read-only; the DSN comes from OW_BILLING_RO_DSN
(injected by ow_secret_env.py) and is never printed.
"""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq

TABLES = ["INVOICE_HEADER", "INVOICE_LINE", "CUSTOMER_MASTER", "ENTITY_ATTR_VALUE"]
OWNER = "OW_BILLING"
VOLUME_PREFIX = "dbfs:/Volumes/ow_tp/mig_20260927c_bronze/custbill_landing"

# Oracle source_type -> arrow type, per mapping_spec intended_target_types.
def arrow_type(source_type: str) -> pa.DataType:
    t = source_type.upper()
    if t.startswith("NUMBER"):
        inner = t[6:].strip("()")
        if "," in inner:
            p, s = (int(x) for x in inner.split(","))
            if s == 0:
                return pa.int64()
            return pa.decimal128(p, s)
        return pa.int64()
    if t == "DATE" or t.startswith("TIMESTAMP"):
        return pa.timestamp("us")
    return pa.string()


def load_type_map(spec_path: Path):
    spec = json.loads(spec_path.read_text())
    out = {}
    for obj in spec["objects"]:
        root = obj["root_table"].split(".")[-1]
        out[root] = {f["source"]: arrow_type(f["source_type"]) for f in obj["fields"]}
    return out


def fallback_type(desc) -> pa.DataType:
    tc = desc[1]
    if tc is oracledb.DB_TYPE_NUMBER:
        prec, scale = desc[4], desc[5]
        if scale and prec:
            return pa.decimal128(prec, scale)
        return pa.int64()
    if tc in (oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP):
        return pa.timestamp("us")
    return pa.string()


def connect():
    dsn = os.environ["OW_BILLING_RO_DSN"]
    u = urlparse(dsn)
    return oracledb.connect(
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port or 1521,
        service_name=u.path.lstrip("/"),
    )


def extract_table(conn, table, type_map, out_dir: Path, limit=None):
    sql = f"SELECT * FROM {OWNER}.{table}"
    if limit:
        sql += f" FETCH FIRST {int(limit)} ROWS ONLY"
    cols_map = type_map.get(table, {})
    with conn.cursor() as cur:
        cur.execute(sql)
        desc = cur.description
        names = [d[0] for d in desc]
        fields = [
            pa.field(n.lower(), cols_map.get(n, fallback_type(d)))
            for n, d in zip(names, desc)
        ]
        rows = cur.fetchall()
    colvals = {i: [] for i in range(len(names))}
    for row in rows:
        for i, v in enumerate(row):
            colvals[i].append(v)
    arrays = []
    for i, field in enumerate(fields):
        vals = colvals[i]
        if pa.types.is_decimal(field.type) or pa.types.is_int64(field.type):
            vals = [None if v is None else Decimal(str(v)) if pa.types.is_decimal(field.type) else int(v) for v in vals]
        arrays.append(pa.array(vals, type=field.type))
    tbl = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    path = out_dir / table.lower() / "part-0000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tbl, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"table": table.lower(), "rows": tbl.num_rows, "sha256": digest,
            "local": str(path), "volume": f"{VOLUME_PREFIX}/{table.lower()}/part-0000.parquet"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/custbill_landing"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--spec", default=str(Path(__file__).resolve().parents[4]
                                         / ".migration/units/custbill_lakeflow/mapping_spec.json"))
    ap.add_argument("--manifest", default=str(Path(__file__).resolve().parents[4]
                                              / ".migration/recon/custbill_lakeflow/landing_manifest.json"))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    type_map = load_type_map(Path(args.spec))
    conn = connect()
    manifest = {"extracted_at": datetime.now(timezone.utc).isoformat(),
                "limit": args.limit, "uploaded": not args.no_upload, "tables": []}
    try:
        for t in TABLES:
            info = extract_table(conn, t, type_map, out_dir, args.limit)
            manifest["tables"].append(info)
            print(f"{t}: {info['rows']} rows -> {info['local']}")
    finally:
        conn.close()
    if not args.no_upload:
        for info in manifest["tables"]:
            subprocess.run(
                ["databricks", "fs", "mkdir",
                 f"{VOLUME_PREFIX}/{info['table']}/"],
                check=True,
            )
            subprocess.run(
                ["databricks", "fs", "cp", info["local"], info["volume"], "--overwrite"],
                check=True,
            )
            print(f"uploaded {info['volume']}")
    Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest).write_text(json.dumps(manifest, indent=2))
    print(f"manifest -> {args.manifest}")


if __name__ == "__main__":
    main()
