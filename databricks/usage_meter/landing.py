"""Write usage event batches into the landing volume.

The estate has no live event feed yet, so the meter is fed by batch files dropped
in `/Volumes/ow_tp/bronze/usage_meter_landing/`. The initial batch is exported
from the migrated Delta snapshot `ow_tp.silver.usage_events` -- Delta, never
Oracle. Once a real producer exists it writes the same JSON lines and nothing
downstream changes. Batches land flat in the volume root, because the readers
used here do not descend into subdirectories.

    python3 landing.py backfill            # export the migrated snapshot as one batch
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

from executor import get_executor
from meter_sql import PRODUCTION, Namespace

FIELDS = ("event_id", "tenant_id", "occurred_at", "units", "kind_cd")


def _client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def write_batch(records: Iterable[dict[str, Any]], subdir: str = "", name: str | None = None,
                ns: Namespace = PRODUCTION) -> str:
    """Upload one JSON-lines batch file and return its volume path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    filename = name or f"usage_events_{stamp}.json"
    path = "/".join(p for p in (ns.landing, subdir, filename) if p)
    body = "\n".join(json.dumps({k: r.get(k) for k in FIELDS}, default=str) for r in records)
    _client().files.upload(path, io.BytesIO(body.encode()), overwrite=True)
    return path


def snapshot_records(ex, limit: int | None = None) -> list[dict[str, Any]]:
    """The migrated usage events, shaped as they would arrive from a producer."""
    rows = ex.sql(
        "SELECT id AS event_id, tenant_id, "
        "DATE_FORMAT(occurred_at, 'yyyy-MM-dd HH:mm:ss') AS occurred_at, "
        "CAST(units AS STRING) AS units, CAST(kind_cd AS STRING) AS kind_cd "
        "FROM ow_tp.silver.usage_events ORDER BY occurred_at, id"
        + (f" LIMIT {int(limit)}" if limit else ""))
    return [dict(r) for r in rows]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backfill"])
    parser.add_argument("--subdir", default="", help="leave empty: batches land flat in the volume root")
    args = parser.parse_args(argv)

    ex = get_executor()
    records = snapshot_records(ex)
    # A fresh file name every export: COPY INTO skips a path it has already read,
    # so overwriting one would make later exports invisible.
    path = write_batch(records, subdir=args.subdir)
    print(json.dumps({"records": len(records), "path": path}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
