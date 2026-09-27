"""Wave 0 load: TRUNCATE + COPY the four billing reference tables on Lakebase from extract CSVs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

TARGET_SCHEMA = "billing"
TARGET_DATABASE = "ow_tp"
LOAD_ORDER = ["codes", "plans", "tenants", "usage_events"]  # FK-safe
TRUNCATE_ORDER = ["usage_events", "tenants", "plans", "codes"]  # FK-safe


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com")
    ap.add_argument("--user", default="d9d1c4ec-29da-4ec7-9aa0-e932710d61e2")
    ap.add_argument("--dbname", default="ow_tp")
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--in-dir", type=Path, required=True,
                    help="directory of <table>.csv files written by extract_reference.py")
    args = ap.parse_args(argv)

    # Password comes from ~/.pgpass via libpq; never handled here.
    conninfo = (
        f"host={args.host} port={args.port} user={args.user} "
        f"dbname={args.dbname} sslmode=require")
    with psycopg.connect(conninfo) as pg, pg.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
        if not row or row[0] != TARGET_DATABASE:
            raise SystemExit(
                f"connected to {row[0] if row else '?'}, not {TARGET_DATABASE}; refusing to write")
        cur.execute(
            "TRUNCATE TABLE " + ", ".join(f"{TARGET_SCHEMA}.{t}" for t in TRUNCATE_ORDER))
        for table in LOAD_ORDER:
            path = args.in_dir / f"{table}.csv"
            if not path.is_file():
                raise SystemExit(f"missing extract file {path}")
            header = path.open().readline().strip().split(",")
            tgt_cols = ", ".join(header)
            with cur.copy(
                    f"COPY {TARGET_SCHEMA}.{table} ({tgt_cols}) FROM STDIN "
                    "(FORMAT csv, HEADER true, NULL '\\N')") as copy, path.open("rb") as fh:
                while chunk := fh.read(1 << 20):
                    copy.write(chunk)
        for table in LOAD_ORDER:
            cur.execute(f"SELECT count(*) FROM {TARGET_SCHEMA}.{table}")
            print(f"{TARGET_DATABASE}.{TARGET_SCHEMA}.{table}: {cur.fetchone()[0]} rows")
        pg.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
