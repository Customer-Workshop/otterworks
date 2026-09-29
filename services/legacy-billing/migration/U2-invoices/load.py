"""U2-invoices fixture/live loader.

INVOICE_HEADER + matched INVOICE_LINE -> invoices (lines embedded);
INVOICE_LINE rows whose INVOICE_ID has no header -> quarantine_invoice_line.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".migration" / "tools"))
import mongo_load

UNIT = "U2-invoices"
INVOICES = "invoices"
QUARANTINE = "quarantine_invoice_line"


def _orphan_hashes(orphans):
    return sorted(
        hashlib.sha256(str(row["LINE_ID"]).encode()).hexdigest()[:16] for row in orphans
    )


def load(cur, db, allowed):
    spec = mongo_load.load_spec()
    invoiceSpec = mongo_load.coll_spec(spec, INVOICES)
    quarantineSpec = mongo_load.coll_spec(spec, QUARANTINE)

    cur.execute("SELECT * FROM ow_billing.invoice_header")
    headers = mongo_load.fetch_dicts(cur)
    cur.execute("SELECT * FROM ow_billing.invoice_line")
    lines = mongo_load.fetch_dicts(cur)

    headerIds = {row["INVOICE_ID"] for row in headers}
    matched = [row for row in lines if row["INVOICE_ID"] in headerIds]
    orphans = [row for row in lines if row["INVOICE_ID"] not in headerIds]

    invoiceDocs = mongo_load.build_root_docs(invoiceSpec, headers, {"lines": matched})

    quarantineMeta = quarantineSpec["quarantine"]
    quarantineDocs = mongo_load.build_root_docs(quarantineSpec, orphans)
    for doc in quarantineDocs:
        doc["quarantine_reason"] = quarantineMeta["reason"]
        doc["source_table"] = quarantineSpec["root_table"]
    if len(quarantineDocs) != quarantineMeta["expected_rows"]:
        raise ValueError(
            f"{QUARANTINE}: {len(quarantineDocs)} orphan lines, spec expects "
            f"{quarantineMeta['expected_rows']}"
        )

    bulk = {
        INVOICES: mongo_load.write_collection(
            db, INVOICES, invoiceDocs, invoiceSpec.get("indexes"), allowed
        ),
        QUARANTINE: mongo_load.write_collection(
            db, QUARANTINE, quarantineDocs, quarantineSpec.get("indexes"), allowed
        ),
    }
    return {
        "source_counts": {
            "invoice_header": len(headers),
            "invoice_line": len(lines),
            "invoice_line_matched": len(matched),
            "invoice_line_orphans": len(orphans),
        },
        "doc_counts": {INVOICES: len(invoiceDocs), QUARANTINE: len(quarantineDocs)},
        "embedded_counts": {f"{INVOICES}.lines": sum(len(d["lines"]) for d in invoiceDocs)},
        "bulk": bulk,
        "expected_orphan_hashes": _orphan_hashes(orphans),
    }


if __name__ == "__main__":
    mongo_load.run_unit(UNIT, load)
