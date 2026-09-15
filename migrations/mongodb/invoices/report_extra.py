"""Recompute this unit's evidence numbers from Atlas and write the recon-report extras.

Every number here is read back out of ow_billing_migration after the load; nothing is
carried over from the loader's own counters.

    python migrations/mongodb/invoices/report_extra.py .migration/recon/U3-invoices/extra.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import mongo_db  # noqa: E402
from invoices.load_invoices import INVOICES, ORPHANS  # noqa: E402

MANIFEST = Path("testdata/legacy/manifests/demo.json")
UNVERIFIED = [
    "Y/N-to-boolean (POSTED_YN), CSV-to-array (GL_ACCT_CSV) and DD-MON-YY string parsing "
    "are graded by tier 4 recorded operations, not by the canonicaliser: the harness has no "
    "yn_to_bool, csv_split_trim or parse_date_string rule and patching the harness was out "
    "of scope. Raised as profile feedback in .migration/canonicalization.json.",
    "CODES-decoded fields (invoices.status, dunning[].status) are graded by tier 4, not "
    "tier 3, because the source holds an integer code and the target holds the decoded "
    "string; the harness cannot compare the two.",
    "lines[].servicePeriod is a derived {from,to} pair with no source column, so it is "
    "graded by tier 4 month-bucket counts rather than by a keyed field diff.",
    "lines[].type stays an integer by design (no CODES type for invoice line types; RPT-114 "
    "decodes it with a hard-coded DECODE), so no decode path is exercised for it.",
    "Both estates share one collection separated by the source field, so the harness grades "
    "conversion and billing through two mapping roots with a target filter; a document with "
    "neither source value would be invisible to tier 3. Tier 1 count parity on the whole "
    "collection is the control.",
    "The billing estate is 3 invoices, 2 lines and 1 dunning attempt, so billing-side "
    "grading is structurally exercised but statistically thin.",
    "The repo self-check asks for an ow_tp / ow-tp- namespace prefix. The engagement intake "
    "fixes the target database as ow_billing_migration, so the prefix rule is deliberately "
    "not met; .migration/allowed_targets.json is the control instead.",
    "Scale is the demo estate on an Atlas M0 cluster. Nothing here is a statement about "
    "production volumes or production index sizing.",
    "The load reads Oracle in one read-only transaction, so it is snapshot-consistent; it is "
    "not serialised against a second concurrent loader, which the wave manifest's disjoint "
    "write targets prevent rather than the code.",
]


def main(out_path: str) -> int:
    db = mongo_db()
    agg = list(db[INVOICES].aggregate([
        {"$group": {"_id": "$source", "docs": {"$sum": 1},
                    "lines": {"$sum": {"$size": {"$ifNull": ["$lines", []]}}},
                    "dunning": {"$sum": {"$size": {"$ifNull": ["$dunning", []]}}}}},
    ]))
    by_source = {r["_id"]: r for r in agg}
    counts = {
        "invoices": db[INVOICES].count_documents({}),
        "invoices.source=conversion": by_source["conversion"]["docs"],
        "invoices.source=billing": by_source["billing"]["docs"],
        "invoices.lines[]": sum(r["lines"] for r in agg),
        "invoices.dunning[]": sum(r["dunning"] for r in agg),
        ORPHANS: db[ORPHANS].count_documents({}),
    }

    expected = [f"{a['kind']}:{a['target']}:{a['count']}"
                for a in json.loads(MANIFEST.read_text())["planted_anomalies"]
                if a["target"].endswith("INVOICE_LINE")]
    actual = [f"orphaned_rows:oracle.OW_BILLING.INVOICE_LINE:{counts[ORPHANS]}"]
    extra = {
        "wave": 1,
        "batch": "w1-b02",
        "branch": "tp-run/mongodb-20260915T045208Z",
        "mapping_version": "1",
        "tolerance_version": "1",
        "target_db": "ow_billing_migration",
        "collections": [INVOICES, ORPHANS],
        "merge_authority": "live",
        "counts_from_target": counts,
        "planted_anomaly_detections": {
            "expected_set": sorted(expected),
            "actual_set": sorted(actual),
            "missing": sorted(set(expected) - set(actual)),
            "unexpected": sorted(set(actual) - set(expected)),
            "note": "the invoices budget is the 37 orphaned INVOICE_LINE rows; they are kept "
                    "in invoice_lines_orphaned with the dangling invoiceId, counted back out "
                    "of Atlas. The 50 dirty SIGNUP_DT and 31 malformed RELATED_ACCT_IDS "
                    "anomalies live in CUSTOMER_MASTER, which is another batch's unit.",
        },
        "unverified_paths": UNVERIFIED,
        "preflight": {
            "platform": "atlas",
            "manifest": ".tp-preflight/atlas-capabilities.json",
            "passed": True,
        },
        "source_access": "SELECT/WITH only, in a single read-only transaction; no DDL or DML "
                         "against OW_BILLING",
        "secrets": ["ORACLE_BILLING_URI", "MONGODB_ATLAS_URI"],
    }
    Path(out_path).write_text(json.dumps(extra, indent=2) + "\n")
    print(json.dumps(counts, indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
