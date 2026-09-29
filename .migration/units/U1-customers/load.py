"""U1-customers fixture/live loader: CUSTOMER_MASTER + ENTITY_ATTR_VALUE -> customers."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import mongo_load

UNIT = "U1-customers"
COLLECTION = "customers"


def _dup_attr_hashes(eav_rows):
    groups = {}
    for row in eav_rows:
        groups.setdefault((row["ENTITY_ID"], row["ATTR_NAME"]), 0)
        groups[(row["ENTITY_ID"], row["ATTR_NAME"])] += 1
    return sorted(
        hashlib.sha256(f"{cust}|{name}".encode()).hexdigest()[:16]
        for (cust, name), n in groups.items()
        if n > 1
    )


def load(cur, db, allowed):
    spec = mongo_load.load_spec()
    coll = mongo_load.coll_spec(spec, COLLECTION)

    cur.execute("SELECT * FROM ow_billing.customer_master")
    customers = mongo_load.fetch_dicts(cur)
    cur.execute("SELECT * FROM ow_billing.entity_attr_value WHERE entity_type = 'CUSTOMER'")
    eav = mongo_load.fetch_dicts(cur)

    docs = mongo_load.build_root_docs(coll, customers, {"attributes": eav})
    bulk = mongo_load.write_collection(
        db, COLLECTION, docs, coll.get("indexes"), allowed
    )
    return {
        "source_counts": {
            "customer_master": len(customers),
            "entity_attr_value": len(eav),
        },
        "doc_counts": {COLLECTION: len(docs)},
        "bulk": {COLLECTION: bulk},
        "expected_dup_attr_hashes": _dup_attr_hashes(eav),
    }


if __name__ == "__main__":
    mongo_load.run_unit(UNIT, load)
