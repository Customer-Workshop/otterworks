#!/usr/bin/env python3
"""Seed billing.md5_parity_input with the exact inputs the Tier-4 MD5 parity ops hash.

The three ops in .migration/units/p1-pkg-ow-util/ops.json put Oracle's hash of an input
next to billing.f_md5_uuid's hash of the SAME input. Oracle derives its inputs from live
rows; the target side reads them from this table, so the table has to hold the same set or
the op compares against nothing. One read-only Oracle query per vector.

The table is refilled, not appended to, so a rerun leaves it in the same state.

usage:
  python3 .../with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
  python3 /home/ubuntu/with_lakebase_dsn.py mig-p1-w0 -- \
  python3 databricks/migration/lakebase/w0a_seed_md5_vectors.py
"""
import json
import os
import sys

import oracledb
import psycopg

# vector name (must match ops.json) -> Oracle SQL yielding one input string per row
VECTORS = {
    "rating_result": "SELECT DISTINCT period_id FROM ow_billing.rating_results ORDER BY 1",
    "invoice": "SELECT DISTINCT period_id || 'invoice' FROM ow_billing.invoices ORDER BY 1",
    "invoice_line": ("SELECT DISTINCT invoice_id || TO_CHAR(line_no) "
                     "FROM ow_billing.invoice_lines ORDER BY 1"),
}


def main() -> int:
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    inputs: dict[str, list[str]] = {}
    with oracledb.connect(user=parts["user"], password=parts["password"],
                          dsn=f"{parts['host']}:{parts['port']}/{parts['service']}") as ora:
        for vector, sql in VECTORS.items():
            with ora.cursor() as cur:
                inputs[vector] = [r[0] for r in cur.execute(sql)]

    with psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"]) as lb, lb.cursor() as cur:
        cur.execute("TRUNCATE billing.md5_parity_input")
        for vector, values in inputs.items():
            cur.executemany(
                "INSERT INTO billing.md5_parity_input (vector, input) VALUES (%s, %s)",
                [(vector, v) for v in values])
        lb.commit()
        cur.execute("SELECT vector, count(*) FROM billing.md5_parity_input GROUP BY vector")
        seeded = dict(cur.fetchall())
    print(json.dumps({"seeded": seeded}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
