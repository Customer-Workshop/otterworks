"""Wave 1: invoices (two estates in one collection) and invoice_lines_orphaned.

INVOICE_HEADER + INVOICE_LINE become source="conversion" documents with the lines
embedded; INVOICES + INVOICE_LINES + DUNNING_ATTEMPTS become source="billing" documents
with lines[] and dunning[]. The two key spaces do not overlap, so _id is the source
primary key for both. INVOICE_LINE rows with no header keep their dangling invoiceId and
land in invoice_lines_orphaned instead of being attached to an invented header.

    python migrations/mongodb/invoices/load_invoices.py [--drop]

The load is idempotent: each document is replaced by its source primary key and target
documents whose source row is gone are deleted, so a re-run converges on the source key
set. Reads Oracle read-only in one snapshot through ORACLE_BILLING_URI; writes only
ow_billing_migration through MONGODB_ATLAS_URI. Mapping: .migration/03_mapping_spec.json
(version 1).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, ReplaceOne

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import (  # noqa: E402
    csv_list, decode, load_codes, money, mongo_db, oracle_connect, parse_dt, rows,
    set_raw, utc, yn,
)

INVOICES = "invoices"
ORPHANS = "invoice_lines_orphaned"
BATCH = 1000

ORPHAN_PREDICATE = ("NOT EXISTS (SELECT 1 FROM invoice_header h "
                    "WHERE h.invoice_id = l.invoice_id)")


def _service_period(raw):
    """'MMYYYY-MMYYYY' to {from, to}; anything else is null with the raw value kept."""
    if raw is None:
        return None, False
    text = str(raw).strip()
    parts = text.split("-")
    if len(parts) != 2:
        return None, True
    bounds = []
    for part in parts:
        part = part.strip()
        if len(part) != 6 or not part.isdigit():
            return None, True
        month, year = int(part[:2]), int(part[2:])
        if not 1 <= month <= 12 or not 1 <= year <= 9999:
            return None, True
        bounds.append(dt.datetime(year, month, 1, tzinfo=dt.timezone.utc))
    return {"from": bounds[0], "to": bounds[1]}, False


LINE_SQL = ("SELECT line_id, invoice_id, cust_no, cust_name, line_no, line_type_cd, "
            "item_desc, qty, unit_price, amount, tax_amt, service_period, posted_yn, "
            "gl_acct_csv, batch_no, src_system FROM invoice_line l")


def _conversion_line(r):
    """One INVOICE_LINE row as a lines[] element (also the orphan document body)."""
    period, period_bad = _service_period(r["SERVICE_PERIOD"])
    accounts, accounts_bad = csv_list(r["GL_ACCT_CSV"])
    posted = yn(r["POSTED_YN"])
    el = {"lineId": r["LINE_ID"],
          "lineNo": int(r["LINE_NO"]) if r["LINE_NO"] is not None else None,
          "type": int(r["LINE_TYPE_CD"]) if r["LINE_TYPE_CD"] is not None else None,
          "description": r["ITEM_DESC"],
          "qty": money(r["QTY"]),
          "unitPrice": money(r["UNIT_PRICE"]),
          "amount": money(r["AMOUNT"]),
          "taxAmt": money(r["TAX_AMT"]),
          "servicePeriod": period,
          "posted": posted,
          "glAccounts": accounts,
          "batchNo": int(r["BATCH_NO"]) if r["BATCH_NO"] is not None else None,
          "srcSystem": r["SRC_SYSTEM"]}
    if period_bad:
        set_raw(el, "legacy.servicePeriodRaw", r["SERVICE_PERIOD"])
    if accounts_bad:
        set_raw(el, "legacy.glAcctCsvRaw", r["GL_ACCT_CSV"])
    if posted is None and r["POSTED_YN"] is not None:
        set_raw(el, "legacy.postedYnRaw", r["POSTED_YN"])
    return el


def build_conversion(conn, codes):
    """INVOICE_HEADER with its INVOICE_LINE rows embedded, ordered by line number."""
    lines: dict[str, list[dict]] = {}
    customer: dict[str, tuple] = {}
    for r in rows(conn, LINE_SQL + " WHERE NOT " + ORPHAN_PREDICATE
                        + " ORDER BY invoice_id, line_no"):
        lines.setdefault(r["INVOICE_ID"], []).append(_conversion_line(r))
        # CUST_NO/CUST_NAME repeat on every line of a header, but some lines leave them
        # null; lift the first line that carries each one.
        cust_no, cust_name = customer.get(r["INVOICE_ID"], (None, None))
        customer[r["INVOICE_ID"]] = (cust_no if cust_no is not None else r["CUST_NO"],
                                     cust_name if cust_name is not None else r["CUST_NAME"])
    for r in rows(conn, "SELECT invoice_id, invoice_no, cust_id, tenant_id, invoice_dt, "
                        "due_dt, status_cd, total_amt, batch_no FROM invoice_header"):
        invoice_dt = parse_dt(r["INVOICE_DT"])
        due_dt = parse_dt(r["DUE_DT"])
        cust_no, cust_name = customer.get(r["INVOICE_ID"], (None, None))
        doc = {"_id": r["INVOICE_ID"],
               "source": "conversion",
               # omitted rather than null: the invoiceNo index is unique and sparse, and a
               # sparse index still indexes an explicit null
               **({"invoiceNo": r["INVOICE_NO"]} if r["INVOICE_NO"] is not None else {}),
               "tenantId": r["TENANT_ID"],
               "customer": {"id": r["CUST_ID"], "custNo": cust_no, "name": cust_name},
               "invoiceDate": invoice_dt,
               "dueDate": due_dt,
               "status": decode(codes, "INV_STATUS", r["STATUS_CD"]),
               # Conversion rows carry a total only: no subtotal, no tax.
               "totals": {"total": money(r["TOTAL_AMT"])},
               "lines": lines.get(r["INVOICE_ID"], []),
               "legacy": {"batchNo": int(r["BATCH_NO"]) if r["BATCH_NO"] is not None
                          else None}}
        if invoice_dt is None and r["INVOICE_DT"] is not None:
            set_raw(doc, "legacy.invoiceDtRaw", r["INVOICE_DT"])
        if due_dt is None and r["DUE_DT"] is not None:
            set_raw(doc, "legacy.dueDtRaw", r["DUE_DT"])
        yield doc


def build_billing(conn, codes):
    """INVOICES with INVOICE_LINES as lines[] and DUNNING_ATTEMPTS as dunning[]."""
    lines: dict[str, list[dict]] = {}
    for r in rows(conn, "SELECT id, invoice_id, line_no, line_type, description, amount "
                        "FROM invoice_lines ORDER BY invoice_id, line_no"):
        lines.setdefault(r["INVOICE_ID"], []).append({
            "lineId": r["ID"],
            "lineNo": int(r["LINE_NO"]),
            "type": r["LINE_TYPE"],
            "description": r["DESCRIPTION"],
            "amount": money(r["AMOUNT"]),
        })
    dunning: dict[str, list[dict]] = {}
    for r in rows(conn, "SELECT id, invoice_id, attempt_no, scheduled_for, status_cd "
                        "FROM dunning_attempts ORDER BY invoice_id, attempt_no"):
        dunning.setdefault(r["INVOICE_ID"], []).append({
            "attemptNo": int(r["ATTEMPT_NO"]),
            "scheduledFor": utc(r["SCHEDULED_FOR"]),
            "status": decode(codes, "DUN_STATUS", r["STATUS_CD"]),
        })
    for r in rows(conn, "SELECT id, tenant_id, period_id, issued_at, subtotal, tax, "
                        "total, status_cd FROM invoices"):
        yield {"_id": r["ID"],
               "source": "billing",
               "tenantId": r["TENANT_ID"],
               "periodId": r["PERIOD_ID"],
               "invoiceDate": utc(r["ISSUED_AT"]),
               "status": decode(codes, "INV_STATUS", r["STATUS_CD"]),
               "totals": {"subtotal": money(r["SUBTOTAL"]),
                          "tax": money(r["TAX"]),
                          "total": money(r["TOTAL"])},
               "lines": lines.get(r["ID"], []),
               "dunning": dunning.get(r["ID"], [])}


def build_orphans(conn, _codes):
    """INVOICE_LINE rows with no header: the dangling invoiceId is kept as-is."""
    for r in rows(conn, LINE_SQL + " WHERE " + ORPHAN_PREDICATE + " ORDER BY line_id"):
        el = _conversion_line(r)
        doc = {"_id": el.pop("lineId"), "invoiceId": r["INVOICE_ID"]}
        doc.update(el)
        yield doc


# Exactly the indexes the mapping spec declares for invoices; the orphan collection
# declares none and gets none (M0: keep index counts modest).
INDEXES = {
    INVOICES: [({"tenantId": ASCENDING, "invoiceDate": DESCENDING}, {}),
               ({"customer.id": ASCENDING, "invoiceDate": DESCENDING}, {}),
               ({"invoiceNo": ASCENDING}, {"unique": True, "sparse": True}),
               ({"status": ASCENDING, "dueDate": ASCENDING}, {})],
    ORPHANS: [],
}


def _write(db, name, docs):
    ops, n, seen = [], 0, set()
    for doc in docs:
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        seen.add(doc["_id"])
        n += 1
        if len(ops) == BATCH:
            db[name].bulk_write(ops, ordered=False)
            ops = []
    if ops:
        db[name].bulk_write(ops, ordered=False)
    return n, seen


def load(drop: bool = False) -> dict[str, int]:
    conn = oracle_connect()
    db = mongo_db()
    counts: dict[str, int] = {}
    try:
        codes = load_codes(conn)
        if drop:
            db[INVOICES].drop()
            db[ORPHANS].drop()
        n_conv, seen = _write(db, INVOICES, build_conversion(conn, codes))
        n_bill, seen_bill = _write(db, INVOICES, build_billing(conn, codes))
        seen |= seen_bill
        n_orph, seen_orph = _write(db, ORPHANS, build_orphans(conn, codes))
        for name, kept in ((INVOICES, seen), (ORPHANS, seen_orph)):
            stale = [i for i in db[name].distinct("_id") if i not in kept]
            if stale:
                db[name].delete_many({"_id": {"$in": stale}})
                print(f"{name}: {len(stale)} stale removed")
            for keys, opts in INDEXES[name]:
                db[name].create_index(list(keys.items()), **opts)
        counts = {"invoices_conversion": n_conv, "invoices_billing": n_bill,
                  ORPHANS: n_orph}
        for k, v in counts.items():
            print(f"{k}: {v} documents")
    finally:
        conn.close()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drop", action="store_true",
                    help="drop both collections first (a clean reload)")
    args = ap.parse_args()
    load(drop=args.drop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
