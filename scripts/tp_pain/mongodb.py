#!/usr/bin/env python3
"""Beat 1 "legacy pain" opener for the MongoDB demo track.

One command, ~90 seconds of story: a routine business ask — "add one field to
the customer record" — rendered as its real blast radius across the Oracle
billing estate, plus live proof that the 156th field already shipped through
the ENTITY_ATTR_VALUE escape hatch because the schema could not say no.

Everything printed is deterministic for a given namespace: the live numbers
come from the seeded fixture (seeded RNG derived from NS) and the repo scan
walks a fixed file list in sorted order.

Run via `make tp-pain-mongodb NS=<ns>` (wraps scripts/tp-pain-mongodb.sh).
Requires the Oracle billing fixture (`make oracle-billing-up`) seeded for the
namespace (`make oracle-billing-seed NS=<ns>`). Read-only: issues SELECTs.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import oracledb

REPO_ROOT = Path(__file__).resolve().parents[2]

# Deterministic blast-radius scan: every repo artifact that names the
# CUSTOMER_MASTER layout and would need review (or silently break) if a
# column were added. Paths are fixed and walked in order.
TOUCH_POINTS = [
    ("schema DDL", "services/legacy-billing/db/oracle/schema/02_horror.sql",
     "table + 158-column _HIST copy + sequences"),
    ("stored PL/SQL", "services/legacy-billing/db/oracle/schema/02_horror.sql",
     "trg_customer_master_hist names every column, twice"),
    ("report query", "services/legacy-billing/app/reports.py",
     "RPT-114 reconciliation BALANCES_SQL selects from the table"),
    ("parity harness", "procs/harness/oracle_record.py",
     "golden Oracle transcripts recorded against this schema"),
    ("seeder/manifest", "testdata/legacy/oracle_billing_seed.py",
     "deterministic seeder inserts + manifest checksums over the layout"),
    ("estate docs", "services/legacy-billing/db/oracle/README.md",
     "the estate's own map of the horror tables"),
    ("ops process", "services/legacy-billing/db/oracle/ops/OPERATIONS_HANDBOOK.doc.txt",
     "CUSTOMER_MASTER_LAYOUT.xls (last updated 2011) + CAB approval"),
]

PATTERN = re.compile(r"customer_master", re.IGNORECASE)


def hr(char: str = "-") -> None:
    print(char * 72)


def ns_batch_no(ns: str) -> int:
    """Mirror testdata/legacy/legacy_common.ns_seed + oracle_billing_seed."""
    seed = int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)
    return seed % 90_000_000 + 1_000_000


def connect(args: argparse.Namespace):
    return oracledb.connect(user=args.user, password=args.password,
                            host=args.host, port=args.port,
                            service_name=args.service)


def one(cur, sql: str, **binds):
    cur.execute(sql, binds)
    return cur.fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", required=True, help="seeded namespace, e.g. demo")
    ap.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--password",
                    default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    args = ap.parse_args()

    started = time.monotonic()
    batch_no = ns_batch_no(args.ns)

    print()
    hr("=")
    print('TP DEMO / Beat 1 — "just add a field" (MongoDB track)')
    hr("=")
    print("The ask: Finance wants ONE new customer field: PREFERRED_CURRENCY_CD.")
    print(f"The estate: OW_BILLING @ {args.host}:{args.port}/{args.service}, "
          f"ns={args.ns} (batch {batch_no})")

    try:
        conn = connect(args)
    except (oracledb.Error, OSError) as exc:
        print(f"\nERROR: cannot reach the Oracle billing fixture: {exc}",
              file=sys.stderr)
        print("Start it first:  make oracle-billing-up", file=sys.stderr)
        return 2
    cur = conn.cursor()

    n_rows = one(cur, "SELECT COUNT(*) FROM customer_master "
                      "WHERE conversion_batch_no = :b", b=batch_no)
    if n_rows == 0:
        print(f"\nERROR: namespace '{args.ns}' has no seeded rows.",
              file=sys.stderr)
        print(f"Seed it first:  make oracle-billing-seed NS={args.ns}",
              file=sys.stderr)
        return 2

    n_cols = one(cur, "SELECT COUNT(*) FROM user_tab_columns "
                      "WHERE table_name = 'CUSTOMER_MASTER'")
    n_hist_cols = one(cur, "SELECT COUNT(*) FROM user_tab_columns "
                           "WHERE table_name = 'CUSTOMER_MASTER_HIST'")
    n_triggers = one(cur, "SELECT COUNT(*) FROM user_triggers "
                          "WHERE table_name = 'CUSTOMER_MASTER'")

    print()
    print("[1] The table you would be changing (live from Oracle)")
    hr()
    print(f"  CUSTOMER_MASTER            {n_cols} columns, "
          f"{n_rows:,} rows in ns '{args.ns}'")
    print(f"  CUSTOMER_MASTER_HIST       {n_hist_cols} columns "
          "(full row copy + audit columns)")
    print(f"  triggers on the table      {n_triggers} — the history trigger "
          "names EVERY column")
    print("  => one new column = table + hist table + trigger column lists, "
          "in lockstep,")
    print("     or UPDATEs silently stop being audited.")

    print()
    print("[2] Blast radius in this repo (deterministic scan)")
    hr()
    total_refs = 0
    seen: set[str] = set()
    for category, rel_path, why in TOUCH_POINTS:
        path = REPO_ROOT / rel_path
        refs = len(PATTERN.findall(path.read_text(encoding="utf-8",
                                                  errors="replace")))
        if rel_path not in seen:
            seen.add(rel_path)
            total_refs += refs
        print(f"  {category:<16} {rel_path}")
        print(f"  {'':<16}   {refs:>3} reference(s) — {why}")
    print(f"  => {total_refs} CUSTOMER_MASTER references across "
          f"{len(seen)} files — and the prod DDL path is")
    print("     deploy_prod_FINAL_v2.sh.txt: alphabetical *.sql, errors "
          "swallowed, 02:20 quiet window.")

    print()
    print("[3] The escape hatch already in production (live from Oracle)")
    hr()
    n_eav = one(cur, "SELECT COUNT(*) FROM entity_attr_value WHERE entity_id IN "
                     "(SELECT cust_id FROM customer_master "
                     " WHERE conversion_batch_no = :b)", b=batch_no)
    n_attrs = one(cur, "SELECT COUNT(DISTINCT attr_name) FROM entity_attr_value "
                       "WHERE entity_id IN (SELECT cust_id FROM customer_master "
                       " WHERE conversion_batch_no = :b)", b=batch_no)
    print(f"  ENTITY_ATTR_VALUE          {n_eav:,} rows for ns '{args.ns}' "
          f"across {n_attrs} ad-hoc attribute names")
    print()
    print("  The ad-hoc 156th field nobody ever added a column for:")
    cur.execute(
        "SELECT attr_value, COUNT(*) FROM entity_attr_value"
        " WHERE attr_name = 'TAX_REGION_OVERRIDE'"
        "   AND entity_id IN (SELECT cust_id FROM customer_master"
        "                      WHERE conversion_batch_no = :b)"
        " GROUP BY attr_value ORDER BY attr_value", b=batch_no)
    rows = cur.fetchall()
    n_override = sum(count for _, count in rows)
    print(f"    TAX_REGION_OVERRIDE — {n_override:,} live rows, "
          "attr_type always 'STR', values:")
    for value, count in rows:
        print(f"      {value!r:<24} x {count:,}")
    print("  => same attribute, every value a different spelling: no type, "
          "no constraint,")
    print("     no validation — because a schemaless side-table cannot "
          "say \"no\".")

    conn.close()

    print()
    hr("=")
    print("PUNCHLINE")
    hr("=")
    print(f"  Adding column #{n_cols + 1} the right way touches "
          f"{len(TOUCH_POINTS)} artifacts, {n_triggers} triggers,")
    print("  a CAB ticket, and a spreadsheet. So nobody does it.")
    print(f"  The 156th field ALREADY SHIPPED — {n_override:,} rows of "
          "TAX_REGION_OVERRIDE in the")
    print("  EAV table: untyped, unconstrained, eight spellings of a boolean.")
    print("  No schema means no guarantee. The target fixes this with an "
          "enforced")
    print("  $jsonSchema: one optional field, one line, and bad data bounces "
          "at the door.")
    print(f"\n  ({time.monotonic() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
