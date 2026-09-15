#!/usr/bin/env python3
"""Apply a reviewed .sql file to the Lakebase branch named by $OW_TP_LAKEBASE_DSN.

usage: python3 apply_sql.py <file.sql> [<file.sql> ...]
The DSN comes from the environment and is never printed.

Only files committed under this directory (databricks/migration/lakebase/) can be applied.
The DSN belongs to the migration principal, which owns the billing schema, so an arbitrary
path would turn this into a way to run any privileged statement against the target. Keeping
the input inside the reviewed directory means everything it can run has been through a PR.
"""
import os
import sys
from pathlib import Path

import psycopg

ALLOWED_DIR = Path(__file__).resolve().parent


def resolve(path: str) -> Path:
    p = Path(path).resolve()
    if p.suffix != ".sql" or not p.is_file():
        raise SystemExit(f"not a .sql file: {path}")
    if p.parent != ALLOWED_DIR:
        raise SystemExit(
            f"refusing {path}: only .sql files in {ALLOWED_DIR} may be applied")
    return p


def main(paths: list[str]) -> int:
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")
    if not paths:
        raise SystemExit("usage: apply_sql.py <file.sql> [<file.sql> ...]")
    files = [resolve(p) for p in paths]
    with psycopg.connect(dsn, autocommit=False) as conn:
        for path in files:
            with conn.cursor() as cur:
                cur.execute(path.read_text())
            conn.commit()
            print(f"applied {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
