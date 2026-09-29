"""U0-reference loader (wave 0, D-015): codes, tenants, plans + OW_BILLING sequences."""
import sys
from pathlib import Path

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import mongo_load

UNIT = "U0-reference"


def load(cur, db, allowed):
    spec = mongo_load.load_spec()
    source_counts, doc_counts, bulk = {}, {}, {}

    def finish(coll_name):
        coll = mongo_load.coll_spec(spec, coll_name)
        rows = mongo_load.fetch_dicts(cur)
        source_counts[coll["root_table"].split(".")[-1].lower()] = len(rows)
        docs = mongo_load.build_root_docs(coll, rows)
        bulk[coll_name] = mongo_load.write_collection(
            db, coll_name, docs, coll.get("indexes"), allowed
        )
        doc_counts[coll_name] = len(docs)

    cur.execute("SELECT * FROM ow_billing.codes")
    finish("codes")
    cur.execute("SELECT * FROM ow_billing.tenants")
    finish("tenants")
    cur.execute("SELECT * FROM ow_billing.plans")
    finish("plans")

    try:
        cur.execute(
            "SELECT sequence_name, last_number, increment_by FROM dba_sequences WHERE sequence_owner = 'OW_BILLING'"
        )
        seq_view = "dba_sequences"
    except oracledb.DatabaseError:
        cur.execute(
            "SELECT sequence_name, last_number, increment_by FROM all_sequences WHERE sequence_owner = 'OW_BILLING'"
        )
        seq_view = "all_sequences"
    sequences = mongo_load.fetch_dicts(cur)
    if not sequences:
        raise RuntimeError(f"{seq_view} returned no OW_BILLING sequences")
    seq_docs = [
        {
            "_id": str(r["SEQUENCE_NAME"]).lower(),
            "last_number": mongo_load.Int64(r["LAST_NUMBER"]),
            "increment_by": mongo_load.Int64(r["INCREMENT_BY"]),
        }
        for r in sequences
    ]
    source_counts[seq_view] = len(sequences)
    bulk["sequences"] = mongo_load.write_collection(
        db, "sequences", seq_docs, [], allowed
    )
    doc_counts["sequences"] = len(seq_docs)
    return {
        "source_counts": source_counts,
        "doc_counts": doc_counts,
        "bulk": bulk,
    }


if __name__ == "__main__":
    mongo_load.run_unit(UNIT, load)
