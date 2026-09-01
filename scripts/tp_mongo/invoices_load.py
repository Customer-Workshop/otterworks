"""Wave 2 loader: OW_BILLING.INVOICE_HEADER + INVOICE_LINE -> ow_tp_demo.invoices.

Reads the legacy estate with SELECTs only and writes one document per invoice, keyed by the
natural business key `INVOICE_ID`, with its lines embedded as `lines[]` (D1: lines are only
ever read through their header, at most 23 per invoice).

The estate declares no foreign key from `INVOICE_LINE` to `INVOICE_HEADER`, so some lines
point at an invoice that does not exist. Those cannot be embedded anywhere: they are written
to the quarantine database, one record per line, and the count is reported.

Idempotent: every run clears this namespace's documents from the collections it owns and
reloads them, so a retry starts clean.

    python3 scripts/tp_mongo/invoices_load.py --ns demo \
        --source-dsn-secret OW_BILLING_SOURCE_DSN --target-uri-secret MONGODB_ATLAS_URI \
        --target-db ow_tp_demo --quarantine-db ow_tp_demo_quarantine
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pymongo import ASCENDING, InsertOne

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CONVENTIONS,
    MAPPING_SPEC,
    assert_target,
    canonical,
    load_fields,
    mongo_database,
    oracle_connect,
    parse_legacy_date,
    put,
)

UNIT = "invoices"
ROOT_TABLE = "OW_BILLING.INVOICE_HEADER"
LINE_TABLE = "OW_BILLING.INVOICE_LINE"
BATCH_SIZE = 1000

# Typed fields derived from the estate's `DD-MON-YY` string dates; the raw string stays under
# `legacy.*`, which is what the mapping spec compares (D4, H2).
DERIVED_DATES = [("INVOICE_DT", "invoice_at"), ("DUE_DT", "due_at")]

# Every `INVOICE_LINE` column, with its target and BSON type. Lines are not graded field by
# field by the mapping (an embed carries cardinality only), so the loader is where their
# shape is stated: money and quantities are Decimal128, the header's own columns are copied
# under `legacy.` to mark them as the denormalized duplicates they are, and the text the
# estate stores as `DD-MON-YY` or a delimited list is preserved verbatim.
LINE_FIELDS = [
    ("LINE_ID", "line_id", "string"),
    ("LINE_NO", "line_no", "long"),
    ("LINE_TYPE_CD", "line_type_cd", "long"),
    ("ITEM_DESC", "item_desc", "string"),
    ("QTY", "qty", "decimal"),
    ("UNIT_PRICE", "unit_price", "decimal"),
    ("AMOUNT", "amount", "decimal"),
    ("TAX_AMT", "tax_amt", "decimal"),
    ("SERVICE_PERIOD", "service_period", "string"),
    ("POSTED_YN", "posted_yn", "string"),
    ("SRC_SYSTEM", "src_system", "string"),
    ("BATCH_NO", "batch_no", "long"),
    ("INVOICE_NO", "legacy.invoice_no", "string"),
    ("CUST_ID", "legacy.cust_id", "string"),
    ("CUST_NO", "legacy.cust_no", "string"),
    ("CUST_NAME", "legacy.cust_name", "string"),
    ("TENANT_ID", "legacy.tenant_id", "string"),
    ("INVOICE_DT", "legacy.invoice_dt", "string"),
    ("GL_ACCT_CSV", "legacy.gl_acct_csv", "string"),
]

# `POSTED_YN` is the one CHAR column on the line table; the rest are VARCHAR2, whose blanks
# are data (the estate stores meaningful all-blank legacy date strings).
LINE_RULES = {"POSTED_YN": ["rstrip_spaces", "empty_string_is_null"]}


# The estate's own rendering of a missing `DD-MON-YY`: the separators in place with each
# field blanked to its own width, right-trim tolerated. Deliberately exact — anything else,
# punctuation included, is a malformed date and is quarantined.
BLANK_LEGACY_DATE = re.compile(r" {2}- {3}- {0,2}")


def absent_legacy_date(raw) -> bool:
    return raw is None or raw == "" or BLANK_LEGACY_DATE.fullmatch(raw) is not None


def line_document(row: dict) -> tuple[dict, dict | None]:
    """One embedded line, plus the quarantine record for its legacy date if the estate's own
    conversion could not parse it (D4, the same field-level policy the headers follow).

    The raw string is preserved either way; only the typed `invoice_at` is withheld, and the
    anomaly is counted rather than disappearing.
    """
    line: dict = {}
    for column, target, bson_type in LINE_FIELDS:
        put(line, target, canonical(row[column], bson_type, LINE_RULES.get(column, [])))
    raw = row["INVOICE_DT"]
    if absent_legacy_date(raw):
        return line, None
    parsed = parse_legacy_date(raw)
    if parsed is None:
        return line, {"field": "INVOICE_DT", "reason": "unparseable_legacy_date",
                      "raw_value": raw, "line_id": row["LINE_ID"],
                      "invoice_id": row["INVOICE_ID"]}
    line["invoice_at"] = parsed
    return line, None


def fetch_lines(cursor, batch_no: int) -> tuple[dict[str, list[dict]], list[dict], list[dict]]:
    """This batch's lines, grouped by the invoice they belong to, the ones that belong to no
    invoice at all, and the field-level quarantine records the embedded ones raised.

    Ordered by `LINE_ID`, not `LINE_NO`: `LINE_NO` repeats within an invoice, so it is not a
    line identity and cannot order the array deterministically.
    """
    columns = [column for column, _, _ in LINE_FIELDS]
    cursor.execute(
        f"SELECT l.INVOICE_ID, {', '.join('l.' + c for c in columns)}, "
        f"       CASE WHEN EXISTS (SELECT 1 FROM {ROOT_TABLE} h "
        f"                          WHERE h.INVOICE_ID = l.INVOICE_ID "
        f"                            AND h.BATCH_NO = :b) THEN 1 ELSE 0 END AS HAS_HEADER "
        f"  FROM {LINE_TABLE} l WHERE l.BATCH_NO = :b ORDER BY l.LINE_ID", b=batch_no)

    by_invoice: dict[str, list[dict]] = {}
    orphans: list[dict] = []
    quarantine: list[dict] = []
    for row in cursor:
        record = dict(zip(["INVOICE_ID"] + columns + ["HAS_HEADER"], row))
        line, bad_date = line_document(record)
        if record["HAS_HEADER"]:
            by_invoice.setdefault(record["INVOICE_ID"], []).append(line)
            # An orphan's whole line is quarantined below, so a second record for its date
            # would double-count the same row.
            if bad_date is not None:
                quarantine.append(bad_date)
        else:
            orphans.append({"reason": "orphan_invoice_line",
                            "invoice_id": record["INVOICE_ID"], "line": line})
    return by_invoice, orphans, quarantine


def build_document(row: dict, fields, lines: list[dict], ns: str) -> tuple[dict, list[dict]]:
    doc: dict = {"ns": ns}
    quarantine: list[dict] = []
    for column, target, bson_type, rules in fields:
        put(doc, target, canonical(row[column], bson_type, rules))

    for column, target in DERIVED_DATES:
        raw = row[column]
        if absent_legacy_date(raw):
            continue
        parsed = parse_legacy_date(raw)
        if parsed is None:
            quarantine.append({"field": column, "reason": "unparseable_legacy_date",
                               "raw_value": raw,
                               "_id": f"{ns}:{row['INVOICE_ID']}:{column}",
                               "invoice_id": row["INVOICE_ID"]})
        else:
            doc[target] = parsed

    doc["lines"] = lines
    for q in quarantine:
        q.update({"ns": ns, "unit": UNIT})
    return doc, quarantine


def line_quarantine_document(record: dict, ns: str) -> dict:
    return dict(record, _id=f"{ns}:{record['line_id']}:{record['field']}", ns=ns, unit=UNIT)


def orphan_document(orphan: dict, ns: str) -> dict:
    """An orphan is quarantined whole: the line has no header to embed it in, so the record
    carries the line itself rather than a pointer to a document that does not exist."""
    return {"_id": f"{ns}:{orphan['line']['line_id']}", "ns": ns, "unit": UNIT,
            "reason": orphan["reason"], "field": "INVOICE_ID",
            "invoice_id": orphan["invoice_id"], "line_id": orphan["line"]["line_id"],
            "line": orphan["line"]}


def ensure_indexes(collection) -> None:
    """D9's index plan for `invoices`, derived from the month-end report's read paths: the
    status rollup, the per-customer invoice list, and the line lookup by identity."""
    collection.create_index([("batch_no", ASCENDING), ("status_cd", ASCENDING)],
                            name="batch_status")
    collection.create_index([("cust_id", ASCENDING), ("legacy.invoice_dt", ASCENDING)],
                            name="cust_invoice_dt")
    # `INVOICE_NO` is unique per conversion batch, not across the collection: the uniqueness
    # constraint is scoped to the namespace so a second namespace can be loaded beside this
    # one without the two colliding.
    collection.create_index([("ns", ASCENDING), ("invoice_no", ASCENDING)],
                            name="ns_invoice_no_unique", unique=True)
    collection.create_index([("lines.line_id", ASCENDING)], name="lines_line_id")


def assert_source_slice(cursor, batch_no: int, mapped: set[str]) -> int:
    """Preconditions checked before a single document is written, because both of them make
    the load destructive rather than wrong:

    - the batch must hold headers. An empty answer (wrong batch number, a source outage)
      would otherwise clear the namespace and report a successful load of nothing.
    - every header column must be in the mapping. Unlike `CUSTOMER_MASTER`, this table has
      no retired columns, so a column appearing here is new source data the load would drop
      silently and recon could not see.
    """
    cursor.execute(f"SELECT COUNT(*) FROM {ROOT_TABLE} WHERE BATCH_NO = :b", b=batch_no)
    rows = int(cursor.fetchone()[0])
    if rows == 0:
        raise SystemExit(f"{ROOT_TABLE} has no rows for BATCH_NO={batch_no}; "
                         f"refusing to clear the target for an empty source")

    cursor.execute("SELECT column_name FROM all_tab_columns "
                   "WHERE owner = 'OW_BILLING' AND table_name = 'INVOICE_HEADER' "
                   "ORDER BY column_id")
    unmapped = [c for (c,) in cursor if c not in mapped]
    if unmapped:
        raise SystemExit(
            "columns on the invoice header are absent from the approved mapping, so the load "
            f"would drop them: {', '.join(unmapped)}")
    return rows


def load(ns: str, source_dsn_secret: str, target_uri_secret: str, target_db: str,
         quarantine_db: str, spec_path: Path = MAPPING_SPEC,
         conventions_path: Path = CONVENTIONS) -> dict:
    batch_no = assert_target(ns, conventions_path, target_uri_secret,
                             target_db=target_db, quarantine_db=quarantine_db)
    fields = load_fields(spec_path, UNIT)
    db = mongo_database(target_uri_secret, target_db)
    qdb = mongo_database(target_uri_secret, quarantine_db)
    invoices, quarantined = db["invoices"], qdb["invoices"]

    connection = oracle_connect(source_dsn_secret)
    with connection, connection.cursor() as cursor:
        cursor.arraysize = BATCH_SIZE
        columns = [f[0] for f in fields]
        assert_source_slice(cursor, batch_no, set(columns))

        lines_by_invoice, orphans, line_quarantine = fetch_lines(cursor, batch_no)

        cursor.execute(f"SELECT {', '.join(columns)} FROM {ROOT_TABLE} "
                       f" WHERE BATCH_NO = :b ORDER BY INVOICE_ID", b=batch_no)
        names = [d[0] for d in cursor.description]

        # A retry starts clean: this namespace's slice is removed before it is rewritten.
        invoices.delete_many({"ns": ns})
        quarantined.delete_many({"ns": ns, "unit": UNIT})

        loaded = embedded = 0
        docs: list[InsertOne] = []
        quarantine_docs = [InsertOne(orphan_document(o, ns)) for o in orphans]
        quarantine_docs += [InsertOne(line_quarantine_document(q, ns)) for q in line_quarantine]
        for row in cursor:
            record = dict(zip(names, row))
            doc, quarantine = build_document(
                record, fields, lines_by_invoice.get(record["INVOICE_ID"], []), ns)
            embedded += len(doc["lines"])
            docs.append(InsertOne(doc))
            quarantine_docs.extend(InsertOne(q) for q in quarantine)
            if len(docs) >= BATCH_SIZE:
                invoices.bulk_write(docs, ordered=False)
                loaded += len(docs)
                docs = []
        if docs:
            invoices.bulk_write(docs, ordered=False)
            loaded += len(docs)
        if quarantine_docs:
            quarantined.bulk_write(quarantine_docs, ordered=False)

    ensure_indexes(invoices)
    reasons: dict[str, int] = {}
    for q in quarantined.find({"ns": ns, "unit": UNIT}, {"reason": 1}):
        reasons[q["reason"]] = reasons.get(q["reason"], 0) + 1
    return {"unit": UNIT, "ns": ns, "batch_no": batch_no,
            "target": f"{target_db}.invoices", "loaded": loaded,
            "embedded_lines": embedded,
            "quarantine_target": f"{quarantine_db}.invoices",
            "quarantined": sum(reasons.values()), "quarantine_by_reason": reasons}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="invoices_load")
    p.add_argument("--ns", default="demo")
    p.add_argument("--source-dsn-secret", required=True,
                   help="ENV VAR NAME holding the read-only source DSN")
    p.add_argument("--target-uri-secret", required=True,
                   help="ENV VAR NAME holding the migration-cluster URI")
    p.add_argument("--target-db", required=True)
    p.add_argument("--quarantine-db", required=True)
    p.add_argument("--mapping", type=Path, default=MAPPING_SPEC)
    args = p.parse_args(argv)
    print(json.dumps(load(args.ns, args.source_dsn_secret, args.target_uri_secret,
                          args.target_db, args.quarantine_db, args.mapping), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
