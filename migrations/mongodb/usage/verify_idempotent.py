"""Prove the U4-usage load is idempotent: hash the target, load again, hash again.

    python migrations/mongodb/usage/verify_idempotent.py [--out <file>]

Exits non-zero if either collection changed. Reads Oracle read-only and writes only
usage_events and rating_periods in ow_billing_migration.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_usage import COLLECTIONS, load  # noqa: E402


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
    ap.add_argument("--out", help="write the before/after fingerprints to this file")
    args = ap.parse_args()

    before = fingerprint()
    load(drop=False)
    after = fingerprint()
    evidence = {"before": before, "after": after, "identical": before == after}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not evidence["identical"]:
        print("NOT IDEMPOTENT: a re-run changed the target")
        return 1
    print("idempotent: a second load left both collections byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
