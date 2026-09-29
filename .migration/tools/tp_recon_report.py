"""Emit a TP recon report JSON for one unit+mode.

Combines the harness result.json with the unit's first-run and rerun load
records, recomputes the target-side numbers from the target itself, and writes
docs/tech-partnerships/recon/<unit>.<mode>.recon.json (schema:
docs/tech-partnerships/contracts/schema/recon-report.schema.json).
Counts and hashes only; no row values.
"""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DB = "ow_tp_mmp_live"
SOURCE_OF_TRUTH = "oracle OW_BILLING"

_MODE_ENVS = {
    "fixture": "OW_TP_MMP_FIXTURE_URI",
    "live": "OW_TP_MMP_TARGET_URI",
}


def _target_counts(db, collections):
    return {name: db[name].count_documents({}) for name in collections}



def _orphan_hashes(db):
    return sorted(
        hashlib.sha256(str(d["_id"]).encode()).hexdigest()[:16]
        for d in db["quarantine_invoice_line"].find({}, {"_id": 1})
    )


def _dup_attr_hashes(db):
    groups = Counter()
    for doc in db["customers"].find(
        {}, {"_id": 1, "attributes.attr_name": 1}
    ):
        for el in doc.get("attributes", []):
            groups[(str(doc["_id"]), el.get("attr_name"))] += 1
    return sorted(
        hashlib.sha256(f"{cust}|{name}".encode()).hexdigest()[:16]
        for (cust, name), n in groups.items()
        if n > 1
    )


def main():
    parser = argparse.ArgumentParser(prog="tp_recon_report")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--mode", required=True, choices=sorted(_MODE_ENVS))
    parser.add_argument("--result", help="harness result.json (omit when the harness refused to run)")
    parser.add_argument("--load-first", required=True, help="first-run load-<mode> record")
    parser.add_argument("--load-rerun", required=True, help="rerun load-<mode> record")
    parser.add_argument("--namespace", default=TARGET_DB)
    args = parser.parse_args()

    result = json.loads(Path(args.result).read_text()) if args.result else None
    first = json.loads(Path(args.load_first).read_text())
    rerun = json.loads(Path(args.load_rerun).read_text())

    uri_env = _MODE_ENVS[args.mode]
    db = MongoClient(os.environ[uri_env])[args.namespace]

    collections = (
        result["collections"] if result else sorted(first.get("doc_counts", {}))
    )
    source_counts = first.get("source_counts", {})
    target_counts = _target_counts(db, collections)
    coll_by_root = {c["root_table"].lower(): c["collection"] for c in
                    json.loads((REPO_ROOT / ".migration" / "03_mapping_spec.json").read_text())["collections"]}

    spec_by_coll = {
        c["collection"]: c
        for c in json.loads(
            (REPO_ROOT / ".migration" / "03_mapping_spec.json").read_text()
        )["collections"]
    }

    def _check(check_id, expected, actual, passed):
        return {
            "id": check_id,
            "expected": expected,
            "actual": actual,
            "source_of_truth": SOURCE_OF_TRUTH,
            "result": "pass" if passed else "fail",
        }

    checks = []
    unverified_paths = []
    if result:
        tier1 = next((t for t in result["tiers"] if t["tier"] == 1), None)
        tier2 = next((t for t in result["tiers"] if t["tier"] == 2), None)
        tier3 = next((t for t in result["tiers"] if t["tier"] == 3), None)
        t3_stats = (tier3 or {}).get("stats", {})
        embeds_graded = t3_stats.get("embeds_graded", {})
        embed_extras_unchecked = t3_stats.get("embed_extras_unchecked", [])
        tier2_findings = (tier2 or {}).get("findings") or []
        tier3_findings = (tier3 or {}).get("findings") or []
        string_aggs = {
            s["field"]: len(s.get("stats", [1]))
            for s in (tier2 or {}).get("stats", {}).get(
                "string_aggregates_deferred_to_tier3", []
            )
        }
        deferred_fields = (tier2 or {}).get("stats", {}).get(
            "deferred_to_tier3", []
        )
        for coll in collections:
            root = next((r for r, c in coll_by_root.items() if c == coll), coll)
            expected_count = (
                (tier1 or {}).get("stats", {}).get("source_counts", {}).get(coll)
            )
            if expected_count is None:
                expected_count = source_counts.get(root)
            actual_count = target_counts[coll]
            checks.append(
                _check(
                    f"tier1.counts_through_mapping.{coll}",
                    expected_count,
                    actual_count,
                    expected_count == actual_count,
                )
            )
            for embed in spec_by_coll.get(coll, {}).get("embeds", []):
                path = f"{coll}.{embed['array_path']}"
                child_src = source_counts.get(embed["child_table"].lower())
                if child_src is not None:
                    child_src -= sum(
                        source_counts.get(oc["root_table"].lower(), 0)
                        for name, oc in spec_by_coll.items()
                        if name != coll
                        and oc.get("root_table", "").lower()
                        == embed["child_table"].lower()
                    )
                actual_embeds = embeds_graded.get(path)
                if actual_embeds is None or child_src is None:
                    checks.append(
                        {
                            "id": f"tier1.embedded_count.{path}",
                            "expected": child_src,
                            "actual": actual_embeds,
                            "source_of_truth": SOURCE_OF_TRUTH,
                            "result": "skipped",
                        }
                    )
                    unverified_paths.append(f"{path}: embed UNGRADED by harness")
                else:
                    checks.append(
                        _check(
                            f"tier1.embedded_count.{path}",
                            child_src,
                            actual_embeds,
                            child_src == actual_embeds,
                        )
                    )
            compared = sum(
                string_aggs.get(f, 1)
                for f in deferred_fields
                if f.split(".", 1)[0] == coll
            )
            coll_t2_findings = sum(
                1 for f in tier2_findings if f.get("collection") == coll
            )
            checks.append(
                _check(
                    f"tier2.per_field_aggregates.{coll}",
                    compared,
                    compared - coll_t2_findings,
                    coll_t2_findings == 0,
                )
            )
            coll_t3_findings = sum(
                1 for f in tier3_findings if f.get("collection") == coll
            )
            checks.append(
                _check(
                    f"tier3.keyed_diffs.{coll}",
                    0,
                    coll_t3_findings,
                    coll_t3_findings == 0,
                )
            )
        for path in embed_extras_unchecked:
            unverified_paths.append(
                f"{path}: extra-element check skipped (scoped embed, D-012)"
            )
    else:
        for coll in collections:
            root = (
                "invoice_line_orphans"
                if coll == "quarantine_invoice_line"
                else next((r for r, c in coll_by_root.items() if c == coll), coll)
            )
            checks.append(
                {
                    "id": f"counts.{coll}",
                    "expected": source_counts.get(root),
                    "actual": target_counts[coll],
                    "source_of_truth": SOURCE_OF_TRUTH,
                    "result": "skipped",
                }
            )

    if args.unit == "U2-invoices":
        expected_set = first.get("expected_orphan_hashes", [])
        actual_set = _orphan_hashes(db)
    elif args.unit == "U1-customers":
        expected_set = first.get("expected_dup_attr_hashes", [])
        actual_set = _dup_attr_hashes(db)
    else:
        expected_set = []
        actual_set = []

    rerun_bulk = rerun.get("bulk", {})
    idempotent = all(
        c.get("upserted", 0) == 0 and c.get("deleted", 0) == 0 for c in rerun_bulk.values()
    ) and (result["verdict"] == "PASS" if result else True)

    report = {
        "kind": "recon-report",
        "unit": args.unit,
        "namespace": args.namespace,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z"),
        "run_mode": args.mode,
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": f"rerun bulk {json.dumps(rerun_bulk, sort_keys=True)}; recon verdict {result['verdict'] if result else 'refused (spec child_where/target_where asymmetry)'}",
        },
        "planted_anomaly_detections": {
            "expected_set": expected_set,
            "actual_set": actual_set,
            "missing": sorted(set(expected_set) - set(actual_set)),
            "unexpected": sorted(set(actual_set) - set(expected_set)),
        },
        "unverified_paths": (
            unverified_paths
            + (["live recon not yet run"] if args.mode == "fixture" else [])
            + (
                []
                if result
                else [
                    "recon harness refused: spec child_where/root_where has no target_where"
                ]
            )
        ),
    }

    out = (
        REPO_ROOT
        / "docs"
        / "tech-partnerships"
        / "recon"
        / f"{args.unit}.{args.mode}.recon.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": str(out), "checks": len(checks)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
