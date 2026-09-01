#!/usr/bin/env python3
"""Probe transaction-safe finalize branches against the target.

`sp_finalize_rating` re-finalizes an existing period through its update branch, so the
migrated `RatingService.finalize_rating` must survive being called twice for the same
tenant/period inside its MongoDB session transaction without leaving duplicate
`rating_periods`/`rating_results` documents.

The source period insert also collides on the natural `(tenant_id, period_start)` key.
When that imported period has a non-derived id, the source then violates the
`rating_results.period_id` foreign key; the probe verifies that the migrated service
aborts without writing a result or changing the imported period.

`subscriptions` belongs to unit U3 and is not loaded yet, so the covering-subscription read
is served from the same read-only Oracle extract that scripts/tp_mongo/parity_rating_u4.py
builds; that substitution is recorded in the emitted report.

The finalize writes land in the U4-owned collections; run the loader again (drop+recreate)
before the recon gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.parity_rating_u4 import _subscription_docs  # noqa: E402
from tp_mongo.rating_service import (  # noqa: E402
    RATING_PERIODS,
    RATING_RESULTS,
    RatingPeriodMissing,
    RatingService,
    StaticSubscriptionSource,
    md5_uuid,
)

TARGET_DB = "ow_tp_mongodb_032752"


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn-secret", default="OW_BILLING_FIXTURE_DSN",
        help="environment variable name containing user/password/dsn",
    )
    parser.add_argument(
        "--uri-secret", default="MONGODB_ATLAS_URI",
        help="environment variable name containing the Mongo URI",
    )
    parser.add_argument("--target-db", default=TARGET_DB)
    parser.add_argument(
        "--tenant-id", default="00000000-0000-0000-0000-000000000001",
        help="fixture tenant whose period is finalized twice",
    )
    parser.add_argument("--period-start", default="2026-02-01")
    parser.add_argument("--period-end", default="2026-02-28")
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U4/finalize_idempotency.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _payload(finalized: dict) -> dict:
    rating = finalized["rating"]
    return {
        "period_id": finalized["period_id"],
        "result_id": finalized["result_id"],
        "inserted_period": finalized["inserted_period"],
        "inserted_result": finalized["inserted_result"],
        "rating": {
            "used_units": rating.used_units,
            "quota_units": rating.quota_units,
            "rollover_units": rating.rollover_units,
            "billable_units": rating.billable_units,
            "first_tier_units": rating.first_tier_units,
            "second_tier_units": rating.second_tier_units,
            "overage_amount": (
                None if rating.overage_amount is None else f"{rating.overage_amount:f}"
            ),
        },
    }


def _rating_payload_equal(first: dict, second: dict) -> bool:
    return all(
        first[key] == second[key]
        for key in first
        if key not in {"inserted_period", "inserted_result"}
    )


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    dsn_value = _secret_value(args.dsn_secret, "Oracle DSN secret")
    uri_value = _secret_value(args.uri_secret, "Mongo URI secret")
    user, password, dsn = dsn_value.split("/", 2)

    import oracledb
    from pymongo import MongoClient

    oracle = oracledb.connect(user=user, password=password, dsn=dsn)
    client = MongoClient(uri_value)
    try:
        subscriptions = _subscription_docs(oracle)
        db = client[args.target_db]
        service = RatingService(
            db, subscription_source=StaticSubscriptionSource(subscriptions)
        )
        period_start = _day(args.period_start)
        period_end = _day(args.period_end)

        first = service.finalize_rating(args.tenant_id, period_start, period_end)
        second = service.finalize_rating(args.tenant_id, period_start, period_end)
        period_id = first["period_id"]
        result_id = first["result_id"]
        period_docs = db[RATING_PERIODS].count_documents({"_id": period_id})
        result_docs = db[RATING_RESULTS].count_documents({"period_id": period_id})
        first_payload = _payload(first)
        second_payload = _payload(second)
        repeat_checks = {
            "both_calls_succeeded": True,
            "second_call_took_update_path": (
                second["inserted_period"] is False
                and second["inserted_result"] is False
            ),
            "single_rating_period_doc": period_docs == 1,
            "single_rating_result_doc": result_docs == 1,
            "payloads_equal": _rating_payload_equal(first_payload, second_payload),
        }

        imported_start = "2025-12-01"
        imported_end = "2025-12-31"
        imported_period_start = _day(imported_start)
        imported_period_end = _day(imported_end)
        imported_period = db[RATING_PERIODS].find_one(
            {
                "tenant_id": args.tenant_id,
                "period_start": imported_period_start,
            }
        )
        if imported_period is None:
            raise RuntimeError("imported fixture rating period is missing")
        imported_source_id = imported_period["_id"]
        imported_period_end_before = imported_period["period_end"]
        imported_period_id = md5_uuid(args.tenant_id + imported_start)
        imported_result_id = md5_uuid(imported_period_id)
        imported_error = None
        try:
            service.finalize_rating(
                args.tenant_id, imported_period_start, imported_period_end
            )
        except RatingPeriodMissing as error:
            imported_error = str(error)
        imported_after = db[RATING_PERIODS].find_one(
            {"tenant_id": args.tenant_id, "period_start": imported_period_start}
        )
        imported_period_docs = db[RATING_PERIODS].count_documents(
            {"tenant_id": args.tenant_id, "period_start": imported_period_start}
        )
        imported_result_docs = db[RATING_RESULTS].count_documents(
            {"_id": imported_result_id}
        )
        imported_checks = {
            "fk_violation_raised": imported_error is not None,
            "single_imported_period": imported_period_docs == 1,
            "original_period_id_preserved": (
                imported_after is not None
                and imported_after["_id"] == imported_source_id
            ),
            "imported_period_unchanged": (
                imported_after is not None
                and imported_after["period_end"] == imported_period_end_before
            ),
            "no_derived_result_written": imported_result_docs == 0,
        }
        checks = {
            "derived_repeat": repeat_checks,
            "imported_period_fk_violation": imported_checks,
        }
        ok = all(repeat_checks.values()) and all(imported_checks.values())
        report = {
            "unit": "U4",
            "probe": "finalize_rating idempotency and imported-period FK parity",
            "run_mode": "fixture",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_db": args.target_db,
            "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
            "subscription_source": (
                "read-only Oracle extract (SUBSCRIPTIONS belongs to unit U3 and is not "
                "loaded; the Mongo-backed subscription read path is declared-unexercised)"
            ),
            "imported_period_path_note": (
                "The imported-period case mirrors the source fk_rr_period violation: "
                "the natural-key collision updates the imported period, but the derived "
                "result period_id is absent, so the transaction aborts."
            ),
            "derived_repeat_case": {
                "inputs": {
                    "tenant_id": args.tenant_id,
                    "period_start": args.period_start,
                    "period_end": args.period_end,
                },
                "period_id": period_id,
                "result_id": result_id,
                "rating_periods_docs_for_period": period_docs,
                "rating_results_docs_for_period": result_docs,
                "first_call": first_payload,
                "second_call": second_payload,
                "checks": repeat_checks,
            },
            "imported_period_case": {
                "inputs": {
                    "tenant_id": args.tenant_id,
                    "period_start": imported_start,
                    "period_end": imported_end,
                },
                "original_period_id": imported_source_id,
                "derived_period_id": imported_period_id,
                "derived_result_id": imported_result_id,
                "rating_periods_docs_for_natural_key": imported_period_docs,
                "derived_result_docs": imported_result_docs,
                "error": imported_error,
                "checks": imported_checks,
            },
            "checks": checks,
            "verdict": "PASS" if ok else "FAIL",
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        for name, passed in repeat_checks.items():
            print(f"derived_repeat.{name} | {'PASS' if passed else 'FAIL'}")
        for name, passed in imported_checks.items():
            print(f"imported_period_fk_violation.{name} | {'PASS' if passed else 'FAIL'}")
        print(f"U4 finalize idempotency | {report['verdict']} | {report_path}")
        return 0 if ok else 1
    finally:
        client.close()
        oracle.close()


if __name__ == "__main__":
    raise SystemExit(main())
