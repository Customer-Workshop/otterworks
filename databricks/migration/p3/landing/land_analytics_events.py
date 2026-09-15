#!/usr/bin/env python3
"""Land the analytics event snapshot durably in bronze, replacing a destructive read.

    python3 databricks/migration/p3/landing/land_analytics_events.py \
        --snapshot-dir /path/to/fixtures/p3probe --batch p3probe --run-date 2026-09-15

`analytics_daily.py` consumes its input: every SQS batch it reads is deleted immediately
after being read, and nothing keeps a copy. A run that fails after the delete has destroyed
the day. P3-D01 replaces that with a durable landing: the events are written once into
`ow_tp.bronze.analytics_events_raw`, and every downstream recomputation reads the table, so
a rerun reads the same input the first run read.

Two properties this loader has to hold:

* **Idempotent.** Landing the same batch twice leaves the table byte-identical. Rows are
  keyed by `event_uid` = `<batch>:<stream>:<ordinal>`, which is a property of the snapshot
  and not of the run, and the load is a MERGE.
* **Order preserving.** The legacy concatenates `sqs_events + dynamo_events` and its
  `top_users` output is ordered by count with ties broken by first appearance in that list,
  so the order is observable output. `ingest_ordinal` records it: SQS records in queue
  order, then DynamoDB records in scan order. Nothing downstream may invent an order.

  The DynamoDB half of that order is the order the *scan* returns, which is a property of
  the table and not of the snapshot file: the two differ, and the difference is visible in
  the byte order of `hourly_breakdown.json.gz` and `top_users.jsonl.gz`. So the snapshot
  carries `analytics_source_order.json`, the event ids in the order the source handed them
  over, captured by `exports/capture_source_order.py` at extraction time. Events the
  recorded scan did not return (a record dated outside the scanned day) keep snapshot-file
  order behind the ones it did; the day the legacy read is sequenced exactly as it read it.

The payload is stored verbatim as JSON text. The events are heterogeneous by construction
(the attribution field varies per record, `sizeBytes` is present only on uploads), so typing
them here would mean deciding at landing time what the contract says, which belongs in the
silver SQL where it can be read next to the legacy behaviour it reproduces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

RAW_TABLE = "ow_tp.bronze.analytics_events_raw"
STAGE_TABLE = "ow_tp.bronze.analytics_events_raw_stage"
DEFAULT_VOLUME = "/Volumes/ow_tp/bronze/landing/analytics"
WAREHOUSE = "565cd2fd713738c4"
# The order the legacy concatenates them in; ordinals are assigned in this order.
STREAMS = (("sqs", "analytics_sqs_events.json"),
           ("dynamodb", "analytics_dynamodb_events.json"))
SOURCE_ORDER = "analytics_source_order.json"

CREATE_RAW = f"""
CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
  event_uid STRING NOT NULL COMMENT 'batch:stream:ordinal - a property of the snapshot, so a re-land is a no-op',
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot this record came from',
  source_stream STRING NOT NULL COMMENT 'sqs | dynamodb',
  ingest_ordinal BIGINT NOT NULL COMMENT 'position in the legacy concatenation: all sqs records, then all dynamodb records',
  event_date STRING COMMENT 'the records own event_date attribute, verbatim; the DynamoDB scan filter reads it',
  payload STRING NOT NULL COMMENT 'the event as landed, verbatim JSON',
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Durable landing for the analytics event stream (P3-D01). Replaces analytics_daily.py consuming and deleting its SQS input.'
"""


def client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def execute(w, statement: str, parameters=None) -> list[list[str]]:
    """Run one statement on the migration warehouse, binding named markers only.

    Values are always bound as parameters, never formatted into the statement text, so a
    payload cannot change the shape of the statement it is landed by.
    """
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


def source_order(snapshot: Path) -> list[str] | None:
    """The event ids in the order the source returned them, if the snapshot recorded it."""
    path = snapshot / SOURCE_ORDER
    if not path.exists():
        return None
    recorded = json.loads(path.read_text())
    order = recorded["event_ids"] if isinstance(recorded, dict) else recorded
    if len(set(order)) != len(order):
        raise SystemExit(f"{path} repeats an event id; it is a sequence, not a bag")
    return order


def in_source_order(events: list[dict], order: list[str] | None) -> list[dict]:
    """Sequence the scanned events as the source returned them, file order behind them.

    A recorded id the snapshot does not hold means the two describe different extractions,
    which would silently sequence the wrong day, so it fails rather than being skipped.
    """
    if order is None:
        return events
    by_id = {event["event_id"]: event for event in events}
    missing = [event_id for event_id in order if event_id not in by_id]
    if missing:
        raise SystemExit(f"{len(missing)} ids in {SOURCE_ORDER} are not in the snapshot "
                         f"(first: {missing[0]}); the order was captured from a different "
                         "extraction than this snapshot holds")
    scanned = [by_id[event_id] for event_id in order]
    recorded = set(order)
    return scanned + [event for event in events if event["event_id"] not in recorded]


def snapshot_rows(snapshot: Path, batch: str) -> list[tuple[str, str, str, int, str, str]]:
    """(event_uid, batch, stream, ordinal, event_date, payload) in legacy concatenation order."""
    rows = []
    ordinal = 0
    order = source_order(snapshot)
    for stream, name in STREAMS:
        events = json.loads((snapshot / name).read_text())
        if stream == "dynamodb":
            events = in_source_order(events, order)
        for event in events:
            payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
            rows.append((f"{batch}:{stream}:{ordinal}", batch, stream, ordinal,
                         event.get("event_date"), payload))
            ordinal += 1
    return rows


def verify_snapshot(snapshot: Path) -> None:
    """Refuse a snapshot that does not match its own manifest.

    The snapshot is the declared input of both sides of the recon. Landing a drifted copy
    would silently compare the target against input the legacy never saw.
    """
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{snapshot} has no manifest.json; regenerate it with gen_p3_fixture.py")
    checksums = json.loads(manifest_path.read_text()).get("checksums")
    if not checksums:
        raise SystemExit(f"{manifest_path} carries no checksums; regenerate the fixture")
    problems = []
    for _, name in STREAMS:
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
    """Copy the snapshot files into the governed volume, overwriting with identical bytes.

    The manifest travels with them: the job task lands from the volume copy with
    `--skip-upload`, and `verify_snapshot` has to be able to check that copy against the
    same checksums the local run checked, not trust it because it is in a volume.
    """
    written = []
    for _, name in (*STREAMS, ("manifest", "manifest.json"), ("order", SOURCE_ORDER)):
        if not (snapshot / name).exists():
            continue
        target = f"{volume_dir}/{name}"
        w.files.upload(target, (snapshot / name).open("rb"), overwrite=True)
        written.append(target)
    return written


def load(w, rows: list[tuple], batch: str) -> dict:
    execute(w, CREATE_RAW)
    execute(w, f"CREATE OR REPLACE TABLE {STAGE_TABLE} ("
               "event_uid STRING, snapshot_batch STRING, source_stream STRING, "
               "ingest_ordinal BIGINT, event_date STRING, payload STRING)")
    for start in range(0, len(rows), 50):
        statement, params = insert_chunk(rows[start:start + 50])
        execute(w, statement, params)
    execute(w, f"""
        MERGE INTO {RAW_TABLE} AS t
        USING (SELECT event_uid, snapshot_batch, source_stream, ingest_ordinal, event_date,
                      payload FROM {STAGE_TABLE}) AS s
        ON t.event_uid = s.event_uid
        WHEN MATCHED AND t.payload <> s.payload THEN UPDATE SET
            t.snapshot_batch = s.snapshot_batch, t.source_stream = s.source_stream,
            t.ingest_ordinal = s.ingest_ordinal, t.event_date = s.event_date,
            t.payload = s.payload, t.landed_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT (event_uid, snapshot_batch, source_stream, ingest_ordinal,
                                      event_date, payload, landed_at)
            VALUES (s.event_uid, s.snapshot_batch, s.source_stream, s.ingest_ordinal,
                    s.event_date, s.payload, current_timestamp())
    """)
    execute(w, f"DROP TABLE IF EXISTS {STAGE_TABLE}")
    counted = execute(w, f"SELECT count(*) FROM {RAW_TABLE} WHERE snapshot_batch = :batch",
                      {"batch": batch})
    return {"table": RAW_TABLE, "batch": batch, "rows_in_snapshot": len(rows),
            "rows_in_table": int(counted[0][0])}


def insert_chunk(chunk: list[tuple]) -> tuple[str, list]:
    """One INSERT with a named marker per value: the REST statement API has no ? markers."""
    from databricks.sdk.service.sql import StatementParameterListItem

    columns = [("event_uid", "STRING"), ("snapshot_batch", "STRING"),
               ("source_stream", "STRING"), ("ingest_ordinal", "BIGINT"),
               ("event_date", "STRING"), ("payload", "STRING")]
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
    return f"INSERT INTO {STAGE_TABLE} VALUES " + ", ".join(tuples), params


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
    result = load(w, snapshot_rows(snapshot, args.batch), args.batch)
    result["volume_files"] = uploaded
    result["dynamodb_order"] = ("source_scan" if source_order(snapshot) is not None
                               else "snapshot_file")
    json.dump(result, sys.stdout, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
