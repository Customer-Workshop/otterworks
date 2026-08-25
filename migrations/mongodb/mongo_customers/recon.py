#!/usr/bin/env python3
"""Reconcile the migrated `customers` collection against the estate baseline.

    make mongo-customers-recon NS=demo

Every number in the report is recomputed here — counts and the line-format md5
are read back out of the document store, and the anomaly membership is
recomputed from both sides. Nothing is copied out of the baseline manifest
except the expected values a check is compared *against*.

Anomalies are compared as SETS of customer ids, not as counts: a recon that
matched only totals would stay green while quarantining the wrong 50 rows.
The report lists both `missing` (planted but not detected) and `unexpected`
(detected but not planted), and any non-empty side fails the run.

The report is written to docs/tech-partnerships/recon/mongo_customers.recon.json
and is gated by `make tp-validate-recon`.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import oracledb
from pymongo import MongoClient
from pymongo.errors import WriteError

from migrate import (discover_batch_no, namespace, oracle_connect)
from schema import (CUSTOMERS_COLLECTION, EAV_TABLE, QUARANTINE_COLLECTION,
                    SOURCE_TABLE, database_name, quarantine_database_name)
from transform import (document_id, parse_csv_list, parse_legacy_date)

UNIT = "mongo_customers"
DOCUMENT_VALIDATION_FAILURE = 121
MANIFEST_CUSTOMERS = f"oracle.{SOURCE_TABLE}"
MANIFEST_EAV = f"oracle.{EAV_TABLE}"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "testdata", "legacy", "manifests")
DEFAULT_REPORT = os.path.join(REPO_ROOT, "docs", "tech-partnerships", "recon",
                              f"{UNIT}.recon.json")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", required=True, type=namespace)
    ap.add_argument("--mongo-uri", default=os.environ.get("TP_MONGODB_URI")
                    or os.environ.get("MONGODB_URI"))
    ap.add_argument("--oracle-host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--oracle-port", type=int,
                    default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--oracle-service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    ap.add_argument("--oracle-user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--oracle-password",
                    default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--run-mode", choices=["fixture", "live"], default="fixture")
    ap.add_argument("--run-summary", action="append", default=[],
                    help="migration run summary JSON; pass twice to prove idempotency")
    ap.add_argument("--manifest-dir", default=DEFAULT_MANIFEST)
    ap.add_argument("--out", default=DEFAULT_REPORT)
    args = ap.parse_args(argv)
    if not args.mongo_uri:
        ap.error("set TP_MONGODB_URI (or MONGODB_URI), or pass --mongo-uri")
    return args


def generated_at() -> str:
    """Frozen clock when the deterministic wrapper pins one, else wall clock."""
    faketime = os.environ.get("TP_FAKETIME")
    if faketime:
        return (datetime.strptime(faketime, "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"))
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(checks, cid, expected, actual, source_of_truth):
    checks.append({"id": cid, "expected": expected, "actual": actual,
                   "source_of_truth": source_of_truth,
                   "result": "pass" if expected == actual else "fail"})


def target_checksum(customers, ns: str):
    """The baseline's line-format md5, recomputed from the document store.

    The estate's manifest digests `<pk>:<amount>\\n` lines in primary-key
    order; the same digest over the target collection is what proves the
    migration moved the balances, not just the row count.
    """
    digest = hashlib.md5()
    cursor = customers.find({"namespace": ns},
                            {"customer_id": 1, "balances.current_amount": 1}
                            ).sort("customer_id", 1)
    rows = 0
    for doc in cursor:
        amount = doc.get("balances", {}).get("current_amount")
        if amount is None:
            raise SystemExit(f"customer {doc.get('customer_id')} has no current "
                             "balance in the target; checksum cannot be recomputed")
        digest.update(f"{doc['customer_id']}:{amount.to_decimal():.2f}\n".encode())
        rows += 1
    return digest.hexdigest(), rows


def source_anomaly_set(cur, batch_no):
    """Recompute planted anomaly membership from the estate itself."""
    cur.execute("""SELECT cust_id, signup_dt, related_acct_ids FROM customer_master
                    WHERE conversion_batch_no = :b ORDER BY cust_id""", b=batch_no)
    expected = set()
    for cust_id, signup_dt, related in cur:
        if signup_dt is not None and parse_legacy_date(signup_dt)[1]:
            expected.add(f"dirty_dates:{cust_id}")
        if related is not None and parse_csv_list(related)[1]:
            expected.add(f"malformed_csv_lists:{cust_id}")
    return expected


def target_anomaly_set(quarantine, ns):
    reason_to_anomaly = {"dirty_date": "dirty_dates",
                         "malformed_csv_list": "malformed_csv_lists"}
    actual = set()
    for doc in quarantine.find(
            {"namespace": ns, "reason": {"$in": list(reason_to_anomaly)}},
            {"customer_id": 1, "reason": 1}):
        actual.add(f"{reason_to_anomaly[doc['reason']]}:{doc['customer_id']}")
    return actual


def probe_validator(customers, ns):
    """Prove the validator rejects both legacy shapes, with error 121."""
    conforming = {
        "_id": document_id(ns, "__recon_probe__"),
        "customer_id": "__recon_probe__",
        "namespace": ns,
        "signup_dt": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "source": {"table": SOURCE_TABLE, "batch_no": 0},
    }
    results = {}
    customers.delete_one({"_id": conforming["_id"]})
    try:
        customers.insert_one(dict(conforming))
        results["conforming_insert"] = "accepted"
    except WriteError as exc:
        results["conforming_insert"] = f"rejected: {exc.code}"
    finally:
        customers.delete_one({"_id": conforming["_id"]})

    for case, mutate in (
            ("string_signup_dt", lambda d: d.update({"signup_dt": "31-FEB-24"})),
            ("unknown_top_level_field",
             lambda d: d.update({"tax_region_override": "see ticket 48213"}))):
        doc = dict(conforming)
        mutate(doc)
        try:
            customers.insert_one(doc)
            results[case] = "accepted"
            customers.delete_one({"_id": doc["_id"]})
        except WriteError as exc:
            results[case] = f"rejected: server error {exc.code}"
    return results


def null_legacy_fields(customers, ns):
    """Sparse columns must be omitted, never written as null."""
    pipeline = [
        {"$match": {"namespace": ns}},
        {"$project": {"nulls": {"$size": {"$filter": {
            "input": {"$objectToArray": {"$ifNull": ["$legacy", {}]}},
            "cond": {"$eq": ["$$this.v", None]}}}}}},
        {"$match": {"nulls": {"$gt": 0}}},
        {"$count": "documents"},
    ]
    result = list(customers.aggregate(pipeline))
    return result[0]["documents"] if result else 0


def bad_array_fields(customers, ns):
    """No list column may be null or a one-element list holding an empty string."""
    return customers.count_documents({"namespace": ns, "$or": [
        {"related_acct_ids": {"$type": "null"}}, {"promo_codes": {"$type": "null"}},
        {"related_acct_ids": [""]}, {"promo_codes": [""]},
    ]})


def folded_attribute_values(customers, ns):
    pipeline = [
        {"$match": {"namespace": ns, "attributes": {"$exists": True}}},
        {"$project": {"n": {"$sum": {"$map": {
            "input": {"$objectToArray": "$attributes"},
            "in": {"$size": "$$this.v"}}}}}},
        {"$group": {"_id": None, "total": {"$sum": "$n"}}},
    ]
    result = list(customers.aggregate(pipeline))
    return result[0]["total"] if result else 0


def main(argv=None) -> int:
    args = parse_args(argv)
    ns = args.ns
    with open(os.path.join(args.manifest_dir, f"{ns}.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    baseline = manifest["targets"][MANIFEST_CUSTOMERS]
    eav_baseline = manifest["targets"][MANIFEST_EAV]
    planted = {a["kind"]: a["count"] for a in manifest["planted_anomalies"]}

    conn = oracle_connect(args)
    cur = conn.cursor()
    batch_no = discover_batch_no(cur, ns)
    if batch_no is None:
        raise SystemExit(f"no {SOURCE_TABLE} rows for namespace {ns}: nothing to recon")

    client = MongoClient(args.mongo_uri, uuidRepresentation="standard")
    customers = client[database_name(ns)][CUSTOMERS_COLLECTION]
    quarantine = client[quarantine_database_name(ns)][QUARANTINE_COLLECTION]

    checks = []
    documents = customers.count_documents({"namespace": ns})
    check(checks, "doc-count", baseline["rows"], documents,
          f"{MANIFEST_CUSTOMERS}.rows vs count on {CUSTOMERS_COLLECTION}")
    check(checks, "doc-count-distinct-ids", baseline["rows"],
          len(customers.distinct("customer_id", {"namespace": ns})),
          "distinct customer_id in the target (proves no duplicate documents)")
    check(checks, "doc-id-derivation", "uuid5", "uuid5" if all(
        doc["_id"] == document_id(ns, doc["customer_id"])
        for doc in customers.find({"namespace": ns},
                                  {"customer_id": 1}).limit(1000)) else "mismatch",
          "sampled _id recomputed as uuid5(namespace, customer_id)")

    folded = folded_attribute_values(customers, ns)
    eav_quarantined = quarantine.count_documents(
        {"namespace": ns, "source.table": EAV_TABLE})
    check(checks, "eav-fold", eav_baseline["rows"], folded + eav_quarantined,
          f"{MANIFEST_EAV}.rows vs folded attribute values + attributed rows")
    check(checks, "eav-attr-names-verbatim", True,
          customers.count_documents({"namespace": ns,
                                     "attributes.TAX_REGION_OVERRIDE":
                                         {"$exists": True}}) > 0,
          "attributes.TAX_REGION_OVERRIDE read back verbatim from the target")

    check(checks, "csv-to-array-types", 0, bad_array_fields(customers, ns),
          "documents whose list columns are null or [\"\"] in the target")
    check(checks, "csv-to-array-empty-list",
          True, customers.count_documents({"namespace": ns,
                                           "related_acct_ids": []}) > 0,
          "well-formed empty lists present as empty arrays in the target")

    dated = customers.count_documents({"namespace": ns,
                                       "signup_dt": {"$type": "date"}})
    dirty = quarantine.count_documents({"namespace": ns, "reason": "dirty_date"})
    check(checks, "date-conversion", baseline["rows"] - planted["dirty_dates"], dated,
          "documents carrying a BSON date signup_dt")
    check(checks, "date-conversion-not-coerced", 0,
          customers.count_documents({"namespace": ns,
                                     "signup_dt": {"$type": "string"}}),
          "documents whose signup_dt stayed a string (must be zero)")
    check(checks, "date-conversion-quarantined", planted["dirty_dates"], dirty,
          f"{MANIFEST_CUSTOMERS}.SIGNUP_DT anomaly count vs dirty_date quarantine")
    quarantined_ids = [d["customer_id"] for d in quarantine.find(
        {"namespace": ns, "reason": "dirty_date"}, {"customer_id": 1})]
    check(checks, "date-conversion-not-defaulted", 0,
          customers.count_documents({"namespace": ns,
                                     "customer_id": {"$in": quarantined_ids},
                                     "signup_dt": {"$exists": True}}),
          "quarantined customers must carry no signup_dt at all")

    check(checks, "sparse-columns", 0, null_legacy_fields(customers, ns),
          "documents with an explicit null in the legacy subdocument")

    validator_probe = probe_validator(customers, ns)
    check(checks, "validator", {
        "conforming_insert": "accepted",
        "string_signup_dt": f"rejected: server error {DOCUMENT_VALIDATION_FAILURE}",
        "unknown_top_level_field":
            f"rejected: server error {DOCUMENT_VALIDATION_FAILURE}",
    }, validator_probe, "live insert probes against the target collection")

    checksum, checksum_rows = target_checksum(customers, ns)
    check(checks, "checksum", baseline["checksum"], checksum,
          f"{MANIFEST_CUSTOMERS}.checksum vs md5 recomputed from "
          f"{CUSTOMERS_COLLECTION}")
    check(checks, "checksum-coverage", baseline["rows"], checksum_rows,
          "rows fed into the recomputed checksum")

    expected_set = source_anomaly_set(cur, batch_no)
    actual_set = target_anomaly_set(quarantine, ns)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    check(checks, "planted-anomaly-set-size",
          planted["dirty_dates"] + planted["malformed_csv_lists"],
          len(expected_set),
          "manifest planted counts vs anomaly membership recomputed from the estate")
    check(checks, "planted-anomaly-set-match", {"missing": [], "unexpected": []},
          {"missing": missing, "unexpected": unexpected},
          "estate anomaly membership vs quarantine membership, compared as sets")

    summaries = []
    for path in args.run_summary:
        with open(path, encoding="utf-8") as fh:
            summaries.append(json.load(fh))
    idempotency = {"performed": False, "result": "fail"}
    if len(summaries) >= 2:
        first, second = summaries[-2], summaries[-1]
        comparable = ["customers", "attributes", "documents_in_target",
                      "quarantine_in_target", "batch_no"]
        identical = all(first.get(k) == second.get(k) for k in comparable)
        idempotency = {
            "performed": True,
            "result": "pass" if identical and second.get(
                "stale_documents_removed", 0) == 0 else "fail",
            "evidence": ("two consecutive migration runs reported identical "
                         f"counts: documents_in_target="
                         f"{second.get('documents_in_target')}, "
                         f"quarantine_in_target="
                         f"{second.get('quarantine_in_target')}, "
                         f"stale_documents_removed="
                         f"{second.get('stale_documents_removed')}"),
        }
        check(checks, "idempotency", {"identical_run_counts": True},
              {"identical_run_counts": identical},
              "two observed migration runs over the same source set")

    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": generated_at(),
        "run_mode": args.run_mode,
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": idempotency,
        "planted_anomaly_detections": {
            "expected_set": sorted(expected_set),
            "actual_set": sorted(actual_set),
            "missing": missing,
            "unexpected": unexpected,
        },
        "unverified_paths": [
            "Atlas M0 cluster ow_tp_mongodb_demo: this report is run_mode=fixture "
            "against a local mongo:7 document store; live recon is recomputed "
            "separately against the cluster.",
            "invalid_encoding quarantine path: the estate's AL32UTF8 columns hold "
            "no undecodable bytes at this batch, so the path is covered only by "
            "the unit tests in tests/test_transform.py, not by live data.",
            "missing_required_field quarantine path: CUST_ID is NOT NULL in the "
            "source, so the fail-closed branch is exercised by unit tests only.",
            "empty-source no-op path: exercised against a namespace with no rows "
            "in the estate (the run exits zero before opening the target), not "
            "against a batch that was emptied after a prior successful load.",
            "null_attribute_value quarantine path: every ENTITY_ATTR_VALUE row in "
            "this batch has a value, so it is covered by unit tests only.",
        ],
    }

    failed = [c["id"] for c in checks if c["result"] != "pass"]
    if idempotency["performed"] and idempotency["result"] != "pass":
        failed.append("idempotency_rerun")
    if not args.run_summary:
        report["unverified_paths"].append(
            "idempotency: no run summaries were supplied to this invocation.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"report": args.out, "checks": len(checks),
                      "failed": failed}, indent=2))
    client.close()
    conn.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
