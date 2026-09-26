"""Wave 1 / batch w1-b02 loader, unit invoice_batch (mapping v1.1.0, halt fix A):
OW_BILLING.INVOICE_HEADER -> mmp_rt_billing.invoice_headers   (_id = INVOICE_ID, no lines[] array)
OW_BILLING.INVOICE_LINE   -> mmp_rt_billing.invoice_lines     (_id = LINE_ID, ref invoiceId; ALL rows)

invoice_lines is a referenced root collection: every INVOICE_LINE row lands there through its
mapping row. The derived, ungraded flag `orphan: true` is set on the rows whose INVOICE_ID has
no INVOICE_HEADER (37 planted orphans); it is absent otherwise (null_missing_equiv).

Both declared write targets are dropped and recreated per run (playbook 3 step 4) with their
index_plan, then written by replace-upsert on _id, so a re-run converges. Load order matters:
invoice_headers first, then invoice_lines, whose orphan flag is derived from the header ids
just loaded (one distinct() on the target; no extra source query). One Oracle connection,
two SELECTs (source_concurrency 1). Conversions per mapping v1.1.0 / profile oracle.md:
NUMBER(p,s>0) -> Decimal128 at declared scale, CHAR rstrip, '' -> missing, *_YN -> bool,
*_DT VARCHAR2 trap columns kept as strings.
Usage: ~/.venvs/recon/bin/python services/legacy-billing/migration/load_invoice_batch.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_embedded_collection, load_mapping, mongo_db, oracle_connect  # noqa: E402

MAPPING = ".migration/mapping/invoice_batch.json"
WRITE_TARGETS = ("invoice_headers", "invoice_lines")  # load order: headers before lines


def orphan_flag(header_ids):
    """derive() for invoice_lines: {'orphan': True} iff INVOICE_ID has no INVOICE_HEADER."""
    def derive(row, doc):
        return {"orphan": True} if row["INVOICE_ID"] not in header_ids else None
    return derive


def main():
    mapping = load_mapping(MAPPING)
    db = mongo_db()
    with oracle_connect() as conn:
        n_headers, _ = load_embedded_collection(conn, db, mapping, "invoice_headers")
        header_ids = set(db.invoice_headers.distinct("_id"))
        n_lines, _ = load_embedded_collection(conn, db, mapping, "invoice_lines",
                                              derive=orphan_flag(header_ids))
    n_orphans = db.invoice_lines.count_documents({"orphan": True})
    print(f"loaded mmp_rt_billing.invoice_headers: {n_headers} docs")
    print(f"loaded mmp_rt_billing.invoice_lines: {n_lines} docs ({n_orphans} flagged orphan:true)")


if __name__ == "__main__":
    main()
