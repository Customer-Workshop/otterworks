"""Fingerprint the finance close and its exported files, so a rerun can be compared to it.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/fingerprint_gold.py --label after-second-run

Idempotency is proven by running the pipeline and the export job again and comparing this
fingerprint, never by asserting that the code looks idempotent. `closed_at` is excluded on
purpose: it is wall clock, it changes on every run by design, and including it would make
every rerun look like drift. The exported `.csv` and `.xls` are hashed as bytes, which is
the property that matters for the file consumers the report used to have.
"""

from __future__ import annotations

import argparse
import json
import os

from databricks import sql as dbsql

GOLD = """
SELECT count(*) AS rows,
       sum(record_count) AS records,
       md5(concat_ws('\\n', sort_array(collect_list(
         concat_ws('\\u0001', lpad(cast(row_order AS string), 4, '0'), sort_key,
                   currency, rec_type, record_type,
                   cast(record_count AS string), cast(total_amount AS string)))))) AS content_md5
FROM ow_tp.gold.custbill_finance_close
"""

EXPORTS = """
SELECT _metadata.file_name AS name, md5(content) AS content_md5, length(content) AS bytes
FROM read_files('/Volumes/ow_tp/gold/exports/custbill', format => 'binaryFile')
ORDER BY name
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    out: dict[str, object] = {"label": args.label}
    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        cur.execute(GOLD)
        rows, records, content_md5 = cur.fetchone()
        out["gold"] = {"rows": rows, "records": int(records), "content_md5": content_md5}
        cur.execute(EXPORTS)
        out["exports"] = [
            {"name": name, "content_md5": md5, "bytes": nbytes}
            for name, md5, nbytes in cur.fetchall()
        ]

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
