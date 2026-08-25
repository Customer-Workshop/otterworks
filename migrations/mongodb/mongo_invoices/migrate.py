#!/usr/bin/env python3
"""Migrate the Oracle billing invoice estate into the invoices collection.

INVOICE_HEADER becomes one document per invoice with its INVOICE_LINE rows
embedded; the legacy DD-MON-YY text dates become BSON dates and every monetary
column crosses as BSON decimal. A line the estate cannot attribute to a header
-- or that carries a NULL amount, quantity or foreign key -- is written to the
quarantine collection with its source keys and a reason code instead of being
attached to a synthesized header or defaulted to zero.

Usage:
  migrations/mongodb/mongo_invoices/run.sh migrate --ns demo [--summary-out F]

Environment:
  DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_SERVICE  Oracle estate (defaults to
      the local fixture on port 52521)
  TP_MONGODB_URI                                  target document store
      (defaults to the local fixture at mongodb://localhost:27017)
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal

from bson.decimal128 import Decimal128
from pymongo import ReplaceOne

import common

HEADER_SQL = """
    SELECT invoice_id, invoice_no, cust_id, tenant_id, invoice_dt, due_dt,
           status_cd, total_amt, batch_no
      FROM invoice_header
     WHERE batch_no = :batch_no
"""

LINE_SQL = """
    SELECT line_id, invoice_no, invoice_id, cust_id, cust_no, cust_name,
           tenant_id, line_no, line_type_cd, item_desc, qty, unit_price,
           amount, tax_amt, invoice_dt, service_period, posted_yn,
           gl_acct_csv, batch_no, src_system
      FROM invoice_line
     WHERE batch_no = :batch_no
     ORDER BY invoice_id, line_no, line_id
"""

ZERO = Decimal("0.00")


def parsed_payload(line: dict) -> dict:
    """The source row's parsed fields, carried into quarantine unchanged.

    A quarantined line keeps everything that did parse -- including its money
    columns as BSON decimal -- so the estate's line-level checksum can be
    recomputed from the target store over the full source set.
    """
    parsed = {
        "line_no": int(line["line_no"]) if line.get("line_no") is not None else None,
        "line_type_code": (int(line["line_type_cd"])
                           if line.get("line_type_cd") is not None else None),
        "item_desc": line.get("item_desc"),
        "service_period": line.get("service_period"),
        "posted": line.get("posted_yn"),
        "gl_acct_csv": line.get("gl_acct_csv"),
        "invoice_dt_text": line.get("invoice_dt"),
        "src_system": line.get("src_system"),
        "cust_name": line.get("cust_name"),
    }
    for field, key in (("amount", "amount"), ("tax_amt", "tax_amt"),
                       ("qty", "qty"), ("unit_price", "unit_price")):
        value = line.get(field)
        parsed[key] = common.to_decimal128(value) if value is not None else None
    return parsed


class Quarantine:
    """Accumulates rejected and attributed source rows for one batch."""

    def __init__(self, ns: str):
        self.ns = ns
        self.docs: list[dict] = []
        self.by_reason: dict[str, int] = {}

    def add(self, reason: str, line: dict, detail: dict | None = None) -> None:
        doc = {
            "_id": common.quarantine_doc_id(self.ns, line["line_id"], reason),
            "ns": self.ns,
            "reason": reason,
            "source": {
                "system": common.SOURCE_SYSTEM,
                "schema": common.SOURCE_SCHEMA,
                "table": common.LINE_TABLE,
                "line_id": line["line_id"],
                "invoice_id": line["invoice_id"],
                "invoice_no": line["invoice_no"],
                "cust_id": line["cust_id"],
                "cust_no": line["cust_no"],
                "tenant_id": line["tenant_id"],
                "batch_no": (int(line["batch_no"])
                             if line.get("batch_no") is not None else None),
            },
            "parsed": parsed_payload(line),
        }
        if detail:
            doc.update(detail)
        self.docs.append(doc)
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1


def row_to_line(cursor_row, columns) -> dict:
    return dict(zip(columns, cursor_row))


def build_line(ns: str, raw: dict, quarantine: Quarantine):
    """Transform one INVOICE_LINE row, or quarantine it and return None."""
    for field, reason in (("amount", "null_amount"), ("tax_amt", "null_amount"),
                          ("qty", "null_quantity"), ("unit_price", "null_quantity")):
        if raw[field] is None:
            quarantine.add(reason, raw, {"detail": {"null_column": field}})
            return None
    if raw["invoice_id"] is None:
        quarantine.add("null_foreign_key", raw, {"detail": {"null_column": "invoice_id"}})
        return None

    for field in ("item_desc", "cust_name", "service_period", "gl_acct_csv"):
        raw_hex = common.undecodable_hex(raw[field])
        if raw_hex is not None:
            quarantine.add("invalid_encoding", raw,
                           {"detail": {"column": field, "raw_bytes_hex": raw_hex}})
            return None

    try:
        line_date = common.parse_legacy_date(raw["invoice_dt"])
    except ValueError as exc:
        quarantine.add("invalid_date", raw,
                       {"detail": {"column": "invoice_dt", "value": raw["invoice_dt"],
                                   "error": str(exc)}})
        return None

    gl_accounts, leftovers = common.parse_gl_accounts(raw["gl_acct_csv"])
    if leftovers:
        # tolerate-and-attribute: the line is migrated with the fields that did
        # parse, and the unattributed content is recorded in quarantine.
        quarantine.add("extra_delimited_fields", raw,
                       {"detail": {"column": "gl_acct_csv",
                                   "value": raw["gl_acct_csv"],
                                   "unattributed": leftovers},
                        "migrated": True})

    line = {
        "line_id": raw["line_id"],
        "line_no": int(raw["line_no"]) if raw["line_no"] is not None else None,
        "line_type_code": int(raw["line_type_cd"]) if raw["line_type_cd"] is not None else None,
        # free text crosses byte-for-byte: no trimming, no normalization
        "item_desc": raw["item_desc"],
        "qty": common.to_decimal128(raw["qty"]),
        "unit_price": common.to_decimal128(raw["unit_price"]),
        "amount": common.to_decimal128(raw["amount"]),
        "tax_amt": common.to_decimal128(raw["tax_amt"]),
        "line_date": line_date,
        "service_period": raw["service_period"],
        "posted": raw["posted_yn"],
        "gl_accounts": gl_accounts,
        "source": {
            "cust_id": raw["cust_id"],
            "cust_no": raw["cust_no"],
            "cust_name": raw["cust_name"],
            "tenant_id": raw["tenant_id"],
            "src_system": raw["src_system"],
        },
    }
    if leftovers:
        line["gl_accounts_unattributed"] = leftovers
    return line


def header_defect(header: dict) -> str | None:
    """Why this header cannot carry an invoice document, or None.

    Evaluated before any line is transformed, so a header the estate cannot
    represent takes its lines with it into quarantine instead of dropping them.
    """
    try:
        issue_date = common.parse_legacy_date(header["invoice_dt"])
        common.parse_legacy_date(header["due_dt"])
    except ValueError as exc:
        return str(exc)
    if issue_date is None:
        return "NULL INVOICE_DT is never defaulted"
    return None


def header_source(header: dict) -> dict:
    """The header row shaped as a quarantine source record."""
    return {"line_id": header["invoice_id"], "invoice_id": header["invoice_id"],
            "invoice_no": header["invoice_no"], "cust_id": header["cust_id"],
            "cust_no": None, "tenant_id": header["tenant_id"],
            "batch_no": header["batch_no"]}


def build_invoice(ns: str, header: dict, lines: list[dict], quarantine: Quarantine):
    """Assemble one invoice document, or quarantine an unusable header."""
    try:
        issue_date = common.parse_legacy_date(header["invoice_dt"])
        due_date = common.parse_legacy_date(header["due_dt"])
    except ValueError as exc:
        quarantine.add("invalid_date",
                       {"line_id": header["invoice_id"], "invoice_id": header["invoice_id"],
                        "invoice_no": header["invoice_no"], "cust_id": header["cust_id"],
                        "cust_no": None, "tenant_id": header["tenant_id"],
                        "batch_no": header["batch_no"]},
                       {"detail": {"table": common.HEADER_TABLE, "error": str(exc)}})
        return None
    if issue_date is None:
        quarantine.add("invalid_date",
                       {"line_id": header["invoice_id"], "invoice_id": header["invoice_id"],
                        "invoice_no": header["invoice_no"], "cust_id": header["cust_id"],
                        "cust_no": None, "tenant_id": header["tenant_id"],
                        "batch_no": header["batch_no"]},
                       {"detail": {"table": common.HEADER_TABLE,
                                   "error": "NULL INVOICE_DT is never defaulted"}})
        return None

    lines_total = sum((common.money(line["amount"]) for line in lines), ZERO)
    tax_total = sum((common.money(line["tax_amt"]) for line in lines), ZERO)
    header_total = (common.to_decimal128(header["total_amt"])
                    if header["total_amt"] is not None else None)

    return {
        "_id": common.invoice_doc_id(ns, header["invoice_id"]),
        "ns": ns,
        "invoice_no": header["invoice_no"],
        "issue_date": issue_date,
        "due_date": due_date,
        "status_code": int(header["status_cd"]) if header["status_cd"] is not None else None,
        "header_total": header_total,
        "lines_total": Decimal128(lines_total),
        "lines_tax_total": Decimal128(tax_total),
        "lines_count": len(lines),
        # The legacy estate does not derive the header total from its lines;
        # both values are carried across unchanged and the difference is
        # reported by recon rather than reconciled away here.
        "header_total_matches_lines": (
            header_total is not None and common.money(header_total) == lines_total
        ),
        "customer": {"cust_id": header["cust_id"], "tenant_id": header["tenant_id"]},
        "source": {
            "system": common.SOURCE_SYSTEM,
            "schema": common.SOURCE_SCHEMA,
            "table": common.HEADER_TABLE,
            "invoice_id": header["invoice_id"],
            "invoice_no": header["invoice_no"],
            "batch_no": int(header["batch_no"]) if header["batch_no"] is not None else None,
        },
        "lines": lines,
        "migration": {"unit": common.UNIT, "model_version": 1},
    }


def flush(collection, ops: list[ReplaceOne]) -> int:
    if not ops:
        return 0
    collection.bulk_write(ops, ordered=False)
    count = len(ops)
    ops.clear()
    return count


def sweep(collection, ns: str, keep_ids: set) -> int:
    """Remove documents of this namespace that the source no longer has.

    Scoped to `ns` so a rerun never touches another namespace's slice.
    """
    existing = {doc["_id"] for doc in collection.find({"ns": ns}, {"_id": 1})}
    stale = list(existing - keep_ids)
    for start in range(0, len(stale), 1000):
        collection.delete_many({"ns": ns, "_id": {"$in": stale[start:start + 1000]}})
    return len(stale)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", required=True)
    ap.add_argument("--batch-size", type=int, default=500,
                    help="documents per target write batch (per-batch trigger)")
    ap.add_argument("--summary-out", help="write the run summary as JSON to this path")
    args = ap.parse_args()

    ns = args.ns
    batch_no = common.batch_no(ns)
    conn = common.oracle_connect()
    cur = conn.cursor()
    cur.arraysize = 5000

    cur.execute("SELECT COUNT(*) FROM invoice_header WHERE batch_no = :batch_no",
                batch_no=batch_no)
    header_rows = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM invoice_line WHERE batch_no = :batch_no",
                batch_no=batch_no)
    line_rows = int(cur.fetchone()[0])

    if header_rows == 0 and line_rows == 0:
        # empty-input semantics: leave prior invoices untouched, exit zero, and
        # do not create or reconfigure anything in the target.
        summary = {"unit": common.UNIT, "ns": ns, "batch_no": batch_no,
                   "source": {"headers": 0, "lines": 0}, "action": "no-op",
                   "reason": "empty source set"}
        print(json.dumps(summary, indent=2))
        if args.summary_out:
            with open(args.summary_out, "w") as fh:
                fh.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        cur.close()
        conn.close()
        return 0

    client = common.mongo_client()
    db = client[common.db_name(ns)]
    qdb = client[common.quarantine_db_name(ns)]
    common.ensure_collection(db, common.COLLECTION, common.INVOICE_VALIDATOR,
                             common.INVOICE_INDEXES)
    common.ensure_collection(qdb, common.QUARANTINE_COLLECTION,
                             common.QUARANTINE_VALIDATOR, common.QUARANTINE_INDEXES)
    invoices = db[common.COLLECTION]
    quarantined = qdb[common.QUARANTINE_COLLECTION]

    cur.execute(HEADER_SQL, batch_no=batch_no)
    header_cols = [d[0].lower() for d in cur.description]
    headers = {}
    unusable_headers = {}
    for row in cur:
        header = row_to_line(row, header_cols)
        defect = header_defect(header)
        if defect is None:
            headers[header["invoice_id"]] = header
        else:
            unusable_headers[header["invoice_id"]] = (header, defect)

    quarantine = Quarantine(ns)
    for _, (header, defect) in sorted(unusable_headers.items()):
        quarantine.add("invalid_date", header_source(header),
                       {"detail": {"table": common.HEADER_TABLE, "error": defect}})

    lines_by_invoice: dict[str, list[dict]] = {}
    embedded_lines = 0

    cur.execute(LINE_SQL, batch_no=batch_no)
    line_cols = [d[0].lower() for d in cur.description]
    for row in cur:
        raw = row_to_line(row, line_cols)
        if raw["invoice_id"] is None:
            # a missing foreign key is its own defect, not an orphan: an orphan
            # names a header that does not exist, this line names none at all
            quarantine.add("null_foreign_key", raw,
                           {"detail": {"null_column": "invoice_id"}})
            continue
        if raw["invoice_id"] in unusable_headers:
            # the header cannot cross, so its lines are quarantined alongside it
            # rather than silently dropped or re-parented
            quarantine.add("header_unusable", raw,
                           {"detail": {"table": common.HEADER_TABLE,
                                       "error": unusable_headers[raw["invoice_id"]][1]}})
            continue
        if raw["invoice_id"] not in headers:
            # never attached to a synthesized or guessed header
            quarantine.add("orphan_no_header", raw)
            continue
        line = build_line(ns, raw, quarantine)
        if line is None:
            continue
        lines_by_invoice.setdefault(raw["invoice_id"], []).append(line)
        embedded_lines += 1

    ops: list[ReplaceOne] = []
    written = 0
    keep_ids = set()
    over_bounded = []
    max_lines = 0
    for invoice_id, header in sorted(headers.items()):
        lines = lines_by_invoice.get(invoice_id, [])
        # headers with a defect were separated out before any line was read, so
        # build_invoice cannot reject one here
        doc = build_invoice(ns, header, lines, quarantine)
        if doc is None:
            continue
        max_lines = max(max_lines, len(lines))
        if len(lines) > common.BOUNDED_LINES_PER_INVOICE:
            over_bounded.append({"invoice_no": header["invoice_no"], "lines": len(lines)})
        keep_ids.add(doc["_id"])
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if len(ops) >= args.batch_size:
            written += flush(invoices, ops)
    written += flush(invoices, ops)

    qops = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in quarantine.docs]
    q_written = 0
    for start in range(0, len(qops), args.batch_size):
        q_written += flush(quarantined, qops[start:start + args.batch_size])

    stale_invoices = sweep(invoices, ns, keep_ids)
    stale_quarantine = sweep(quarantined, ns, {doc["_id"] for doc in quarantine.docs})

    summary = {
        "unit": common.UNIT,
        "ns": ns,
        "batch_no": batch_no,
        "run_mode": common.run_mode(),
        "action": "migrated",
        "source": {"headers": header_rows, "lines": line_rows},
        "target": {
            "database": common.db_name(ns),
            "collection": common.COLLECTION,
            "quarantine_database": common.quarantine_db_name(ns),
            "quarantine_collection": common.QUARANTINE_COLLECTION,
        },
        "written": {"invoices": written, "quarantined": q_written},
        "embedded_lines": embedded_lines,
        "quarantined_by_reason": dict(sorted(quarantine.by_reason.items())),
        "swept_stale": {"invoices": stale_invoices, "quarantine": stale_quarantine},
        "bounded_model": {
            "limit": common.BOUNDED_LINES_PER_INVOICE,
            "max_lines_on_one_invoice": max_lines,
            "invoices_over_limit": len(over_bounded),
            "over_limit_sample": sorted(over_bounded,
                                        key=lambda e: (-e["lines"], e["invoice_no"]))[:10],
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.summary_out:
        with open(args.summary_out, "w") as fh:
            fh.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    cur.close()
    conn.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
