from __future__ import annotations

import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parent
DDL = ROOT / "sql" / "ow_billing_u0.sql"


def main() -> int:
    dsn = os.environ.get("LAKEBASE_MIGRATION_DSN")
    if not dsn:
        raise SystemExit("LAKEBASE_MIGRATION_DSN is unset")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            database = cur.fetchone()[0]
            if database != "databricks_postgres":
                raise RuntimeError(f"unexpected Lakebase database: {database!r}")
        conn.execute(DDL.read_text())
        conn.commit()
    print("Lakebase U0_shared_core DDL applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
