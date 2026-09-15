"""Load the captured legacy CUSTBILL bytes into the recon source table.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/load_legacy_baseline.py

This is the SOURCE side of the p2-sftp-ingest recon: the pinned .dat files the legacy chain
was run over, one row per physical record, loaded verbatim into
ow_tp.bronze.custbill_legacy_baseline_raw. The TARGET side is ow_tp.bronze.custbill_raw,
which the Lakeflow pipeline recomputes from the same .dat files inside Spark. The two sides
share nothing but the input bytes: this loader deliberately does not import
custbill_bytes.py, so a bug in the pipeline's splitter cannot be copied into its own
baseline.

The table is replaced on every run: it is derived evidence, and a half-refreshed baseline is
worse than none.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from databricks import sql as dbsql

TABLE = "ow_tp.bronze.custbill_legacy_baseline_raw"
DEFAULT_INPUTS = Path(__file__).resolve().parents[1] / "baseline/captured/inputs"
ENCODING = "iso-8859-1"


def records(path: Path) -> list[tuple[int, str, int]]:
    """Physical records of a landed file: split on LF, a trailing LF closes the last record.

    A CR is left inside the record - the legacy parser sees it too. A blank line in the
    middle of a file is a record; the empty piece after a trailing LF is not.
    """
    body = path.read_bytes()
    if not body:
        return []
    parts = body.split(b"\n")
    if parts[-1] == b"":
        parts.pop()
    return [(i + 1, p.decode(ENCODING), len(p)) for i, p in enumerate(parts)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default=str(DEFAULT_INPUTS))
    args = ap.parse_args()

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    rows: list[tuple[str, int, str, int]] = []
    for dat in sorted(Path(args.inputs).glob("CUSTBILL*.dat")):
        for record_no, raw, nbytes in records(dat):
            rows.append((dat.name, record_no, raw, nbytes))

    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        cur.execute(f"CREATE OR REPLACE TABLE {TABLE} ("
                    "source_file STRING, record_no BIGINT, "
                    "raw_record STRING, record_bytes INT)")
        for chunk_start in range(0, len(rows), 200):
            chunk = rows[chunk_start:chunk_start + 200]
            values = ", ".join("(?, ?, ?, ?)" for _ in chunk)
            cur.execute(f"INSERT INTO {TABLE} VALUES {values}",
                        [v for row in chunk for v in row])
        cur.execute(f"SELECT count(*), count(DISTINCT source_file) FROM {TABLE}")
        loaded, files = cur.fetchone()

    print(json.dumps({"table": TABLE, "rows": loaded, "files": files}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
