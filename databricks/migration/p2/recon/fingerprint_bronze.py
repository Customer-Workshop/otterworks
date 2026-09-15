"""Fingerprint the bronze CUSTBILL tables so a rerun can be compared to the run before it.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/fingerprint_bronze.py --label after-second-run

Idempotency is proven by running the pipeline again and comparing this fingerprint, never by
asserting that the code looks idempotent. `ingested_at` is excluded on purpose: it is wall
clock, it changes on every run by design, and including it would make every rerun look like
drift.
"""

from __future__ import annotations

import argparse
import json
import os

from databricks import sql as dbsql

QUERY = """
SELECT count(*) AS rows,
       count(DISTINCT source_file) AS files,
       sum(record_bytes) AS total_bytes,
       md5(concat_ws('\\n', sort_array(collect_list(
         concat_ws('\\u0001', source_file, lpad(cast(record_no AS string), 9, '0'),
                   raw_record, cast(record_bytes AS string)))))) AS content_md5
FROM ow_tp.bronze.custbill_raw
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        cur.execute(QUERY)
        rows, files, total_bytes, content_md5 = cur.fetchone()
        cur.execute("SELECT count(*), sum(record_count), sum(file_bytes) "
                    "FROM ow_tp.bronze.custbill_files")
        ledger_rows, ledger_records, ledger_bytes = cur.fetchone()

    print(json.dumps({"label": args.label,
                      "custbill_raw": {"rows": rows, "files": files,
                                       "total_bytes": total_bytes,
                                       "content_md5": content_md5},
                      "custbill_files": {"rows": ledger_rows,
                                         "records": ledger_records,
                                         "bytes": ledger_bytes}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
