"""The usage meter pipeline: land -> normalise -> meter.

Each stage is a function so the Lakeflow tasks, the tests and a local run all
execute the same code. Stages are safe to rerun: bronze ingest skips files it has
already read, silver dedupes on event id, and gold recomputes only the periods
whose events moved since its watermark.

    python3 pipeline.py ingest|normalise|meter
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# The Lakeflow task execs this file without setting __file__, so fall back to argv.
for _candidate in (globals().get("__file__"), sys.argv[0]):
    if _candidate:
        sys.path.insert(0, os.path.dirname(os.path.abspath(_candidate)))

from executor import Executor, get_executor, run_id
from meter_sql import (
    PRODUCTION,
    Namespace,
    bronze_high_watermark,
    constraints,
    copy_into_bronze,
    ddl,
    merge_gold,
    merge_silver,
    quarantine_rejects,
    read_watermark,
    silver_high_watermark,
    volume_ddl,
    write_watermark,
)

EPOCH = "1900-01-01 00:00:00"
# The subdirectory ends up in a volume path and a SQL source literal.
SAFE_SUBDIR = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


def _ts(value: Any) -> str:
    return str(value)[:26] if value is not None else EPOCH


def ensure_objects(ex: Executor, ns: Namespace = PRODUCTION, with_volume: bool = True) -> None:
    if with_volume:
        ex.sql(volume_ddl(ns))
    for statement in ddl(ns):
        ex.sql(statement)
    for statement in constraints(ns):
        try:
            ex.sql(statement)
        except Exception as exc:  # the constraint is already there on a rerun
            if "already exists" not in str(exc).lower():
                raise


def ingest(ex: Executor, ns: Namespace = PRODUCTION, subdir: str = "") -> dict[str, Any]:
    if subdir and not SAFE_SUBDIR.fullmatch(subdir):
        raise SystemExit(f"refusing to read {subdir!r}: not a plain landing subdirectory")
    before = _ts(ex.scalar(read_watermark(ns, "bronze")))
    ex.sql(copy_into_bronze(ns, subdir))
    row = ex.one(bronze_high_watermark(ns, before)) or {}
    rows_in = int(row.get("n") or 0)
    high = _ts(row.get("hi")) if rows_in else before
    ex.sql(write_watermark(ns, "bronze", high, rows_in, run_id()))
    return {"stage": "ingest", "rows_landed": rows_in, "watermark": high}


def normalise(ex: Executor, ns: Namespace = PRODUCTION) -> dict[str, Any]:
    before = _ts(ex.scalar(read_watermark(ns, "silver")))
    row = ex.one(bronze_high_watermark(ns, before)) or {}
    rows_in = int(row.get("n") or 0)
    if rows_in == 0:
        ex.sql(write_watermark(ns, "silver", before, 0, run_id()))
        return {"stage": "normalise", "rows_in": 0, "watermark": before}
    high = _ts(row.get("hi"))
    # Bound the batch by `high` so rows landing mid-run are picked up next time
    # instead of being skipped by the watermark.
    ex.sql(quarantine_rejects(ns, before, high))
    ex.sql(merge_silver(ns, before, high))
    ex.sql(write_watermark(ns, "silver", high, rows_in, run_id()))
    return {"stage": "normalise", "rows_in": rows_in, "watermark": high}


def meter(ex: Executor, ns: Namespace = PRODUCTION) -> dict[str, Any]:
    before = _ts(ex.scalar(read_watermark(ns, "gold")))
    row = ex.one(silver_high_watermark(ns, before)) or {}
    rows_in = int(row.get("n") or 0)
    if rows_in == 0:
        ex.sql(write_watermark(ns, "gold", before, 0, run_id()))
        return {"stage": "meter", "rows_in": 0, "watermark": before, "cells_written": 0}
    high = _ts(row.get("hi"))
    cells = ex.scalar(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT tenant_id, kind_cd, period_start FROM {ns.events} "
        f"WHERE last_seen_at > CAST('{before}' AS TIMESTAMP_NTZ) "
        f"AND last_seen_at <= CAST('{high}' AS TIMESTAMP_NTZ))")
    ex.sql(merge_gold(ns, before, high))
    ex.sql(write_watermark(ns, "gold", high, rows_in, run_id()))
    return {"stage": "meter", "rows_in": rows_in, "watermark": high, "cells_written": int(cells or 0)}


STAGES = {"ingest": ingest, "normalise": normalise, "meter": meter}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument("--subdir", default="", help="subdirectory of the landing volume to read")
    args = parser.parse_args(argv)

    ex = get_executor()
    ensure_objects(ex)
    result = ingest(ex, PRODUCTION, args.subdir) if args.stage == "ingest" else STAGES[args.stage](ex, PRODUCTION)
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    # The Lakeflow task execs this file, where SystemExit(0) still marks the run
    # failed, so only exit on a non-zero code.
    _code = main(sys.argv[1:])
    if _code:
        sys.exit(_code)
