#!/usr/bin/env python3
"""Digest a target table's full state so a reload can be proved idempotent.

Row count plus an order-independent hash of every row, read back from the target platform
itself rather than from the loader's own output.

The digest is SHA-256 of the sorted per-row SHA-256 hashes: sorting makes it independent of
row order, and nothing reduces a row to a short checksum on the way, so two different table
states cannot share a digest by summing to the same number.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from jdbc_watermark_load import CATALOG, SCHEMA, ident, sql_conn  # noqa: E402


def digest(table: str, schema: str = SCHEMA) -> dict:
    table = ident(table, "--table")
    qualified = f"{CATALOG}.{ident(schema, '--schema')}.{table}"
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {qualified}")
        rows = cur.fetchone()[0]
        cur.execute(
            "SELECT sha2(array_join(array_sort(collect_list(row_hash)), ''), 256) FROM "
            f"(SELECT sha2(to_json(struct(*)), 256) AS row_hash FROM {qualified})")
        content = cur.fetchone()[0]
    return {"table": qualified, "rows": rows, "content_digest": content}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--schema", default=SCHEMA, help=f"schema in {CATALOG} (default {SCHEMA})")
    ap.add_argument("--expect", help="JSON digest from an earlier run to compare against")
    args = ap.parse_args()
    got = digest(args.table, args.schema)
    if args.expect:
        want = json.loads(args.expect)
        got["idempotent"] = (want["rows"] == got["rows"]
                             and want["content_digest"] == got["content_digest"])
        got["previous"] = want
    print(json.dumps(got))
    return 0 if got.get("idempotent", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
