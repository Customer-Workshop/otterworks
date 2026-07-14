# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg2-binary", "tabulate"]
# ///
"""
OtterWorks RDS -> Aurora Serverless v2 reconciliation harness.

Proves the REPLATFORM move is data-identical before the connection-layer flip
is trusted: for every user table in the target schema it compares, between the
OLD (RDS) and NEW (Aurora) databases,

  1. row counts, and
  2. a deterministic content checksum
     md5( string_agg( md5(row_to_json(t)::text) ORDER BY row_to_json(t)::text ) )

A checksum is independent of physical row order, so two logically-identical
PostgreSQL databases hash the same regardless of how each engine stores rows.

This is a *continuous-validation* harness: with --watch it re-runs on an
interval so you can seed/replay traffic against both endpoints and watch
aggregates stay in lock-step until you trust the swap.

Usage:
    # one-shot compare of two endpoints
    uv run tests/reconciliation/reconcile_db.py \
        --old-dsn "postgresql://otterworks:otterworks_dev@localhost:5432/otterworks" \
        --new-dsn "postgresql://otterworks:otterworks_dev@localhost:5433/otterworks"

    # continuous validation every 10s until counts/checksums match N times
    uv run tests/reconciliation/reconcile_db.py --old-dsn ... --new-dsn ... \
        --watch --interval 10

Env fallbacks (used when --old-dsn / --new-dsn are omitted):
    RECON_OLD_DSN, RECON_NEW_DSN

Exit codes:
    0 = OLD and NEW reconcile (all tables match)
    1 = one or more tables diverge
    2 = connection/config error
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

import psycopg2
from tabulate import tabulate

DEFAULT_SCHEMA = "public"


@dataclass
class TableStats:
    table: str
    row_count: int
    checksum: str


def list_tables(conn, schema: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
              AND table_name <> 'flyway_schema_history'
            ORDER BY table_name
            """,
            (schema,),
        )
        return [r[0] for r in cur.fetchall()]


def table_stats(conn, schema: str, table: str) -> TableStats:
    qualified = f'"{schema}"."{table}"'
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {qualified}")  # noqa: S608 - identifiers are from information_schema
        count = int(cur.fetchone()[0])
        # Deterministic, order-independent content checksum.
        cur.execute(  # noqa: S608 - identifiers are from information_schema
            f"""
            SELECT md5(coalesce(
                string_agg(md5(row_to_json(t)::text), ',' ORDER BY row_to_json(t)::text),
                ''
            ))
            FROM {qualified} t
            """
        )
        checksum = cur.fetchone()[0]
    return TableStats(table=table, row_count=count, checksum=checksum)


def collect(dsn: str, schema: str, tables: list[str] | None) -> dict[str, TableStats]:
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True, autocommit=True)
        names = tables or list_tables(conn, schema)
        return {t: table_stats(conn, schema, t) for t in names}
    finally:
        conn.close()


def reconcile_once(old_dsn: str, new_dsn: str, schema: str, tables: list[str] | None) -> bool:
    old = collect(old_dsn, schema, tables)
    new = collect(new_dsn, schema, tables)

    all_tables = sorted(set(old) | set(new))
    rows = []
    ok = True
    for t in all_tables:
        o = old.get(t)
        n = new.get(t)
        if o is None or n is None:
            ok = False
            rows.append([t, "MISSING", o.row_count if o else "-", n.row_count if n else "-", "FAIL"])
            continue
        count_ok = o.row_count == n.row_count
        checksum_ok = o.checksum == n.checksum
        status = "PASS" if (count_ok and checksum_ok) else "FAIL"
        if status == "FAIL":
            ok = False
        detail = "" if status == "PASS" else (
            f"count {'ok' if count_ok else 'DIFF'} / checksum {'ok' if checksum_ok else 'DIFF'}"
        )
        rows.append([t, detail or "match", o.row_count, n.row_count, status])

    print(
        tabulate(
            rows,
            headers=["table", "detail", "old_rows", "new_rows", "status"],
            tablefmt="github",
        )
    )
    total = len(all_tables)
    passed = sum(1 for r in rows if r[-1] == "PASS")
    print(f"\n{passed}/{total} tables reconcile — {'RECONCILED' if ok else 'DIVERGENCE DETECTED'}")
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description="RDS -> Aurora reconciliation harness")
    p.add_argument("--old-dsn", default=os.getenv("RECON_OLD_DSN", ""))
    p.add_argument("--new-dsn", default=os.getenv("RECON_NEW_DSN", ""))
    p.add_argument("--schema", default=os.getenv("RECON_SCHEMA", DEFAULT_SCHEMA))
    p.add_argument("--tables", nargs="*", default=None, help="Restrict to these tables")
    p.add_argument("--watch", action="store_true", help="Continuous validation")
    p.add_argument("--interval", type=float, default=10.0, help="Seconds between watch passes")
    p.add_argument(
        "--require-passes",
        type=int,
        default=3,
        help="In --watch mode, exit 0 after this many consecutive reconciled passes",
    )
    args = p.parse_args()

    if not args.old_dsn or not args.new_dsn:
        print("ERROR: both --old-dsn and --new-dsn (or RECON_OLD_DSN/RECON_NEW_DSN) are required", file=sys.stderr)
        return 2

    try:
        if not args.watch:
            return 0 if reconcile_once(args.old_dsn, args.new_dsn, args.schema, args.tables) else 1

        consecutive = 0
        while True:
            print(f"\n=== reconcile pass @ {time.strftime('%H:%M:%S')} ===")
            ok = reconcile_once(args.old_dsn, args.new_dsn, args.schema, args.tables)
            consecutive = consecutive + 1 if ok else 0
            if consecutive >= args.require_passes:
                print(f"\nReconciled {consecutive} consecutive passes — swap is trusted.")
                return 0
            time.sleep(args.interval)
    except psycopg2.Error as exc:
        print(f"ERROR: database error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
