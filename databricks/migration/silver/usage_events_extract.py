#!/usr/bin/env python3
"""Unit p1-usage-events (U-18), read half: snapshot USAGE_EVENTS out of the legacy estate.

One read-only JDBC snapshot of the table plus the `USAGE_KIND` code set, taken in a single
read-only transaction so both see the same point in time. The same route as the wave-0
transport (D-002 fallback): D10-01 was denied, so there is no Lakehouse Federation.

The write half is `usage_events_load.py`, deliberately a separate program: nothing but reads
ever runs in a process that holds legacy credentials.

`TRG_USAGE_EVENTS_CHECK` is evaluated here, against the code set read in the same
transaction: a non-positive `units` (ORA-20001) or a `kind_cd` that is not a known usage
kind (ORA-20002) fails the extract and nothing is handed to the load. Rows are never
dropped, cleaned or quarantined; reproducing the rejection is the parity behaviour (D8-01).
See usage_events_enforcement.md.

usage (under with_oracle_secret.py, which puts the secret in the named environment variable):
  python3 databricks/migration/silver/usage_events_extract.py --out /tmp/usage_events.parquet
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import oracledb
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE_SCHEMA = "ow_billing"
SECRET_ENV = "OW_TP_ORACLE_RO"

# NUMBER comes back as a float by default, which would round counters this unit compares
# exactly. Decimals keep every NUMBER exact from the source cursor into Parquet.
oracledb.defaults.fetch_decimals = True


def oracle_conn():
    parts = json.loads(os.environ[SECRET_ENV])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def read_source() -> tuple[list[tuple], set[int]]:
    with oracle_conn() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(f"SELECT code_val FROM {SOURCE_SCHEMA}.codes "
                    "WHERE code_type = 'USAGE_KIND'")
        kinds = {int(r[0]) for r in cur.fetchall()}
        cur.execute("SELECT id, tenant_id, occurred_at, units, kind_cd "
                    f"FROM {SOURCE_SCHEMA}.usage_events")
        rows = cur.fetchall()
    return rows, kinds


def trigger_rule_violations(rows: list[tuple], kinds: set[int]) -> list[str]:
    """The two rejections TRG_USAGE_EVENTS_CHECK raises, applied to the snapshot."""
    violations = []
    for row_id, _tenant, _at, units, kind_cd in rows:
        if units is None or int(units) <= 0:
            violations.append(f"{row_id}: units must be > 0 (ORA-20001)")
        if kind_cd is None or int(kind_cd) not in kinds:
            violations.append(f"{row_id}: unknown usage kind {kind_cd} (ORA-20002)")
    return violations


def arrow_table(rows: list[tuple]) -> pa.Table:
    """Target types, fixed by the mapping spec rather than inferred from the rows."""
    return pa.table({
        "id": pa.array([r[0] for r in rows], type=pa.string()),
        "tenant_id": pa.array([r[1] for r in rows], type=pa.string()),
        "occurred_at": pa.array([r[2] for r in rows], type=pa.timestamp("us")),
        "units": pa.array([None if r[3] is None else int(r[3]) for r in rows],
                          type=pa.int64()),
        "kind_cd": pa.array([None if r[4] is None else int(r[4]) for r in rows],
                            type=pa.int16()),
    })


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="Parquet snapshot to write")
    ap.add_argument("--check-only", action="store_true",
                    help="read and check the source, write no snapshot")
    args = ap.parse_args(argv)

    rows, kinds = read_source()
    violations = trigger_rule_violations(rows, kinds)
    out = {"source_table": f"{SOURCE_SCHEMA}.usage_events", "source_rows": len(rows),
           "usage_kinds": sorted(kinds), "violation_count": len(violations)}
    if violations:
        out["trigger_rule_violations"] = violations[:20]
        out["snapshot"] = None
        print(json.dumps(out, indent=2))
        return 1
    if not args.check_only:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(arrow_table(rows), args.out)
        out["snapshot"] = str(args.out)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
