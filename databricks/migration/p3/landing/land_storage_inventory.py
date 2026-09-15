#!/usr/bin/env python3
"""Land the file-storage inventory and its metadata references in bronze.

    python3 databricks/migration/p3/landing/land_storage_inventory.py \
        --snapshot-dir /path/to/fixtures/p3probe --batch p3probe

`storage_cleanup_daily.py` reads two things it cannot read twice the same way: a live
`list_objects_v2` over the file-storage bucket, and a live DynamoDB scan of the metadata
table. It then deletes from the bucket it just listed, so its own second run sees a
different world. P3-D03 splits those apart: the two inputs are landed here, the candidate
set is computed in SQL from the landed copy, and nothing in the converted unit deletes.

Both tables are keyed on (`snapshot_batch`, natural key) and loaded by MERGE, so landing
the same snapshot twice leaves them byte-identical.

The inventory is landed whole, including keys outside the `files/` prefix. The legacy only
lists `files/`, and the prefix filter belongs in the silver SQL next to the rest of the
delete-set definition — landing a pre-filtered inventory would hide the objects the
converted job must be shown *not* to select.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

INVENTORY_TABLE = "ow_tp.bronze.p3_cleanup_inventory_raw"
METADATA_TABLE = "ow_tp.bronze.p3_cleanup_metadata_raw"
RUNS_TABLE = "ow_tp.bronze.p3_cleanup_landing_runs"
DEFAULT_VOLUME = "/Volumes/ow_tp/bronze/landing/analytics"
WAREHOUSE = "565cd2fd713738c4"
FILES = ("file_inventory.json", "file_metadata.json")

CREATE_INVENTORY = f"""
CREATE TABLE IF NOT EXISTS {INVENTORY_TABLE} (
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot this listing came from',
  object_key STRING NOT NULL COMMENT 'S3 key exactly as listed, every prefix, not just files/',
  size_bytes BIGINT NOT NULL COMMENT 'object size in bytes; part of the delete-set key, so a truncating copy is not a match',
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Durable copy of the file-storage listing storage_cleanup_daily.py would have made live.'
"""

CREATE_METADATA = f"""
CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (
  snapshot_batch STRING NOT NULL,
  file_id STRING NOT NULL COMMENT 'metadata row id; the legacy projects s3_key only, this keeps the row identifiable',
  s3_key STRING COMMENT 'the reference the legacy collects; empty and missing values are kept and skipped in SQL',
  owner_id STRING,
  size_bytes BIGINT COMMENT 'the metadata rows own size, which the legacy never reads: it sizes from the listing',
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Durable copy of the otterworks-file-metadata scan that names which objects are still referenced.'
"""

CREATE_RUNS = f"""
CREATE TABLE IF NOT EXISTS {RUNS_TABLE} (
  snapshot_batch STRING NOT NULL,
  objects_landed BIGINT NOT NULL COMMENT 'rows in the snapshot listing, every prefix',
  metadata_landed BIGINT NOT NULL,
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'One row per landed snapshot. A snapshot that legitimately holds no objects lands zero inventory rows, so the row count alone cannot tell an empty bucket from a listing that never arrived; this receipt can.'
"""


def client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def execute(w, statement: str, parameters=None) -> list[list[str]]:
    """Run one statement on the migration warehouse, binding named markers only."""
    from databricks.sdk.service.sql import StatementParameterListItem

    if isinstance(parameters, list):
        params = parameters
    else:
        params = [StatementParameterListItem(name=k, value=v)
                  for k, v in (parameters or {}).items() if f":{k}" in statement]
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, parameters=params or None,
        wait_timeout="50s")
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def verify_snapshot(snapshot: Path) -> None:
    """Refuse a snapshot that does not match its own manifest.

    The snapshot is the declared input of both sides of this recon: the legacy ran against
    a clone of it, the target reads it. A drifted copy would compare the target against
    input the legacy never saw.
    """
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{snapshot} has no manifest.json; regenerate it with gen_p3_fixture.py")
    checksums = json.loads(manifest_path.read_text()).get("checksums")
    if not checksums:
        raise SystemExit(f"{manifest_path} carries no checksums; regenerate the fixture")
    problems = []
    for name in FILES:
        expected = checksums.get(name)
        path = snapshot / name
        if expected is None:
            problems.append(f"{name}: not declared in the manifest")
        elif not path.exists():
            problems.append(f"{name}: declared in the manifest but missing")
        else:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                problems.append(f"{name}: sha256 {actual} != manifest {expected}")
    if problems:
        raise SystemExit("snapshot does not match its manifest:\n  " + "\n  ".join(problems))


def upload(w, snapshot: Path, volume_dir: str) -> list[str]:
    written = []
    for name in (*FILES, "manifest.json"):
        target = f"{volume_dir}/{name}"
        w.files.upload(target, (snapshot / name).open("rb"), overwrite=True)
        written.append(target)
    return written


def inventory_rows(snapshot: Path, batch: str) -> list[tuple]:
    listing = json.loads((snapshot / "file_inventory.json").read_text())
    return [(batch, obj["key"], obj["size"]) for obj in listing]


def metadata_rows(snapshot: Path, batch: str) -> list[tuple]:
    rows = json.loads((snapshot / "file_metadata.json").read_text())
    return [(batch, row["id"], row.get("s3_key"), row.get("owner_id"),
             row.get("size_bytes")) for row in rows]


def record_run(w, batch: str, objects: int, metadata: int) -> None:
    """Receipt that this batch was landed, whatever it contained."""
    execute(w, CREATE_RUNS)
    execute(w, f"""
        MERGE INTO {RUNS_TABLE} AS t
        USING (SELECT :batch AS snapshot_batch, CAST(:objects AS BIGINT) AS objects_landed,
                      CAST(:metadata AS BIGINT) AS metadata_landed) AS s
        ON t.snapshot_batch = s.snapshot_batch
        WHEN MATCHED THEN UPDATE SET t.objects_landed = s.objects_landed,
            t.metadata_landed = s.metadata_landed, t.landed_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT (snapshot_batch, objects_landed, metadata_landed, landed_at)
            VALUES (s.snapshot_batch, s.objects_landed, s.metadata_landed, current_timestamp())
    """, {"batch": batch, "objects": str(objects), "metadata": str(metadata)})


def load(w, table: str, create: str, columns: list[tuple[str, str]], key: list[str],
         rows: list[tuple], batch: str) -> dict:
    stage = f"{table}_stage"
    execute(w, create)
    execute(w, f"CREATE OR REPLACE TABLE {stage} ("
               + ", ".join(f"{n} {t}" for n, t in columns) + ")")
    for start in range(0, len(rows), 50):
        statement, params = insert_chunk(stage, columns, rows[start:start + 50])
        execute(w, statement, params)
    names = [n for n, _ in columns]
    on = " AND ".join(f"t.{k} = s.{k}" for k in key)
    updates = ", ".join(f"t.{n} = s.{n}" for n in names if n not in key)
    execute(w, f"""
        MERGE INTO {table} AS t
        USING (SELECT {', '.join(names)} FROM {stage}) AS s
        ON {on}
        WHEN MATCHED THEN UPDATE SET {updates}, t.landed_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT ({', '.join(names)}, landed_at)
            VALUES ({', '.join('s.' + n for n in names)}, current_timestamp())
    """)
    execute(w, f"DROP TABLE IF EXISTS {stage}")
    counted = execute(w, f"SELECT count(*) FROM {table} WHERE snapshot_batch = :batch",
                      {"batch": batch})
    return {"table": table, "rows_in_snapshot": len(rows),
            "rows_in_table": int(counted[0][0])}


def insert_chunk(stage: str, columns: list[tuple[str, str]],
                 chunk: list[tuple]) -> tuple[str, list]:
    """One INSERT with a named marker per value: the REST statement API has no ? markers."""
    from databricks.sdk.service.sql import StatementParameterListItem

    tuples, params = [], []
    for i, row in enumerate(chunk):
        markers = []
        for (name, sql_type), value in zip(columns, row):
            marker = f"{name}_{i}"
            markers.append(f":{marker}")
            params.append(StatementParameterListItem(
                name=marker, type=sql_type,
                value=None if value is None else str(value)))
        tuples.append("(" + ", ".join(markers) + ")")
    return f"INSERT INTO {stage} VALUES " + ", ".join(tuples), params


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", required=True,
                    help="immutable input snapshot written by scripts/tp_seed/gen_p3_fixture.py")
    ap.add_argument("--batch", required=True, help="snapshot batch id, e.g. the fixture ns")
    ap.add_argument("--volume-dir", default=None,
                    help=f"governed landing directory (default {DEFAULT_VOLUME}/<batch>)")
    ap.add_argument("--skip-upload", action="store_true",
                    help="the snapshot is already in the volume; land from the local copy only")
    args = ap.parse_args(argv)

    snapshot = Path(args.snapshot_dir)
    verify_snapshot(snapshot)
    volume_dir = args.volume_dir or f"{DEFAULT_VOLUME}/{args.batch}"

    w = client()
    uploaded = [] if args.skip_upload else upload(w, snapshot, volume_dir)
    result = {
        "batch": args.batch,
        "volume_files": uploaded,
        "inventory": load(
            w, INVENTORY_TABLE, CREATE_INVENTORY,
            [("snapshot_batch", "STRING"), ("object_key", "STRING"),
             ("size_bytes", "BIGINT")],
            ["snapshot_batch", "object_key"],
            inventory_rows(snapshot, args.batch), args.batch),
        "metadata": load(
            w, METADATA_TABLE, CREATE_METADATA,
            [("snapshot_batch", "STRING"), ("file_id", "STRING"), ("s3_key", "STRING"),
             ("owner_id", "STRING"), ("size_bytes", "BIGINT")],
            ["snapshot_batch", "file_id"],
            metadata_rows(snapshot, args.batch), args.batch),
    }
    record_run(w, args.batch, result["inventory"]["rows_in_table"],
               result["metadata"]["rows_in_table"])
    json.dump(result, sys.stdout, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
