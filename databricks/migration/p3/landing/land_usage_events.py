"""Land the usage-event NDJSON snapshot in bronze.

    python3 databricks/migration/p3/landing/land_usage_events.py \
        --snapshot-dir /path/to/fixtures/p3probe --batch p3probe

`UsageRollupJob.scala` bulk-loads the whole NDJSON file into memory and aggregates it in
one pass. P3-D06 replaces that with SQL on Delta, so the events are landed here once and
the rollup is a query over the landed copy.

Two shapes of the input are contract and are preserved rather than cleaned up on the way
in:

  * the vocabulary is the DOTTED analytics-service one ('document.created'), not the
    snake_case vocabulary analytics_daily consumes (F-0.9). `event_type` is stored exactly
    as the record carried it;
  * `metadata['bytes']` is kept as the raw string. The Scala reads it with a `Try(...
    .toLong).getOrElse(0L)`, so a missing or non-numeric value contributes zero to that
    one event and nothing else. Parsing it here would turn a per-event zero into a NULL
    the rollup would have to guess about.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

EVENTS_TABLE = "ow_tp.bronze.usage_events_raw"
DEFAULT_VOLUME = "/Volumes/ow_tp/bronze/landing/analytics/usage"
WAREHOUSE = "565cd2fd713738c4"
FILES = ("usage-events.ndjson",)

CREATE_EVENTS = f"""
CREATE TABLE IF NOT EXISTS {EVENTS_TABLE} (
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot this event came from',
  source_line BIGINT NOT NULL COMMENT 'line of usage-events.ndjson this row came from; the landing key, because the legacy aggregates every record and does not require event_id to be unique',
  event_id STRING NOT NULL,
  event_type STRING NOT NULL COMMENT 'dotted analytics-service vocabulary, stored verbatim: document.created, storage.allocated, ...',
  user_id STRING COMMENT 'counted distinctly by active_users, unattributed values included as themselves',
  resource_id STRING,
  resource_type STRING,
  event_ts STRING NOT NULL COMMENT 'ISO-8601 instant; a record that carried epoch millis as a JSON number is normalised here the way the Scala Instant format reads it',
  bytes_attr STRING COMMENT "metadata['bytes'] as written. NULL means the record carried none, which the legacy reads as zero for that event",
  metadata_json STRING NOT NULL COMMENT 'the whole metadata map as canonical JSON',
  landed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Durable copy of the usage-event NDJSON UsageRollupJob.scala reads. The rollup is recomputed from here, never from the file.'
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

    The Scala job ran against this exact file; a drifted copy would compare the target
    against input the legacy never saw.
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


REQUIRED = ("eventId", "eventType", "userId", "resourceId", "resourceType", "metadata",
            "timestamp")


def instant(value, where: str) -> str:
    """The instant as `AnalyticsEventJsonProtocol.instantFormat` reads it.

    A JSON string is parsed as ISO-8601 and a JSON number is epoch milliseconds; anything
    else is a deserialization error that takes the whole file down. Normalising the number
    here is what keeps the rollup's UTC day right: the landed value is text, so a raw
    '1709251200000' would reach `to_timestamp` as a formatted timestamp and miss its day.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemExit(f"{where}: timestamp {value!r} is neither an ISO-8601 string nor "
                         "epoch millis; the legacy fails to load the file at all")
    millis = int(value)
    moment = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%S")
    fraction = millis % 1000
    return f"{stamp}.{fraction:03d}Z" if fraction else f"{stamp}Z"


def event_rows(snapshot: Path, batch: str) -> list[tuple]:
    """One row per NDJSON record, keyed by its line rather than by its event id.

    Blank lines and '#' comments are skipped because `EventLoader.fromString` skips them;
    anything else that fails to parse is fatal here, as it is there. `AnalyticsEvent` is a
    seven-field case class read with `jsonFormat7`, so every field is required and metadata
    is a string-to-string map: a record missing one does not land as a NULL, it stops the
    load, because the legacy never aggregates that file at all.
    """
    rows = []
    text = (snapshot / "usage-events.ndjson").read_text()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"usage-events.ndjson:{number}: {exc}; the legacy loader "
                             "raises on the same line rather than skipping it") from exc
        where = f"usage-events.ndjson:{number}"
        missing = [f for f in REQUIRED if f not in record or record[f] is None]
        if missing:
            raise SystemExit(f"{where}: missing {', '.join(missing)}; AnalyticsEvent "
                             "requires all seven fields and the legacy fails to load the "
                             "file at all without them")
        strings = [f for f in ("eventId", "eventType", "userId", "resourceId", "resourceType")
                   if not isinstance(record[f], str)]
        if strings:
            raise SystemExit(f"{where}: {', '.join(strings)} must be a JSON string")
        metadata = record["metadata"]
        if not isinstance(metadata, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
            raise SystemExit(f"{where}: metadata must be a string-to-string map; "
                             "Map[String, String] does not read anything else")
        rows.append((batch, number, record["eventId"], record["eventType"], record["userId"],
                     record["resourceId"], record["resourceType"],
                     instant(record["timestamp"], where), metadata.get("bytes"),
                     json.dumps(metadata, sort_keys=True, separators=(",", ":"))))
    return rows


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
    columns = [("snapshot_batch", "STRING"), ("source_line", "BIGINT"), ("event_id", "STRING"),
               ("event_type", "STRING"), ("user_id", "STRING"), ("resource_id", "STRING"),
               ("resource_type", "STRING"), ("event_ts", "STRING"),
               ("bytes_attr", "STRING"), ("metadata_json", "STRING")]
    # Keyed on the line, not the event id: the same id can legitimately appear twice and the
    # legacy counts it twice, where a MERGE on the id would fail the rerun as ambiguous.
    key = ["snapshot_batch", "source_line"]
    stage = f"{EVENTS_TABLE}_stage"
    execute(w, CREATE_EVENTS)
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
    print(json.dumps({"batch": args.batch, "volume_files": uploaded,
                      "events": load(w, rows, args.batch)}, indent=2))
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
