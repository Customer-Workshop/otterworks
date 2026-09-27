"""Wave 0 reference load, stage 2 of 2: JSON lines on stdin -> Lakebase ow_tp.billing (branch mig-20260927c-w0).

Consumes the stream extract_reference.py writes (stage 1, python-oracledb) and lands it with
psycopg COPY, one transaction: the four unit-owned tables are truncated and reloaded, the row
counts are checked against the extract's trailer and against count(*) after the copy, and only
then committed. Rerunnable: a rerun lands the identical rows. Touches no other billing table.

    extract_reference.py | load_reference.py

Values arrive as text (Decimal rendered exactly, ISO 8601 timestamps, CHAR(1) already stripped)
and are cast by the server to the declared column types of 00_scaffold.sql.

Connects to the literal Lakebase endpoint apply.sh uses (project ow-tp-billing, branch
mig-20260927c-w0) as the migration service principal; the password is libpq's ~/.pgpass entry
(token minted by `databricks postgres generate-database-credential`), never an argument.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Iterator

import psycopg

from reference_tables import TABLES, TARGET_DATABASE, TARGET_SCHEMA


def _scalar(row: tuple[object, ...] | None) -> object:
    if row is None or len(row) != 1:
        raise SystemExit(f"expected a single-column row, got {row!r}")
    return row[0]


def _parse(line: str) -> dict:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"malformed extract line: {exc}") from None
    if not isinstance(rec, dict):
        raise SystemExit("malformed extract line: not an object")
    return rec


def stream(lines: Iterator[str], trailer_box: list[dict[str, int] | None]) -> Iterator[dict]:
    """Row records up to the trailer, which is parked in trailer_box[0]; rows after it are refused."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rec = _parse(line)
        if "end" in rec:
            if not isinstance(rec["end"], dict):
                raise SystemExit("malformed extract trailer")
            trailer_box[0] = rec["end"]
            return
        if trailer_box[0] is not None:
            raise SystemExit("extract stream continues after its trailer")
        if not isinstance(rec.get("table"), str):
            raise SystemExit(f"extract line has no table: {line[:80]}")
        yield rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)

    by_target = {tgt: (columns, i) for i, (_, tgt, columns) in enumerate(TABLES)}
    order = [tgt for _, tgt, _ in TABLES]
    counts: dict[str, int] = {tgt: 0 for tgt in order}
    last_idx = -1
    trailer_box: list[dict[str, int] | None] = [None]
    records = stream(sys.stdin, trailer_box)

    with psycopg.connect(host="ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com", port=5432,
                         dbname="ow_tp", user="d9d1c4ec-29da-4ec7-9aa0-e932710d61e2",
                         sslmode="require") as pg:
        with pg.cursor() as cur:
            cur.execute("SELECT current_database()")
            db = _scalar(cur.fetchone())
            if db != TARGET_DATABASE:
                raise SystemExit(f"target DSN landed in {db}, not {TARGET_DATABASE}; refusing to write")
            targets = ", ".join(f"{TARGET_SCHEMA}.{tgt}" for tgt in order)
            cur.execute(f"TRUNCATE TABLE {targets}")

            for table, rows in itertools.groupby(records, key=lambda rec: rec["table"]):
                if table not in by_target:
                    raise SystemExit(f"extract stream names no unit-owned table: {table!r}")
                columns, idx = by_target[table]
                if idx <= last_idx:
                    raise SystemExit(f"{table}: extract stream is out of table order (FK order)")
                tgt_cols = ", ".join(tgt for _, tgt in columns)
                with cur.copy(f"COPY {TARGET_SCHEMA}.{table} ({tgt_cols}) FROM STDIN") as copy:
                    for rec in rows:
                        row = rec["row"]
                        if not isinstance(row, list) or len(row) != len(columns):
                            raise SystemExit(f"{table}: row has {len(row) if isinstance(row, list) else '?'} "
                                             f"values, expected {len(columns)}")
                        copy.write_row(row)
                        counts[table] += 1
                last_idx = idx
            trailer = trailer_box[0]

            if trailer is None:
                raise SystemExit("extract stream ended without its trailer; nothing committed")
            if trailer != counts:
                raise SystemExit(f"extract reported {trailer} rows, loader saw {counts}; nothing committed")
            for tgt in order:
                cur.execute(f"SELECT count(*) FROM {TARGET_SCHEMA}.{tgt}")
                landed = _scalar(cur.fetchone())
                if landed != counts[tgt]:
                    raise SystemExit(f"{tgt}: copied {counts[tgt]} rows but {landed} landed")
        pg.commit()
    for tgt in order:
        print(f"{TARGET_DATABASE}.{TARGET_SCHEMA}.{tgt}: {counts[tgt]} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
