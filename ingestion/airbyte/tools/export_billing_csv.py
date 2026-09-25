#!/usr/bin/env python3
"""Export one namespace of the Oracle billing estate as CSV files for Airbyte.

Airbyte Cloud cannot reach the on-VM Oracle fixture, so the legacy tables are
exported per namespace (scoped by the seeder's batch number) into an S3 landing
prefix that the Airbyte S3 source reads:

    s3://<bucket>/<ns>/<table>/<table>.csv

Values are written verbatim: string dates stay 'DD-MON-RR', CSV-in-a-column
lists stay CSV, NULLs become empty fields. Cleaning is the lakehouse's job.

Usage:
    export_billing_csv.py --ns demo --out /tmp/airbyte-landing [--bucket NAME]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import oracledb

TABLES = {
    "customer_master": "conversion_batch_no",
    "invoice_header": "batch_no",
    "invoice_line": "batch_no",
    "entity_attr_value": None,
}
NS_PATTERN = re.compile(r"^[a-z0-9]{1,31}$")


def ns_batch_no(ns: str) -> int:
    seed = int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)
    return seed % 90_000_000 + 1_000_000


def connect():
    return oracledb.connect(
        user=os.getenv("ORACLE_USER", "ow_billing"),
        password=os.getenv("ORACLE_PASSWORD", "ow_billing"),
        dsn=os.getenv("ORACLE_DSN", f"localhost:{os.getenv('ORACLE_PORT', '52521')}/FREEPDB1"),
    )


def table_sql(table: str, batch_col: str | None) -> str:
    if batch_col:
        return f"SELECT * FROM {table} WHERE {batch_col} = :batch_no ORDER BY 1"
    return (
        "SELECT e.* FROM entity_attr_value e "
        "WHERE e.entity_type = 'CUSTOMER' AND e.entity_id IN "
        "(SELECT cust_id FROM customer_master WHERE conversion_batch_no = :batch_no) "
        "ORDER BY e.eav_id"
    )


def export(ns: str, out_dir: Path) -> dict:
    batch_no = ns_batch_no(ns)
    manifest = {"kind": "airbyte-landing-manifest", "namespace": ns, "batch_no": batch_no, "tables": {}}
    with connect() as conn:
        for table, batch_col in TABLES.items():
            target = out_dir / ns / table
            target.mkdir(parents=True, exist_ok=True)
            path = target / f"{table}.csv"
            rows = 0
            digest = hashlib.sha256()
            with conn.cursor() as cur, path.open("w", newline="", encoding="utf-8") as handle:
                cur.execute(table_sql(table, batch_col), batch_no=batch_no)
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow([d[0].lower() for d in cur.description])
                for row in cur:
                    writer.writerow(["" if v is None else v for v in row])
                    rows += 1
            digest.update(path.read_bytes())
            manifest["tables"][table] = {
                "rows": rows,
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
                "key": f"{ns}/{table}/{table}.csv",
            }
    (out_dir / ns / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def upload(ns: str, out_dir: Path, bucket: str) -> None:
    import boto3

    s3 = boto3.client("s3")
    for path in sorted((out_dir / ns).rglob("*")):
        if path.is_file():
            key = str(path.relative_to(out_dir))
            s3.upload_file(str(path), bucket, key)
            print(f"uploaded s3://{bucket}/{key}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ns", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--bucket", help="upload the export to this S3 bucket after writing it")
    args = parser.parse_args()
    if not NS_PATTERN.match(args.ns):
        parser.error(f"--ns must match {NS_PATTERN.pattern}")
    manifest = export(args.ns, args.out)
    if args.bucket:
        upload(args.ns, args.out, args.bucket)
    json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
