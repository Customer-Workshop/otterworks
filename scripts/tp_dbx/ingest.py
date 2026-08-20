#!/usr/bin/env python3
"""Databricks landing job replacing etl/legacy-extra/jobs/sftp_ingest_poll.ksh.

Contract: docs/tech-partnerships/contracts/sftp_ingest_poll.json (ING-01..ING-08).

The legacy poller branched on hostname for its paths, "settled" a transfer by
comparing `wc -c` twice one second apart, suppressed every failure with
`2>/dev/null || true`, archived a timestamped copy forever, and never removed
its lock file. This tool lands drop files byte-identically into the namespace's
landing volume with an explicit completion protocol instead:

  stage upload -> checksum handshake -> final upload -> checksum handshake
  -> manifest commit (MERGE, insert-if-absent)

A file is only visible downstream once its manifest row exists, so a partial
transfer is never visible (ING-02). The manifest MERGE keys on file name, so
overlapping runs and mainframe re-sends land each file exactly once (ING-04,
ING-05, ING-A3). Everything is parameterised by --ns/--catalog; there is no
hostname branching and no absolute environment path (ING-03). Any unreadable,
still-changing, or checksum-divergent file fails the run with the file named
(ING-06, ING-A1). Landed objects and manifest rows carry a retention class
enforced by the `retention` command (ING-07).

  provision   create the manifest and ops tables for the namespace
  run         land CUSTBILL*.dat files from a drop directory
  verify      re-download every landed object and re-check size and sha256
  retention   enforce the declared retention class (delete expired objects+rows)
  job         create/refresh the (PAUSED) ow_tp_ingest_<ns> verification job
  run-job     trigger the verification job once and report the outcome
  status      summarise the namespace's landed state
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import Databricks, DbxError, require_ident, require_ns

NOTEBOOK_DIR = "/Shared/ow_tp"
RETENTION_CLASS = "landing-90d"
RETENTION_DAYS = 90


class Names:
    def __init__(self, catalog: str, ns: str):
        self.catalog = require_ident(catalog, "catalog")
        self.ns = require_ns(ns)

    @property
    def landing_root(self) -> str:
        return f"/Volumes/{self.catalog}/bronze/landing/{self.ns}"

    @property
    def ingest_dir(self) -> str:
        return f"{self.landing_root}/ingest"

    def staging_dir(self, run_id: str) -> str:
        return f"{self.landing_root}/staging/{run_id}"

    @property
    def manifest(self) -> str:
        return f"{self.catalog}.bronze.custbill_landed_{self.ns}"

    @property
    def ingest_runs(self) -> str:
        return f"{self.catalog}.ops.ingest_runs_{self.ns}"


def names(args) -> Names:
    return Names(args.catalog, args.ns)


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --- provision ---------------------------------------------------------------
def cmd_provision(dbx: Databricks, args) -> int:
    n = names(args)
    dbx.sql_ok(f"""CREATE TABLE IF NOT EXISTS {n.manifest} (
          file_name STRING COMMENT 'CUSTBILL drop file name, the landing identity key',
          size_bytes BIGINT COMMENT 'Byte size of the landed object',
          sha256 STRING COMMENT 'sha256 of the landed bytes, verified by download after upload',
          landed_path STRING COMMENT 'Volume path of the landed object',
          retention_class STRING COMMENT '{RETENTION_CLASS}: object and row deleted {RETENTION_DAYS} days after landing by the retention command',
          first_landed_at TIMESTAMP,
          landed_by_run STRING)
        USING DELTA
        COMMENT 'Landed CUSTBILL files for ns={n.ns}: one row per file, committed only after the checksum handshake, so this table is the downstream visibility gate'""")
    dbx.sql_ok(f"""CREATE TABLE IF NOT EXISTS {n.ingest_runs} (
          run_id STRING, recorded_at TIMESTAMP,
          file_name STRING COMMENT 'NULL on the run_summary row',
          size_bytes BIGINT, sha256 STRING,
          action STRING COMMENT 'landed | skipped_duplicate | skipped_concurrent | run_summary',
          retention_class STRING,
          detail STRING)
        USING DELTA
        COMMENT 'Per-file ingest audit for ns={n.ns}: sha256 recorded per landed file, plus one run_summary row per run (files=0 for an empty drop)'""")
    print(f"provisioned {n.manifest} and {n.ingest_runs}")
    print(f"landing dir: {n.ingest_dir}")
    return 0


# --- run ----------------------------------------------------------------------
def snapshot(path: Path) -> tuple[bytes, str]:
    """Read the drop file twice; a transfer still in progress shows a different
    digest and fails the run with the file named, replacing the legacy
    size-compared-twice settle heuristic."""
    first = path.read_bytes()
    time.sleep(0.2)
    second = path.read_bytes()
    if sha256(first) != sha256(second):
        raise DbxError(f"{path.name}: bytes changed while reading (transfer still in progress)")
    return first, sha256(first)


def existing_manifest_row(dbx: Databricks, n: Names, name: str) -> dict | None:
    rows = dbx.sql_ok(
        f"SELECT file_name, size_bytes, sha256 FROM {n.manifest} WHERE file_name = '{esc(name)}'"
    ).dicts()
    return rows[0] if rows else None


def handshake_put(dbx: Databricks, target: str, payload: bytes, digest: str, label: str) -> None:
    dbx.put_file(target, payload)
    echoed = dbx.get_file(target)
    if sha256(echoed) != digest:
        raise DbxError(f"{label}: checksum handshake failed at {target} "
                       f"(uploaded {digest}, read back {sha256(echoed)})")


def commit_manifest(dbx: Databricks, n: Names, name: str, size: int, digest: str,
                    landed_path: str, run_id: str) -> bool:
    """Insert-if-absent, keyed on file name. Delta MERGE serialises concurrent
    writers, so exactly one overlapping run inserts; the loser sees a write
    conflict, retries, finds the row, and reports skipped_concurrent."""
    merge = (
        f"MERGE INTO {n.manifest} t USING (SELECT '{esc(name)}' AS file_name) s "
        f"ON t.file_name = s.file_name "
        f"WHEN NOT MATCHED THEN INSERT (file_name, size_bytes, sha256, landed_path, "
        f"retention_class, first_landed_at, landed_by_run) VALUES ('{esc(name)}', {size}, "
        f"'{digest}', '{esc(landed_path)}', '{RETENTION_CLASS}', current_timestamp(), '{run_id}')"
    )
    for attempt in range(5):
        result = dbx.sql(merge)
        if result.ok:
            inserted = int(result.dicts()[0].get("num_inserted_rows", 0))
            return inserted == 1
        if "Concurrent" not in result.error and "conflict" not in result.error.lower():
            raise DbxError(f"manifest commit failed for {name}: {result.error}")
        time.sleep(1 + attempt)
    raise DbxError(f"manifest commit for {name} kept conflicting after 5 attempts")


def record_runs(dbx: Databricks, n: Names, rows: list[tuple]) -> None:
    values = ",".join(
        f"('{run_id}', current_timestamp(), {name}, {size}, {digest}, '{action}', "
        f"{retention}, '{esc(detail)}')"
        for run_id, name, size, digest, action, retention, detail in rows
    )
    dbx.sql_ok(f"INSERT INTO {n.ingest_runs} VALUES {values}")


def lit(value: str | None) -> str:
    return "NULL" if value is None else f"'{esc(value)}'"


def cmd_run(dbx: Databricks, args) -> int:
    n = names(args)
    run_id = uuid.uuid4().hex[:12]
    drop = Path(args.drop)
    if not drop.is_dir():
        raise SystemExit(f"drop directory does not exist: {drop}")
    candidates = sorted(drop.glob("CUSTBILL*.dat"))
    audit: list[tuple] = []
    landed = skipped = 0
    staging = n.staging_dir(run_id)
    failure: DbxError | None = None
    try:
        for path in candidates:
            name = path.name
            try:
                payload, digest = snapshot(path)
            except OSError as exc:
                raise DbxError(f"{name}: unreadable drop file: {exc}")
            prior = existing_manifest_row(dbx, n, name)
            if prior:
                if prior["sha256"] == digest:
                    skipped += 1
                    audit.append((run_id, lit(name), len(payload), lit(digest),
                                  "skipped_duplicate", lit(RETENTION_CLASS),
                                  "already landed with identical sha256"))
                    if not args.keep_source:
                        path.unlink()
                    continue
                raise DbxError(
                    f"{name}: drop bytes (sha256 {digest}) do not match the already-landed "
                    f"object (sha256 {prior['sha256']}); refusing to overwrite or double-land")
            final = f"{n.ingest_dir}/{name}"
            handshake_put(dbx, f"{staging}/{name}", payload, digest, name)
            handshake_put(dbx, final, payload, digest, name)
            if commit_manifest(dbx, n, name, len(payload), digest, final, run_id):
                landed += 1
                audit.append((run_id, lit(name), len(payload), lit(digest), "landed",
                              lit(RETENTION_CLASS), f"landed at {final}"))
            else:
                skipped += 1
                audit.append((run_id, lit(name), len(payload), lit(digest),
                              "skipped_concurrent", lit(RETENTION_CLASS),
                              "an overlapping run committed this file first"))
            if not args.keep_source:
                path.unlink()
    except DbxError as exc:
        failure = exc
    finally:
        for entry in dbx.list_dir(staging):
            dbx.delete_file(entry.get("path", ""))
        dbx.delete_dir(staging)
    status = "failed" if failure else "success"
    detail = f"files={landed} skipped={skipped} scanned={len(candidates)} status={status}"
    if failure:
        detail += f" error={failure}"
    audit.append((run_id, "NULL", "NULL", "NULL", "run_summary", "NULL", detail))
    record_runs(dbx, n, audit)
    if failure:
        raise failure
    print(f"run {run_id}: scanned={len(candidates)} landed={landed} skipped={skipped}")
    return 0


# --- verify -------------------------------------------------------------------
def cmd_verify(dbx: Databricks, args) -> int:
    n = names(args)
    rows = dbx.sql_ok(
        f"SELECT file_name, size_bytes, sha256, landed_path FROM {n.manifest} ORDER BY file_name"
    ).dicts()
    listed = {e["path"].rsplit("/", 1)[-1] for e in dbx.list_dir(n.ingest_dir)}
    failures = []
    for row in rows:
        payload = dbx.get_file(row["landed_path"])
        if len(payload) != int(row["size_bytes"]):
            failures.append(f"{row['file_name']}: size {len(payload)} != {row['size_bytes']}")
        if sha256(payload) != row["sha256"]:
            failures.append(f"{row['file_name']}: sha256 {sha256(payload)} != {row['sha256']}")
    orphans = listed - {r["file_name"] for r in rows}
    if orphans:
        failures.append(f"objects on the volume with no manifest row: {sorted(orphans)}")
    print(json.dumps({"files": len(rows), "failures": failures}, indent=2))
    return 1 if failures else 0


# --- retention ----------------------------------------------------------------
def cmd_retention(dbx: Databricks, args) -> int:
    n = names(args)
    expired = dbx.sql_ok(
        f"SELECT file_name, landed_path FROM {n.manifest} "
        f"WHERE retention_class = '{RETENTION_CLASS}' "
        f"AND first_landed_at < current_timestamp() - INTERVAL {RETENTION_DAYS} DAYS"
    ).dicts()
    for row in expired:
        status = dbx.delete_file(row["landed_path"])
        if not (200 <= status < 300 or status == 404):
            raise DbxError(f"{row['file_name']}: retention delete of {row['landed_path']} "
                           f"-> HTTP {status}; manifest row kept")
        dbx.sql_ok(f"DELETE FROM {n.manifest} WHERE file_name = '{esc(row['file_name'])}'")
    print(f"retention {RETENTION_CLASS}: {len(expired)} expired object(s) removed")
    return 0


# --- verification job ----------------------------------------------------------
def ingest_gate(n: Names) -> str:
    """Fails the SQL task when the landed state is inconsistent: duplicate
    manifest rows for one file, or a landed file whose manifest sha256 was never
    recorded in the ingest audit."""
    return f"""
    WITH dupes AS (
      SELECT file_name FROM {n.manifest} GROUP BY file_name HAVING count(*) > 1
    ),
    unaudited AS (
      SELECT m.file_name FROM {n.manifest} m
      LEFT JOIN {n.ingest_runs} r
        ON r.file_name = m.file_name AND r.sha256 = m.sha256 AND r.action = 'landed'
      WHERE r.file_name IS NULL
    ),
    problems AS (
      SELECT concat('duplicate manifest rows: ', file_name) AS msg FROM dupes
      UNION ALL
      SELECT concat('landed without audit row: ', file_name) FROM unaudited
    )
    SELECT CASE WHEN (SELECT count(*) FROM problems) > 0
                THEN raise_error(concat('INGEST VERIFICATION FAILED: ',
                     (SELECT concat_ws('; ', slice(collect_list(msg), 1, 8)) FROM problems)))
                ELSE concat('INGEST VERIFIED: ', CAST((SELECT count(*) FROM {n.manifest}) AS STRING),
                     ' file(s) landed, each exactly once with an audited sha256')
           END AS ingest_result"""


def cmd_job(dbx: Databricks, args) -> int:
    n = names(args)
    sql_path = f"{NOTEBOOK_DIR}/ingest_check_{n.ns}.sql"
    dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": NOTEBOOK_DIR})
    dbx.ok("POST", "/api/2.0/workspace/import", {
        "path": sql_path,
        "format": "AUTO",
        "overwrite": True,
        "content": base64.b64encode(ingest_gate(n).encode()).decode(),
    })
    settings = {
        "name": f"ow_tp_ingest_{n.ns}",
        "tags": {"project": "otterworks-tp", "demo": "billing-history", "namespace": n.ns},
        "max_concurrent_runs": 1,
        "tasks": [{
            "task_key": "ingest_verify",
            "sql_task": {
                "warehouse_id": dbx.warehouse_id,
                "file": {"path": sql_path, "source": "WORKSPACE"},
            },
        }],
        "schedule": {
            "quartz_cron_expression": "0 30 5 * * ?",
            "timezone_id": "UTC",
            "pause_status": "PAUSED",
        },
        "queue": {"enabled": True},
    }
    job_id = dbx.upsert_job(settings)
    print(f"ingest job {job_id} (schedule PAUSED): {dbx.host}/jobs/{job_id}")
    print(f"  verification SQL: {sql_path}")
    return 0


def cmd_run_job(dbx: Databricks, args) -> int:
    n = names(args)
    job = dbx.find_job(f"ow_tp_ingest_{n.ns}")
    if not job:
        raise SystemExit(f"ingest job for ns={n.ns} not found; run job first")
    run_id = dbx.run_job(int(job["job_id"]))
    print(f"triggered run: {dbx.run_url(run_id)}")
    run = dbx.wait_run(run_id)
    state = run.get("state", {})
    print(f"result: {state.get('result_state')} — {str(state.get('state_message'))[:400]}")
    return 0 if state.get("result_state") == "SUCCESS" else 1


def cmd_status(dbx: Databricks, args) -> int:
    n = names(args)
    result = dbx.sql(
        f"SELECT (SELECT count(*) FROM {n.manifest}) AS landed_files, "
        f"(SELECT sum(size_bytes) FROM {n.manifest}) AS landed_bytes, "
        f"(SELECT count(DISTINCT run_id) FROM {n.ingest_runs}) AS runs"
    )
    print(json.dumps(result.dicts()[0] if result.ok else {"state": result.state, "error": result.error}, indent=2))
    job = dbx.find_job(f"ow_tp_ingest_{n.ns}")
    if job:
        detail = dbx.ok("GET", f"/api/2.1/jobs/get?job_id={int(job['job_id'])}")
        schedule = detail.get("settings", {}).get("schedule")
        state = schedule.get("pause_status", "UNKNOWN") if schedule else "NO SCHEDULE"
        print(f"ingest job: {dbx.host}/jobs/{job['job_id']} schedule={state}")
    else:
        print("ingest job: absent")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["provision", "run", "verify", "retention",
                                            "job", "run-job", "status"])
    parser.add_argument("--ns", required=True, help="namespace suffix (e.g. w2ing)")
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--drop", default=None, help="drop directory to ingest (run)")
    parser.add_argument("--keep-source", action="store_true",
                        help="leave drop files in place after landing (default: remove, like the legacy job)")
    parser.add_argument("--warehouse-id", default=None)
    args = parser.parse_args()
    if args.command == "run" and not args.drop:
        parser.error("run requires --drop <directory>")
    dbx = Databricks(warehouse_id=args.warehouse_id)
    handler = {
        "provision": cmd_provision, "run": cmd_run, "verify": cmd_verify,
        "retention": cmd_retention, "job": cmd_job, "run-job": cmd_run_job,
        "status": cmd_status,
    }[args.command]
    try:
        return handler(dbx, args)
    except DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
