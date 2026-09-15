"""Dry-run the Tier 4 recorded operations for U3-invoices on both stacks.

Same comparison the harness makes (set of rows, keys and values), so an op can be
corrected without spending one of the three full recon re-runs.

    python migrations/mongodb/invoices/check_ops.py [op-name ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db, oracle_connect  # noqa: E402
from recon.canon import Canonicalizer  # noqa: E402
from recon.config import load_canon_rules  # noqa: E402

OPS = Path(".migration/ops/U3-invoices.json")
RULES = Path(".migration/recon/U3-invoices/inputs/canonicalization.json")


def _rows(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _match(source_rows, target_rows, canon, rules):
    """The same set match Tier 4 makes: every row on one side pairs with one on the other."""
    free = [True] * len(target_rows)
    unmatched_source = []
    for s in source_rows:
        hit = None
        for i, t in enumerate(target_rows):
            if free[i] and s.keys() == t.keys() and all(
                    canon.equal(s[k], t[k], rules)[0] for k in s):
                hit = i
                break
        if hit is None:
            unmatched_source.append(s)
        else:
            free[hit] = False
    return unmatched_source, [t for t, f in zip(target_rows, free) if f]


def main(names: list[str]) -> int:
    ops = [o for o in json.loads(OPS.read_text())
           if not names or o["name"] in names]
    canon = Canonicalizer(load_canon_rules(RULES))
    db = mongo_db()
    conn = oracle_connect()
    bad = 0
    try:
        cur = conn.cursor()
        for op in ops:
            s = _rows(cur, op["source_sql"])
            t = list(db[op["collection"]].aggregate(op["target_pipeline"]))
            ls, lt = _match(s, t, canon, list(op.get("rules", [])))
            ok = not ls and not lt
            bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} {op['name']}: {len(s)} source rows, "
                  f"{len(t)} target rows")
            if not ok:
                print("   source only:", json.dumps(ls[:5], default=str))
                print("   target only:", json.dumps(lt[:5], default=str))
    finally:
        conn.close()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
