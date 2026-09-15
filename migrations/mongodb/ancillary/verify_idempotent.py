"""Prove the U5-ancillary load is idempotent: hash the target, load again, hash again.

    python migrations/mongodb/ancillary/verify_idempotent.py [--out <json file>]

Exits non-zero if any collection changed. Reads Oracle read-only and writes only the
three U5-ancillary collections in ow_billing_migration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db  # noqa: E402
from load_ancillary import COLLECTIONS, load  # noqa: E402


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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="write the before/after fingerprints here")
    args = ap.parse_args()
    before = fingerprint()
    load(drop=False)
    after = fingerprint()
    evidence = {"unit": "U5-ancillary", "before": before, "after": after,
                "identical": before == after}
    print(json.dumps(evidence, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(evidence, indent=2) + "\n")
    if not evidence["identical"]:
        print("NOT IDEMPOTENT: a re-run changed the target")
        return 1
    print("idempotent: a second load left all three collections byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
