#!/usr/bin/env python3
"""Read-only: print OW_BILLING.CREDIT_NOTES as a digest, from whichever source the

OW_TP_ORACLE_RO / fixture secret in the environment points at. Never writes, and never
touches the target.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import oracledb


def main() -> int:
    oracledb.defaults.fetch_decimals = True
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    with oracledb.connect(user=parts["user"], password=parts["password"],
                          dsn=f"{parts['host']}:{parts['port']}/{parts['service']}") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, tenant_id, issued_on, amount, remaining_amount "
                        "FROM credit_notes ORDER BY id")
            rows = cur.fetchall()
    body = "\n".join(repr(r) for r in rows)
    print(f"rows={len(rows)} sha256={hashlib.sha256(body.encode()).hexdigest()}")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
