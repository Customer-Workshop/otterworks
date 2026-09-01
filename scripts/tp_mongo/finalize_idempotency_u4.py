#!/usr/bin/env python3
"""Probe that a repeated sp_finalize_rating replay stays idempotent on the target.

`sp_finalize_rating` re-finalizes an existing period through its update branch, so the
migrated `RatingService.finalize_rating` must survive being called twice for the same
tenant/period inside its MongoDB session transaction without leaving duplicate
`rating_periods`/`rating_results` documents.

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
    RatingService,
    StaticSubscriptionSource,
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
        comparable_first = {
            key: value
            for key, value in first_payload.items()
            if key not in {"inserted_period", "inserted_result"}
        }
        comparable_second = {
            key: value
            for key, value in second_payload.items()
            if key not in {"inserted_period", "inserted_result"}
        }
        checks = {
            "both_calls_succeeded": True,
            "second_call_took_update_path": (
                second["inserted_period"] is False
                and second["inserted_result"] is False
            ),
            "single_rating_period_doc": period_docs == 1,
            "single_rating_result_doc": result_docs == 1,
            "payloads_equal": comparable_first == comparable_second,
        }
        ok = all(checks.values())
        report = {
            "unit": "U4",
            "probe": "finalize_rating idempotency",
            "run_mode": "fixture",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_db": args.target_db,
            "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
            "inputs": {
                "tenant_id": args.tenant_id,
                "period_start": args.period_start,
                "period_end": args.period_end,
            },
            "subscription_source": (
                "read-only Oracle extract (SUBSCRIPTIONS belongs to unit U3 and is not "
                "loaded; the Mongo-backed subscription read path is declared-unexercised)"
            ),
            "period_id": period_id,
            "result_id": result_id,
            "rating_periods_docs_for_period": period_docs,
            "rating_results_docs_for_period": result_docs,
            "first_call": first_payload,
            "second_call": second_payload,
            "checks": checks,
            "verdict": "PASS" if ok else "FAIL",
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        for name, passed in checks.items():
            print(f"{name} | {'PASS' if passed else 'FAIL'}")
        print(f"U4 finalize idempotency | {report['verdict']} | {report_path}")
        return 0 if ok else 1
    finally:
        client.close()
        oracle.close()


if __name__ == "__main__":
    raise SystemExit(main())
