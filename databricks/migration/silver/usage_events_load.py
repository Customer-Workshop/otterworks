#!/usr/bin/env python3
"""Unit p1-usage-events (U-18), write half: land the snapshot in ow_tp.silver.usage_events.

Analytical track. The billing application does not write USAGE_EVENTS transactionally, so it
goes to Delta rather than Lakebase; rating reads it today and build session B1 reads it later.

The snapshot comes from `usage_events_extract.py`, which is where every legacy read happens;
this program never holds legacy credentials. It stages the snapshot as one Parquet object
under /Volumes/ow_tp/bronze/landing, merges it on the primary key and deletes the object, so
the only table it writes is ow_tp.silver.usage_events. The merge is a complete snapshot:
keys the source no longer has are deleted, so a rerun converges to the same state.

`occurred_at` lands as TIMESTAMP_NTZ, not TIMESTAMP: the source column carries no zone, and
Databricks TIMESTAMP is an instant rendered in the session zone, which is a different type
from the wall-clock value the source holds. TIMESTAMP_NTZ is the mapping's TIMESTAMP under
P1-D3 (UTC assumed, declared, not applied as a conversion).

`units > 0` — the first half of the legacy row trigger — is carried by the Delta CHECK
constraint added here, so every future writer is held to it and not only this loader. The
second half (`kind_cd` must be a known usage kind) is a lookup the extract makes against the
source code set; see usage_events_enforcement.md.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/migration/silver/usage_events_load.py --parquet /tmp/usage_events.parquet
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from databricks import sql as dbsql
from databricks.sdk import WorkspaceClient

CATALOG = "ow_tp"
SCHEMA = "silver"
TABLE = "usage_events"
TARGET = f"{CATALOG}.{SCHEMA}.{TABLE}"
VOLUME = "/Volumes/ow_tp/bronze/landing"
WAREHOUSE = "565cd2fd713738c4"

DDL = """CREATE TABLE IF NOT EXISTS ow_tp.silver.usage_events (
  id STRING NOT NULL COMMENT 'legacy USAGE_EVENTS.ID, VARCHAR2(36)',
  tenant_id STRING NOT NULL COMMENT 'legacy USAGE_EVENTS.TENANT_ID, VARCHAR2(36)',
  occurred_at TIMESTAMP_NTZ NOT NULL COMMENT 'legacy USAGE_EVENTS.OCCURRED_AT; the source carries no zone, UTC is assumed and declared (plan decision P1-D3)',
  units BIGINT NOT NULL COMMENT 'legacy USAGE_EVENTS.UNITS, NUMBER(10)',
  kind_cd SMALLINT NOT NULL COMMENT 'legacy USAGE_EVENTS.KIND_CD, NUMBER(4), a CODES(USAGE_KIND) value kept as a magic number'
)
USING DELTA
COMMENT 'U-18 USAGE_EVENTS from the legacy billing estate. Loaded by databricks/migration/silver/usage_events_load.py'"""

# The legacy row trigger rejects NVL(units, 0) <= 0; the column is NOT NULL, so > 0 is the
# same rule.
CONSTRAINTS = [("usage_events_units_positive", "units > 0")]

MERGE = """MERGE INTO ow_tp.silver.usage_events t USING (
  SELECT CAST(id AS STRING) AS id,
         CAST(tenant_id AS STRING) AS tenant_id,
         CAST(occurred_at AS TIMESTAMP_NTZ) AS occurred_at,
         CAST(units AS BIGINT) AS units,
         CAST(kind_cd AS SMALLINT) AS kind_cd
  FROM parquet.`{staged}`) s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE"""


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def ensure_table(cur) -> list[str]:
    cur.execute(DDL)
    cur.execute(f"SHOW TBLPROPERTIES {TARGET}")
    props = {r[0]: r[1] for r in cur.fetchall()}
    added = []
    for name, expr in CONSTRAINTS:
        if f"delta.constraints.{name}" in props:
            continue
        cur.execute(f"ALTER TABLE {TARGET} ADD CONSTRAINT {name} CHECK ({expr})")
        added.append(name)
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=Path, required=True,
                    help="snapshot written by usage_events_extract.py")
    args = ap.parse_args(argv)

    run_id = uuid.uuid4().hex
    staged = f"{VOLUME}/{TABLE}/{run_id}.parquet"
    workspace = WorkspaceClient()
    with args.parquet.open("rb") as handle:
        workspace.files.upload(staged, handle, overwrite=True)
    try:
        with sql_conn() as conn, conn.cursor() as cur:
            constraints_added = ensure_table(cur)
            cur.execute(MERGE.format(staged=staged))
            cur.execute(f"SELECT count(*) FROM {TARGET}")
            target_rows = cur.fetchone()[0]
    finally:
        workspace.files.delete(staged)

    print(json.dumps({"table": TARGET, "snapshot": str(args.parquet),
                      "target_rows": target_rows, "deletes_converged": True,
                      "constraints_added": constraints_added,
                      "staged": staged, "staged_retained": False}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
