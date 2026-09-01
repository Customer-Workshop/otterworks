"""Recon gate for the `invoices` unit: tiers 1-3 plus the Tier 4 parity replay.

Same shape as the `customers` runner: the CLI grades every collection in the mapping spec, so
it cannot run one unit on its own (profile feedback H3). This runner grades the approved spec
restricted to the collection this unit owns and supplies the `run_source` / `run_target`
executors Tier 4 needs.

Both Tier 4 operations are the month-end finance report's own two queries (census §3,
`services/legacy-billing/app/reports.py`): the header rollup by status, and the line rollup by
status and line type. They are the reason `lines[]` is embedded (D1) — the report reads lines
only through their header, and its join drops exactly the orphaned lines the loader
quarantines. `CODES` is out of unit scope, so the status and line-type descriptions come from
the static map D8 approved, reproducing the estate's `UNKNOWN(<cd>)` for unmapped codes.

    python3 scripts/tp_mongo/recon_invoices.py --ns demo \
        --source-dsn-secret OW_BILLING_SOURCE_DSN --target-uri-secret MONGODB_ATLAS_URI \
        --target-db ow_tp_demo --out .migration/recon/invoices/
"""

from __future__ import annotations

import argparse
import dataclasses
import decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import mongo_database, ns_batch_no, oracle_connect, secret

UNIT = "invoices"

# D8's static lookup, standing in for the out-of-scope `CODES` table.
STATUS_DESC = {10: "draft", 20: "issued", 30: "paid", 40: "overdue"}
LINE_TYPE_DESC = {1: "CHARGE", 2: "CREDIT", 3: "ADJUSTMENT", 9: "MISC"}

# The month-end endpoint's own SQL, verbatim except for the schema qualifier.
STATUS_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       COUNT(*)                                                     AS invoice_count,
       TO_CHAR(SUM(h.total_amt), 'FM999999999999990.00')            AS header_total_amt
  FROM OW_BILLING.INVOICE_HEADER h,
       OW_BILLING.CODES st
 WHERE h.batch_no = :batch_no
   AND st.code_type (+) = 'INV_STATUS'
   AND st.code_val  (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')')
 ORDER BY 1
"""

LINE_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       DECODE(l.line_type_cd, 1, 'CHARGE',
                              2, 'CREDIT',
                              3, 'ADJUSTMENT',
                              9, 'MISC',
                              'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')') AS line_type,
       COUNT(*)                                                     AS line_count,
       TO_CHAR(SUM(l.amount),  'FM999999999999990.00')              AS line_amount,
       TO_CHAR(SUM(l.tax_amt), 'FM999999999999990.00')              AS line_tax,
       COUNT(DISTINCT h.invoice_id)                                 AS invoices_touched
  FROM OW_BILLING.INVOICE_HEADER h,
       OW_BILLING.INVOICE_LINE   l,
       OW_BILLING.CODES          st
 WHERE h.batch_no = :batch_no
   AND h.invoice_id = l.invoice_id
   AND st.code_type (+) = 'INV_STATUS'
   AND st.code_val  (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')'),
          DECODE(l.line_type_cd, 1, 'CHARGE',
                                 2, 'CREDIT',
                                 3, 'ADJUSTMENT',
                                 9, 'MISC',
                                 'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')')
 ORDER BY 1, 2
"""


def money(value) -> str:
    """The report contract renders amounts as strings with two decimals."""
    return f"{decimal.Decimal(str(value)).quantize(decimal.Decimal('0.01')):f}"


def described(code, descriptions: dict[int, str]) -> str:
    """The estate's own rendering: the code's description, or `UNKNOWN(<cd>)` for a code the
    lookup does not carry — including a NULL one, which Oracle prints as `UNKNOWN()`."""
    if code is None:
        return "UNKNOWN()"
    return descriptions.get(int(code), f"UNKNOWN({int(code)})")


def build_ops() -> list[dict]:
    return [
        {"name": "month-end-by-status", "collection": UNIT, "kind": "by_status", "rules": []},
        {"name": "month-end-by-status-line-type", "collection": UNIT,
         "kind": "by_status_line_type", "rules": []},
    ]


def source_runner(connection, batch_no: int):
    def run(op: dict) -> list[dict]:
        with connection.cursor() as cursor:
            if op["kind"] == "by_status":
                cursor.execute(STATUS_SQL, batch_no=batch_no)
                return [{"status": status, "invoice_count": count, "header_total_amt": total}
                        for status, count, total in cursor]
            cursor.execute(LINE_SQL, batch_no=batch_no)
            return [{"status": status, "line_type": line_type, "line_count": count,
                     "line_amount": amount, "line_tax": tax, "invoices_touched": touched}
                    for status, line_type, count, amount, tax, touched in cursor]

    return run


def target_runner(db, ns: str):
    invoices = db["invoices"]

    def by_status() -> list[dict]:
        rollup = invoices.aggregate([
            {"$match": {"ns": ns}},
            {"$group": {"_id": "$status_cd", "invoice_count": {"$sum": 1},
                        "header_total_amt": {"$sum": "$total_amt"}}},
        ])
        rows = [{"status": described(g["_id"], STATUS_DESC),
                 "invoice_count": g["invoice_count"],
                 "header_total_amt": money(g["header_total_amt"])} for g in rollup]
        return sorted(rows, key=lambda r: r["status"])

    def by_status_line_type() -> list[dict]:
        # `$unwind` is the aggregation-pipeline equivalent of the report's header-to-line
        # join; an invoice with no lines contributes nothing, exactly as the join does.
        rollup = invoices.aggregate([
            {"$match": {"ns": ns}},
            {"$unwind": "$lines"},
            {"$group": {"_id": {"status_cd": "$status_cd",
                                "line_type_cd": "$lines.line_type_cd"},
                        "line_count": {"$sum": 1},
                        "line_amount": {"$sum": "$lines.amount"},
                        "line_tax": {"$sum": "$lines.tax_amt"},
                        "invoices": {"$addToSet": "$_id"}}},
        ])
        rows = [{"status": described(g["_id"]["status_cd"], STATUS_DESC),
                 "line_type": described(g["_id"]["line_type_cd"], LINE_TYPE_DESC),
                 "line_count": g["line_count"],
                 "line_amount": money(g["line_amount"]),
                 "line_tax": money(g["line_tax"]),
                 "invoices_touched": len(g["invoices"])} for g in rollup]
        return sorted(rows, key=lambda r: (r["status"], r["line_type"]))

    def run(op: dict) -> list[dict]:
        return by_status() if op["kind"] == "by_status" else by_status_line_type()

    return run


def unit_spec(spec):
    """The approved spec, restricted to the collection this unit owns. Version unchanged:
    this is a view of mapping v1.0.0, not an edit of it."""
    collections = [c for c in spec.collections if c.collection == UNIT]
    if not collections:
        raise SystemExit(f"mapping spec has no '{UNIT}' collection")
    return dataclasses.replace(spec, collections=collections)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recon_invoices")
    p.add_argument("--ns", default="demo")
    p.add_argument("--source-dsn-secret", required=True)
    p.add_argument("--target-uri-secret", required=True)
    p.add_argument("--target-db", required=True)
    p.add_argument("--mapping", type=Path, default=Path(".migration/03_mapping_spec.json"))
    p.add_argument("--tolerances", type=Path, default=Path(".migration/02_tolerances.json"))
    p.add_argument("--canonicalization", type=Path,
                   default=Path(".migration/profile.canon.json"))
    p.add_argument("--mode", default="live")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    from recon.adapters import MongoTargetAdapter, OracleSourceAdapter
    from recon.config import load_canon_rules, load_mapping_spec, load_tolerances
    from recon.engine import run_recon

    spec = unit_spec(load_mapping_spec(args.mapping))
    tol = load_tolerances(args.tolerances)
    rules = load_canon_rules(args.canonicalization)
    source = OracleSourceAdapter(args.source_dsn_secret)
    target = MongoTargetAdapter(args.target_uri_secret, args.target_db)

    secret(args.source_dsn_secret)  # fail fast on a missing NAME, before any connection
    connection = oracle_connect(args.source_dsn_secret)
    db = mongo_database(args.target_uri_secret, args.target_db)
    with connection:
        result = run_recon(UNIT, args.mode, spec, tol, rules, source, target,
                           ops=build_ops(),
                           run_source=source_runner(connection, ns_batch_no(args.ns)),
                           run_target=target_runner(db, args.ns), out_dir=args.out)
    print(f"recon {result['verdict']}: unit={UNIT} mode={args.mode} "
          f"mapping={spec.version} tolerances={tol.version} -> {args.out}/result.json")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
