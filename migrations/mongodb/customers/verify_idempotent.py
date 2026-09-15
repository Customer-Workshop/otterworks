"""Prove the customers load is idempotent: hash the target, load again, hash again.

    python migrations/mongodb/customers/verify_idempotent.py [out.json]

Exits non-zero if either collection changed. Reads Oracle read-only and writes only
ow_billing_migration.customers and ow_billing_migration.customer_history.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db  # noqa: E402
from customers.load_customers import COLLECTIONS, load  # noqa: E402


def fingerprint() -> dict[str, dict]:
    db = mongo_db()
    out = {}
    for name in COLLECTIONS:
        h = hashlib.sha256()
        n = 0
        for doc in db[name].find({}, sort=[("_id", 1)]):
            h.update(json_util.dumps(doc, sort_keys=True).encode())
            n += 1
        out[name] = {"count": n, "sha256": h.hexdigest()}
    return out


def main(argv: list[str]) -> int:
    before = fingerprint()
    load(drop=False)
    after = fingerprint()
    proof = {"before": before, "after": after, "unchanged": before == after}
    text = json.dumps(proof, indent=2)
    print(text)
    if len(argv) > 1:
        Path(argv[1]).write_text(text + "\n")
    if not proof["unchanged"]:
        print("NOT IDEMPOTENT: a re-run changed the target")
        return 1
    print("idempotent: a second load left both collections byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
