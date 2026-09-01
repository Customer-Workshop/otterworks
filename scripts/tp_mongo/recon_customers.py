"""Recon gate for the `customers` unit: tiers 1-3 plus the Tier 4 parity replay.

The CLI cannot run this unit on its own. `--unit` is a label there — the engine grades every
collection in the mapping spec, so a wave-1 run would also grade `invoices`, which wave 2 has
not loaded yet (profile feedback H3). This runner grades the same approved spec, restricted
to the one collection this unit owns, and supplies the `run_source` / `run_target` executors
Tier 4 needs, which the CLI has no way to pass.

Both Tier 4 operations come from the estate's own read paths (census §3): the reconciliation
report endpoint, and the case-insensitive customer lookup that D6's collation index replaces
`CUST_NAME_UPPER` with.

    python3 scripts/tp_mongo/recon_customers.py --ns demo \
        --source-dsn-secret OW_BILLING_SOURCE_DSN --target-uri-secret MONGODB_ATLAS_URI \
        --target-db ow_tp_demo --out .migration/recon/customers/
"""

from __future__ import annotations

import argparse
import dataclasses
import decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import mongo_database, ns_batch_no, oracle_connect, secret

UNIT = "customers"

# The reconciliation endpoint's own SQL (`services/legacy-billing/app/reports.py`).
BALANCES_SQL = """
SELECT COUNT(*)                                          AS customer_count,
       TO_CHAR(SUM(cur_bal_amt), 'FM999999999999990.00') AS current_balance_total,
       TO_CHAR(SUM(past_due_amt), 'FM999999999999990.00') AS past_due_total
  FROM OW_BILLING.CUSTOMER_MASTER
 WHERE conversion_batch_no = :batch_no
"""

# The estate's case-insensitive name lookup: the trigger-maintained shadow column.
NAME_LOOKUP_SQL = """
SELECT cust_no, cust_name, status_cd
  FROM OW_BILLING.CUSTOMER_MASTER
 WHERE conversion_batch_no = :batch_no
   AND cust_name_upper LIKE :pattern
 ORDER BY cust_no
"""


def money(value) -> str:
    """The report contract renders amounts as strings with two decimals."""
    return f"{decimal.Decimal(str(value)).quantize(decimal.Decimal('0.01')):f}"


def build_ops(name_pattern: str) -> list[dict]:
    return [
        {"name": "reconciliation-report-balances", "collection": UNIT,
         "kind": "balances", "rules": []},
        {"name": "case-insensitive-name-lookup", "collection": UNIT,
         "kind": "name_lookup", "pattern": name_pattern, "rules": ["rstrip_spaces"]},
    ]


def source_runner(connection, batch_no: int):
    def run(op: dict) -> list[dict]:
        with connection.cursor() as cursor:
            if op["kind"] == "balances":
                cursor.execute(BALANCES_SQL, batch_no=batch_no)
                count, current_total, past_due_total = cursor.fetchone()
                return [{"customer_count": count,
                         "current_balance_total": current_total,
                         "past_due_total": past_due_total}]
            cursor.execute(NAME_LOOKUP_SQL, batch_no=batch_no,
                           pattern=op["pattern"].upper())
            return [{"cust_no": cust_no, "cust_name": name, "status_cd": status}
                    for cust_no, name, status in cursor]

    return run


def target_runner(db, ns: str):
    customers = db["customers"]

    def run(op: dict) -> list[dict]:
        if op["kind"] == "balances":
            rollup = next(customers.aggregate([
                {"$match": {"ns": ns}},
                {"$group": {"_id": None, "customer_count": {"$sum": 1},
                            "current_balance_total": {"$sum": "$cur_bal_amt"},
                            "past_due_total": {"$sum": "$past_due_amt"}}},
            ]))
            return [{"customer_count": rollup["customer_count"],
                     "current_balance_total": money(rollup["current_balance_total"]),
                     "past_due_total": money(rollup["past_due_total"])}]
        # D6: case-insensitive matching on `cust_name` itself, with no shadow column.
        regex = op["pattern"].replace("%", ".*")
        cursor = customers.find(
            {"ns": ns, "cust_name": {"$regex": f"^{regex}$", "$options": "i"}},
            {"cust_name": 1, "status_cd": 1}).sort("_id", 1)
        return [{"cust_no": d["_id"], "cust_name": d["cust_name"],
                 "status_cd": d["status_cd"]} for d in cursor]

    return run


def unit_spec(spec):
    """The approved spec, restricted to the collection this unit owns. Version unchanged:
    this is a view of mapping v1.0.0, not an edit of it."""
    collections = [c for c in spec.collections if c.collection == UNIT]
    if not collections:
        raise SystemExit(f"mapping spec has no '{UNIT}' collection")
    return dataclasses.replace(spec, collections=collections)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recon_customers")
    p.add_argument("--ns", default="demo")
    p.add_argument("--source-dsn-secret", required=True)
    p.add_argument("--target-uri-secret", required=True)
    p.add_argument("--target-db", required=True)
    p.add_argument("--mapping", type=Path, default=Path(".migration/03_mapping_spec.json"))
    p.add_argument("--tolerances", type=Path, default=Path(".migration/02_tolerances.json"))
    p.add_argument("--canonicalization", type=Path,
                   default=Path(".migration/profile.canon.json"))
    p.add_argument("--mode", default="live")
    p.add_argument("--name-pattern", default="A%",
                   help="LIKE pattern for the Tier 4 case-insensitive lookup")
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
                           ops=build_ops(args.name_pattern),
                           run_source=source_runner(connection, ns_batch_no(args.ns)),
                           run_target=target_runner(db, args.ns), out_dir=args.out)
    print(f"recon {result['verdict']}: unit={UNIT} mode={args.mode} "
          f"mapping={spec.version} tolerances={tol.version} -> {args.out}/result.json")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
