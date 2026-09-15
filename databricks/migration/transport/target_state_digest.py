#!/usr/bin/env python3
"""Digest a bronze table's full state so a reload can be proved idempotent.

Row count plus an order-independent hash of every row, read back from the target platform
itself rather than from the loader's own output.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from jdbc_watermark_load import CATALOG, SCHEMA, ident, sql_conn  # noqa: E402

BRONZE = f"{CATALOG}.{SCHEMA}"


def digest(table: str) -> dict:
    table = ident(table, "--table")
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {BRONZE}.{table}")
        rows = cur.fetchone()[0]
        cur.execute(
            f"SELECT bigint(sum(crc32(to_json(struct(*))))) FROM {BRONZE}.{table}")
        content = cur.fetchone()[0]
    return {"table": table, "rows": rows, "content_digest": content}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--expect", help="JSON digest from an earlier run to compare against")
    args = ap.parse_args()
    got = digest(args.table)
    if args.expect:
        want = json.loads(args.expect)
        got["idempotent"] = (want["rows"] == got["rows"]
                             and want["content_digest"] == got["content_digest"])
        got["previous"] = want
    print(json.dumps(got))
    return 0 if got.get("idempotent", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
