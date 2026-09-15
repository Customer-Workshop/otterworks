"""Land the audit-event table snapshot in bronze.

A snapshot is produced in two steps, and landing needs both:

    python3 scripts/tp_seed/gen_p3_fixture.py --ns p3probe ...          # the records
    python3 databricks/migration/p3/exports/capture_legacy_audit_objects.py \
        --snapshot /path/to/fixtures/p3probe --run-date <ds>            # the scan order
    python3 databricks/migration/p3/landing/land_audit_events.py \
        --snapshot-dir /path/to/fixtures/p3probe --batch p3probe

The generator writes the records; it cannot write the scan order. That order, and each
record's attribute order, are what DynamoDB hands back for one shape at a time, so they
are read off the seeded table by the capture step and not invented by the generator.

`audit_archive_weekly.py` scans DynamoDB live and then tries to delete what it scanned, so
its input changes underneath it. P3-D04 splits the two: the scan is landed here as a
durable copy, the archive set is computed in SQL from the landed copy, and nothing in the
converted unit deletes from the source.

Three record shapes live in the same table and all three are contract (F-0.4/a/b):

  A-estate  the shape the audit-service actually writes: `Id` / `Timestamp`, no lowercase
            `timestamp`. The legacy's scan filters on `timestamp`, which DynamoDB reads as
            "attribute absent", so these records never match and are never archived.
  A-tsonly  lowercase `timestamp`, no `event_id`.
  A-full    lowercase `timestamp` and `event_id`.

`ts_attr` is the lowercase `timestamp` attribute and only that attribute: it is NULL for a
record that does not carry one. Filling it from `Timestamp` would archive the A-estate
records the legacy leaves alone, which is the whole of F-0.4. The other-cased value is kept
in the payload, where it can be read without being mistaken for the filter column.

The payload is stored as canonical JSON (sorted keys, compact separators) so the archived
body compares as a string on both sides of the recon.

Two more columns exist for the file export, and only for it. The legacy archive object is
one `json.dumps(record)` per line, in scan order, with each record's attributes in the
order DynamoDB handed them over -- neither the snapshot file's order nor sorted order. Both
of those are properties of the source table, not of the snapshot, so they are read off the
scan itself and written next to the snapshot as `audit_source_order.json` -- by
`scripts/tp_seed/gen_p3_fixture.py` when it seeds the fixture, and again by
`exports/capture_legacy_audit_objects.py` when the legacy objects are re-frozen -- then
landed here as `scan_ordinal` and `payload_raw_json`. Canonical
`payload_json` stays the column the recon compares; the raw one exists so the exported
bytes can be the legacy's bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EVENTS_TABLE = "ow_tp.bronze.p3_audit_events_raw"
RUNS_TABLE = "ow_tp.bronze.p3_audit_landing_runs"
DEFAULT_VOLUME = "/Volumes/ow_tp/bronze/landing/analytics"
WAREHOUSE = "565cd2fd713738c4"
FILES = ("audit_events.json",)
ORDER_FILE = "audit_source_order.json"

CREATE_EVENTS = f"""
CREATE TABLE IF NOT EXISTS {EVENTS_TABLE} (
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot this scan came from',
  probe_shape STRING NOT NULL COMMENT 'A-estate | A-tsonly | A-full; part of the key because the same logical event exists in more than one shape',
  event_id STRING NOT NULL COMMENT 'event_id when the record carries one, else its id; the archive is keyed on it',
  ts_attr STRING COMMENT 'the lowercase timestamp attribute and only that one. NULL means the record has none, which is what makes the legacy scan skip it',
  payload_json STRING NOT NULL COMMENT 'the whole record as canonical JSON: the archived body, not a projection of it',
  scan_ordinal INT COMMENT 'position of this record in the source scan; NULL for a record the scan did not return',
  payload_raw_json STRING COMMENT 'the record serialized as the legacy serializes it: source attribute order, json.dumps defaults',
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Durable copy of the otterworks-audit-events scan audit_archive_weekly.py would have made live. Source of the archive set; never written back to DynamoDB (P3-D04).'
"""

CREATE_RUNS = f"""
CREATE TABLE IF NOT EXISTS {RUNS_TABLE} (
  snapshot_batch STRING NOT NULL,
  events_landed BIGINT NOT NULL,
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'One row per landed snapshot. A table that legitimately holds no old events lands zero rows, so the row count alone cannot tell an empty scan from a scan that never arrived; this receipt can.'
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

    The legacy ran against a clone of this snapshot; a drifted copy would compare the
    target against input the legacy never saw.
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


def add_export_columns(w) -> None:
    """Give a table created before the export columns those columns.

    CREATE TABLE IF NOT EXISTS leaves an existing table alone, so a workspace that landed
    this snapshot before the export existed would otherwise merge into columns that are
    not there. The re-landed batch fills them; rows from other batches keep NULL, and the
    exporter refuses to export a batch whose archived rows carry NULL.
    """
    columns = {row[0] for row in execute(w, f"SHOW COLUMNS IN {EVENTS_TABLE}")}
    if "scan_ordinal" not in columns:
        execute(w, f"ALTER TABLE {EVENTS_TABLE} ADD COLUMN scan_ordinal INT COMMENT "
                   "'position of this record in the source scan' AFTER payload_json")
    if "payload_raw_json" not in columns:
        execute(w, f"ALTER TABLE {EVENTS_TABLE} ADD COLUMN payload_raw_json STRING "
                   "COMMENT 'the record as the legacy serializes it' AFTER scan_ordinal")


def upload(w, snapshot: Path, volume_dir: str) -> list[str]:
    written = []
    for name in (*FILES, ORDER_FILE, "manifest.json"):
        target = f"{volume_dir}/{name}"
        w.files.upload(target, (snapshot / name).open("rb"), overwrite=True)
        written.append(target)
    return written


def source_order(snapshot: Path) -> dict[str, dict[str, tuple[int, list[str]]]]:
    """Scan position and source attribute order per shape, per record.

    Required, not optional: without it the landed rows cannot reproduce the archive
    object's bytes, and a unit that silently landed without them would fail the byte gate
    much later with a much worse error message.
    """
    path = snapshot / ORDER_FILE
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. It carries the order the source scan returned the records "
            "in and the attribute order of each one, which the exported archive bytes are "
            "made of. Snapshots from scripts/tp_seed/gen_p3_fixture.py carry it; an older "
            "one gains it from exports/capture_legacy_audit_objects.py.")
    captured = json.loads(path.read_text())["shapes"]
    return {shape: {entry["event_id"]: (position, entry["attribute_order"])
                    for position, entry in enumerate(entries)}
            for shape, entries in captured.items()}


def raw_payload(record: dict, attribute_order: list[str], shape: str,
                identity: str) -> str:
    """`json.dumps(record)` with the attributes in the order the source returned them."""
    if sorted(attribute_order) != sorted(record):
        raise SystemExit(
            f"{shape}/{identity}: the source scan returned attributes "
            f"{sorted(attribute_order)} and the snapshot carries {sorted(record)}; the "
            "captured order describes a different record")
    return json.dumps({name: record[name] for name in attribute_order})


def event_rows(snapshot: Path, batch: str) -> list[tuple]:
    """One row per record per shape, with the record kept whole."""
    by_shape = json.loads((snapshot / "audit_events.json").read_text())
    scanned = source_order(snapshot)
    rows = []
    for shape, records in sorted(by_shape.items()):
        positions = scanned.get(shape, {})
        for record in records:
            identity = record.get("event_id") or record.get("id") or record.get("Id")
            if not identity:
                raise SystemExit(
                    f"{shape}: a record carries neither event_id, id nor Id, so it cannot be "
                    "keyed; the archive would silently collapse rows together")
            position, order = positions.get(identity, (None, None))
            rows.append((batch, shape, identity, record.get("timestamp"),
                         json.dumps(record, sort_keys=True, separators=(",", ":")),
                         None if position is None else position,
                         None if order is None
                         else raw_payload(record, order, shape, identity)))
    return rows


def record_run(w, batch: str, events: int) -> None:
    """Receipt that this batch was landed, whatever it contained."""
    execute(w, CREATE_RUNS)
    execute(w, f"""
        MERGE INTO {RUNS_TABLE} AS t
        USING (SELECT :batch AS snapshot_batch,
                      CAST(:events AS BIGINT) AS events_landed) AS s
        ON t.snapshot_batch = s.snapshot_batch
        WHEN MATCHED THEN UPDATE SET t.events_landed = s.events_landed,
            t.landed_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT (snapshot_batch, events_landed, landed_at)
            VALUES (s.snapshot_batch, s.events_landed, current_timestamp())
    """, {"batch": batch, "events": str(events)})


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


def load(w, rows: list[tuple], batch: str) -> dict:
    columns = [("snapshot_batch", "STRING"), ("probe_shape", "STRING"),
               ("event_id", "STRING"), ("ts_attr", "STRING"), ("payload_json", "STRING"),
               ("scan_ordinal", "INT"), ("payload_raw_json", "STRING")]
    key = ["snapshot_batch", "probe_shape", "event_id"]
    stage = f"{EVENTS_TABLE}_stage"
    execute(w, CREATE_EVENTS)
    add_export_columns(w)
    execute(w, f"CREATE OR REPLACE TABLE {stage} ("
               + ", ".join(f"{n} {t}" for n, t in columns) + ")")
    for start in range(0, len(rows), 25):
        statement, params = insert_chunk(stage, columns, rows[start:start + 25])
        execute(w, statement, params)
    names = [n for n, _ in columns]
    on = " AND ".join(f"t.{k} = s.{k}" for k in key)
    updates = ", ".join(f"t.{n} = s.{n}" for n in names if n not in key)
    execute(w, f"""
        MERGE INTO {EVENTS_TABLE} AS t
        USING (SELECT {', '.join(names)} FROM {stage}) AS s
        ON {on}
        WHEN MATCHED THEN UPDATE SET {updates}, t.landed_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT ({', '.join(names)}, landed_at)
            VALUES ({', '.join('s.' + n for n in names)}, current_timestamp())
    """)
    execute(w, f"DROP TABLE IF EXISTS {stage}")
    counted = execute(w, f"SELECT count(*) FROM {EVENTS_TABLE} WHERE snapshot_batch = :batch",
                      {"batch": batch})
    return {"table": EVENTS_TABLE, "rows_in_snapshot": len(rows),
            "rows_in_table": int(counted[0][0])}


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
    rows = event_rows(snapshot, args.batch)
    result = {"batch": args.batch, "volume_files": uploaded, "events": load(w, rows, args.batch)}
    record_run(w, args.batch, result["events"]["rows_in_table"])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
