#!/usr/bin/env python3
"""Read-only shape and anomaly probe on the source USAGE_EVENTS table (unit p1-usage-events-oltp).

Run under with_oracle_fixture.py (development) or with_oracle_secret.py (the single live
read), which put the secret JSON in the named environment variable:

    python3 databricks/migration/recon/with_oracle_fixture.py OW_TP_ORACLE_RO -- \
      python3 .migration/recon/p1-usage-events-oltp/read_source_rows.py

Only SELECTs, in a read-only transaction. Nothing is printed but counts and column metadata.
"""
from __future__ import annotations

import json
import os
import sys

import oracledb

QUERIES = {
    "row_count": "SELECT COUNT(*) FROM ow_billing.usage_events",
    "orphan_tenant_rows": (
        "SELECT COUNT(*) FROM ow_billing.usage_events u WHERE NOT EXISTS "
        "(SELECT 1 FROM ow_billing.tenants t WHERE t.id = u.tenant_id)"),
    "non_positive_units_rows": (
        "SELECT COUNT(*) FROM ow_billing.usage_events WHERE NVL(units, 0) <= 0"),
    "unknown_kind_rows": (
        "SELECT COUNT(*) FROM ow_billing.usage_events u WHERE NOT EXISTS "
        "(SELECT 1 FROM ow_billing.codes c WHERE c.code_type = 'USAGE_KIND' "
        "AND c.code_val = u.kind_cd)"),
    "null_or_empty_id_rows": (
        "SELECT COUNT(*) FROM ow_billing.usage_events WHERE id IS NULL"),
    "distinct_tenants": "SELECT COUNT(DISTINCT tenant_id) FROM ow_billing.usage_events",
    "fractional_second_rows": (
        "SELECT COUNT(*) FROM ow_billing.usage_events "
        "WHERE occurred_at <> CAST(occurred_at AS TIMESTAMP(0))"),
}


def main() -> int:
    oracledb.defaults.fetch_decimals = True
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    out: dict[str, object] = {}
    with oracledb.connect(user=parts["user"], password=parts["password"],
                          dsn=f"{parts['host']}:{parts['port']}/{parts['service']}") as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            for name, sql in QUERIES.items():
                cur.execute(sql)
                out[name] = int(cur.fetchone()[0])
            cur.execute(
                "SELECT column_name, data_type, data_length, data_precision, data_scale, "
                "nullable FROM all_tab_columns WHERE owner = 'OW_BILLING' "
                "AND table_name = 'USAGE_EVENTS' ORDER BY column_id")
            out["columns"] = [list(map(str, r)) for r in cur.fetchall()]
            cur.execute("SELECT MIN(occurred_at), MAX(occurred_at), SUM(units) "
                        "FROM ow_billing.usage_events")
            lo, hi, units_total = cur.fetchone()
            out["occurred_at_min"] = str(lo)
            out["occurred_at_max"] = str(hi)
            out["units_total"] = str(units_total)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
