#!/usr/bin/env python3
"""Independent audit probes (read-only) run against the Oracle fixture and the Atlas
migration target. Secrets are referenced by environment-variable name only."""
import json
import os

import oracledb
from pymongo import MongoClient

ORACLE_DSN = "localhost:52521/FREEPDB1"
TARGET_DB = "ow_tp_mongodb_032752"
QUARANTINE_DB = "ow_tp_mongodb_032752_quarantine"


def main() -> None:
    cli = MongoClient(os.environ["MONGODB_ATLAS_URI"])
    db, quarantine = cli[TARGET_DB], cli[QUARANTINE_DB]
    cur = oracledb.connect(user="ow_billing", password="ow_billing", dsn=ORACLE_DSN).cursor()

    def source_count(sql: str) -> int:
        cur.execute(sql)
        return cur.fetchone()[0]

    def embedded(collection: str, array: str) -> int:
        rows = list(db[collection].aggregate(
            [{"$group": {"_id": None, "n": {"$sum": {"$size": {"$ifNull": [f"${array}", []]}}}}}]))
        return rows[0]["n"] if rows else 0

    orphans = quarantine["invoice_feed_orphan_lines"].count_documents({})
    lines = embedded("invoice_feed", "lines")
    out = {
        "probe_1_orphan_quarantine": {
            "quarantined_docs": orphans,
            "source_orphan_rows": source_count(
                "select count(*) from INVOICE_LINE l where not exists "
                "(select 1 from INVOICE_HEADER h where h.INVOICE_ID = l.INVOICE_ID)"),
            "expected": 37,
        },
        "probe_2_line_conservation": {
            "embedded_lines": lines,
            "quarantined_lines": orphans,
            "total": lines + orphans,
            "source_INVOICE_LINE": source_count("select count(*) from INVOICE_LINE"),
        },
        "probe_3_subscriptions": {
            "target_docs": db["subscriptions"].count_documents({}),
            "source_rows": source_count("select count(*) from SUBSCRIPTIONS"),
        },
        "probe_4_customers_and_eav": {
            "target_customers": db["customers"].count_documents({}),
            "source_CUSTOMER_MASTER": source_count("select count(*) from CUSTOMER_MASTER"),
            "embedded_attributes": embedded("customers", "attributes"),
            "source_ENTITY_ATTR_VALUE": source_count("select count(*) from ENTITY_ATTR_VALUE"),
        },
        "probe_5_scope": {
            "target_collections": sorted(db.list_collection_names()),
            "quarantine_collections": sorted(quarantine.list_collection_names()),
            "invoice_feed_docs_missing_ns_stamp": db["invoice_feed"].count_documents(
                {"ns": {"$ne": "mongo_032752"}}),
        },
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
