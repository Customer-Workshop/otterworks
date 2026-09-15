"""Prove the invoices load is idempotent: hash the target, load again, hash again.

    python migrations/mongodb/invoices/verify_idempotent.py [out.json]

Exits non-zero if either collection changed. Reads Oracle read-only and writes only
invoices and invoice_lines_orphaned in ow_billing_migration.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db  # noqa: E402
from invoices.load_invoices import INVOICES, ORPHANS, load  # noqa: E402

COLLECTIONS = (INVOICES, ORPHANS)


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


def main(out_path: str | None) -> int:
    before = fingerprint()
    load(drop=False)
    after = fingerprint()
    unchanged = before == after
    record = {"check": "idempotency_rerun", "method": "sha256 of every document, "
              "re-run of the same load without --drop, re-hash",
              "before": before, "after": after, "unchanged": unchanged}
    print(json.dumps(record, indent=2))
    if out_path:
        Path(out_path).write_text(json.dumps(record, indent=2) + "\n")
    if not unchanged:
        print("NOT IDEMPOTENT: a re-run changed the target")
        return 1
    print("idempotent: a second load left both collections byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
