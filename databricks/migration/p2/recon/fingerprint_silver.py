"""Fingerprint the silver CUSTBILL tables so a rerun can be compared to the run before it.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/fingerprint_silver.py --label after-second-run

Idempotency is proven by running the pipeline again and comparing this fingerprint, never
by asserting that the code looks idempotent. `parsed_at` and `quarantined_at` are excluded
on purpose: they are wall clock, they change on every run by design, and including them
would make every rerun look like drift.
"""

from __future__ import annotations

import argparse
import json
import os

from databricks import sql as dbsql

QUERIES = {
    "silver": """
SELECT count(*) AS rows,
       count(DISTINCT source_file) AS files,
       md5(concat_ws('\\n', sort_array(collect_list(
         concat_ws('\\u0001', source_file, lpad(cast(record_no AS string), 9, '0'),
                   raw_record, psv_line, cast(psv_field_count AS string)))))) AS content_md5
FROM ow_tp.silver.custbill
""",
    "quarantine": """
SELECT count(*) AS rows,
       count(DISTINCT source_file) AS files,
       md5(concat_ws('\\n', sort_array(collect_list(
         concat_ws('\\u0001', source_file, lpad(cast(record_no AS string), 9, '0'),
                   concat_ws(',', sort_array(failed_expectations))))))) AS content_md5
FROM ow_tp.bronze.custbill_quarantine
""",
    "trailer_audit": """
SELECT count(*) AS rows,
       count(DISTINCT source_file) AS files,
       md5(concat_ws('\\n', sort_array(collect_list(
         concat_ws('\\u0001', source_file, cast(physical_record_count AS string),
                   coalesce(cast(trailer_count AS string), ''),
                   cast(parsed_count AS string), cast(shadowed_count AS string)))))) AS content_md5
FROM ow_tp.bronze.custbill_trailer_audit
""",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    out: dict[str, object] = {"label": args.label}
    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        for name, query in QUERIES.items():
            cur.execute(query)
            rows, files, content_md5 = cur.fetchone()
            out[name] = {"rows": rows, "files": files, "content_md5": content_md5}

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
