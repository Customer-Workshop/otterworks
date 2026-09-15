"""Prove the wave 0 load is idempotent: hash the target, load again, hash again.

    python migrations/mongodb/reference/verify_idempotent.py

Exits non-zero if any collection changed. Reads Oracle read-only and writes only the
four wave 0 collections in ow_billing_migration.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db  # noqa: E402
from load_reference import COLLECTIONS, load  # noqa: E402


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


def main() -> int:
    before = fingerprint()
    load(drop=False)
    after = fingerprint()
    print(json.dumps({"before": before, "after": after}, indent=2))
    if before != after:
        print("NOT IDEMPOTENT: a re-run changed the target")
        return 1
    print("idempotent: a second load left all four collections byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
