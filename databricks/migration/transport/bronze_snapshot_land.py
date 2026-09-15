#!/usr/bin/env python3
"""Land a local Parquet snapshot into ow_tp.bronze. The target half of the transport.

Pairs with `oracle_snapshot_extract.py`, which produces `<prefix>.parquet` and
`<prefix>.schema.json`. This program never opens a source connection: the two halves are
separate so that no single program both reads the legacy estate and writes a target.

The snapshot is complete by construction, so the landing converges deletes: rows whose key
is no longer in the snapshot are removed, and a snapshot with no rows empties the table.
An empty snapshot still registers the table, from the schema sidecar, so downstream work
sees the right columns and zero rows - the state both pipeline-1 history tables are in.

    python3 bronze_snapshot_land.py --table subscriptions_hist --keys hist_id --in /tmp/sh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

from databricks.sdk import WorkspaceClient

from databricks import sql as dbsql

CATALOG = "ow_tp"
SCHEMA = "bronze"
VOLUME = "/Volumes/ow_tp/bronze/landing"
WAREHOUSE = "565cd2fd713738c4"

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
TYPE = re.compile(r"^[A-Z_0-9]+(\(\d+(,\s*\d+)?\))?$")


def ident(name: str, what: str) -> str:
    n = (name or "").strip().lower()
    if not IDENT.match(n):
        raise SystemExit(f"{what} is not a plain SQL identifier: {name!r}")
    return n


def sql_type(name: str) -> str:
    if not TYPE.match((name or "").strip()):
        raise SystemExit(f"refusing non-type {name!r}")
    return name.strip()


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--keys", required=True, help="comma-separated primary key columns")
    ap.add_argument("--in", dest="prefix", required=True,
                    help="path prefix written by oracle_snapshot_extract.py")
    ap.add_argument("--recreate", action="store_true",
                    help="drop the target first so its column types are rebuilt from the "
                         "snapshot's schema; a MERGE never changes a column's type")
    args = ap.parse_args()
    table = ident(args.table, "--table")
    keys = [ident(k, "--keys") for k in args.keys.split(",")]

    prefix = Path(args.prefix)
    meta = json.loads(prefix.with_suffix(".schema.json").read_text())
    if ident(meta["table"], "snapshot table") != table:
        raise SystemExit(f"snapshot is for {meta['table']!r}, not {table!r}")
    parquet = prefix.with_suffix(".parquet")
    target = f"{CATALOG}.{SCHEMA}.{table}"

    with sql_conn() as conn, conn.cursor() as cur:
        if args.recreate:
            cur.execute(f"DROP TABLE IF EXISTS {target}")
        if not meta["rows"]:
            cols = ", ".join(f"{ident(c['name'], 'column')} {sql_type(c['delta_type'])}"
                             for c in meta["columns"])
            cur.execute(f"SHOW TABLES IN {CATALOG}.{SCHEMA} LIKE '{table}'")
            if cur.fetchall():
                cur.execute(f"DELETE FROM {target}")
                created, emptied = False, True
            else:
                cur.execute(f"CREATE TABLE {target} ({cols})")
                created, emptied = True, False
            cur.execute(f"SELECT count(*) FROM {target}")
            print(json.dumps({"table": target, "snapshot_rows": 0,
                              "target_rows": cur.fetchone()[0], "target_created": created,
                              "target_emptied": emptied, "deletes_converged": True}))
            return 0

        run_id = uuid.uuid4().hex
        staged = f"{VOLUME}/{table}/{run_id}.parquet"
        with parquet.open("rb") as fh:
            WorkspaceClient().files.upload(staged, fh, overwrite=True)
        stage = f"{CATALOG}.{SCHEMA}.{table}__stage_{run_id}"
        try:
            cur.execute(f"CREATE TABLE {stage} AS SELECT * FROM parquet.`{staged}`")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {target} "
                        f"AS SELECT * FROM {stage} WHERE 1=0")
            on = " AND ".join(f"t.{k} <=> s.{k}" for k in keys)
            cur.execute(f"MERGE INTO {target} t USING {stage} s ON {on} "
                        "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT * "
                        "WHEN NOT MATCHED BY SOURCE THEN DELETE")
            cur.execute(f"SELECT count(*) FROM {target}")
            total = cur.fetchone()[0]
        finally:
            # The staged object exists only to seed the stage table; a failing drop must not
            # skip the file delete, so the cleanup is nested.
            try:
                cur.execute(f"DROP TABLE IF EXISTS {stage}")
            finally:
                WorkspaceClient().files.delete(staged)

    print(json.dumps({"table": target, "snapshot_rows": meta["rows"],
                      "target_rows": total, "deletes_converged": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
