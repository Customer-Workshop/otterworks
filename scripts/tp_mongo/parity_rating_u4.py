#!/usr/bin/env python3
"""Replay the recorded Oracle rating transcripts against the migrated rating service.

The transcripts in procs/oracle/transcripts/rating/ are immutable recordings of the
OW_BILLING PL/SQL entrypoints (pkg_rating.fn_usage_rating / fn_usage_summary /
sp_finalize_rating) under the NS=demo fixture, normalized by procs/harness. This replays
the same scenario inputs through scripts/tp_mongo/rating_service.py, reading
`usage_events`, `rating_periods`, `rating_results` and `plans` from the migrated database,
and compares the recorded business fields value-for-value.

`subscriptions` belongs to unit U3 and is not loaded yet, so the covering-subscription read
is served from a read-only Oracle extract (StaticSubscriptionSource) instead of the
migrated collection; that substitution is recorded in the emitted report and declared as an
unverified path in the unit PR.

RATING-008 replays sp_finalize_rating, which writes `rating_periods`/`rating_results`;
run the loader again afterwards (drop+recreate) before the recon gate.

This report is parity evidence for the stored-procedure conversion. It is not the merge
authority: the mongo-recon-harness result.json is.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.rating_service import (  # noqa: E402
    RatingService,
    StaticSubscriptionSource,
)

TARGET_DB = "ow_tp_mongodb_032752"
TRANSCRIPT_DIR = REPO_ROOT / "procs/oracle/transcripts/rating"
SUBSCRIPTION_SQL = (
    "SELECT ID, TENANT_ID, PLAN_ID, STARTS_ON, ENDS_ON, STATUS_CD, SUSPENDED_ON "
    "FROM SUBSCRIPTIONS ORDER BY ID"
)
# fn_usage_rating projects the package globals; the transcripts capture a subset per
# scenario (procs/scenarios/rating/*.yaml).
RATING_FIELDS = (
    "used_units",
    "quota_units",
    "rollover_units",
    "billable_units",
    "first_tier_units",
    "second_tier_units",
    "overage_amount",
)


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
        "--report", default=str(REPO_ROOT / ".migration/recon/U4/parity_rating.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _subscription_docs(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(SUBSCRIPTION_SQL)
    return [
        {
            "_id": row[0],
            "tenant_id": row[1],
            "plan_id": row[2],
            "starts_on": row[3],
            "ends_on": row[4],
            "status_cd": int(row[5]),
            "suspended_on": row[6],
        }
        for row in cursor.fetchall()
    ]


def _normalize(value, like):
    """Render a computed value in the shape procs/harness recorded.

    Recorded decimals are TO_CHAR(...,'FM999999990.00') strings, integers are integers,
    and `collect: true` fields are ordered lists.
    """
    if isinstance(like, list):
        return [_normalize(v, like[0] if like else 0) for v in value]
    if value is None:
        return None
    if isinstance(like, str):
        try:
            return f"{Decimal(str(value)).quantize(Decimal('0.01')):f}"
        except InvalidOperation:  # recorded text field (kind labels), not a decimal
            return str(value)
    if isinstance(like, bool):
        return bool(value)
    if isinstance(like, int):
        return int(value)
    return value


def _actual_rating(service, inputs) -> dict:
    rating = service.compute_rating(
        inputs["tenant_id"], _day(inputs["period_start"]), _day(inputs["period_end"])
    )
    return {name: getattr(rating, name) for name in RATING_FIELDS}


def _actual_summary(service, inputs) -> dict:
    rows = service.usage_summary(
        inputs["tenant_id"], _day(inputs["period_start"]), _day(inputs["period_end"])
    )
    return {
        "kinds": [row["kind"] for row in rows],
        "units": [row["units"] for row in rows],
        "event_count": [row["event_count"] for row in rows],
    }


def _finalized_rows(db, tenant_id: str, period_start: datetime) -> list[dict]:
    """The rollover read path: rating_results joined to rating_periods (oracle_map.yaml
    scenario RATING-008 probe)."""
    pipeline = [
        {"$lookup": {
            "from": "rating_periods",
            "localField": "period_id",
            "foreignField": "_id",
            "as": "period",
        }},
        {"$unwind": "$period"},
        {"$match": {
            "period.tenant_id": tenant_id,
            "period.period_start": period_start,
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = []
    for doc in db["rating_results"].aggregate(pipeline):
        rows.append({
            "used_units": doc["used_units"],
            "quota_units": doc["quota_units"],
            "rollover_units": doc["rollover_units"],
            "billable_units": doc["billable_units"],
            "overage_amount": doc["overage_amount"],
        })
    return rows


def _actual_finalize(service, db, inputs) -> tuple[dict, list[dict]]:
    service.finalize_rating(
        inputs["tenant_id"], _day(inputs["period_start"]), _day(inputs["period_end"])
    )
    rows = _finalized_rows(db, inputs["tenant_id"], _day(inputs["period_start"]))
    return (rows[0] if rows else {}), rows


def _decimal_of(value):
    to_decimal = getattr(value, "to_decimal", None)
    return to_decimal() if callable(to_decimal) else value


def _compare(expected: dict, actual: dict) -> tuple[dict, dict, bool]:
    """Compare only the fields the transcript recorded, in the recorded shape."""
    rendered = {}
    for name, want in expected.items():
        got = actual.get(name, "<absent>")
        if isinstance(got, list):
            got = [_decimal_of(v) for v in got]
        else:
            got = _decimal_of(got)
        rendered[name] = _normalize(got, want) if got != "<absent>" else got
    return expected, rendered, rendered == expected


def _compare_rows(expected_rows, actual_rows) -> tuple[list, bool]:
    rendered = []
    if len(expected_rows) != len(actual_rows):
        return [{"row_count": {"expected": len(expected_rows), "actual": len(actual_rows)}}], False
    ok = True
    for want, got in zip(expected_rows, actual_rows):
        _, row, row_ok = _compare(want, got)
        rendered.append(row)
        ok = ok and row_ok
    return rendered, ok


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
        service = RatingService(db, subscription_source=StaticSubscriptionSource(subscriptions))

        scenarios = []
        all_ok = True
        for path in sorted(TRANSCRIPT_DIR.glob("*.json")):
            transcript = json.loads(path.read_text())
            inputs = transcript["inputs"]
            entrypoint = transcript["entrypoint"]
            probes_rendered = {}
            rows: list[dict] = []
            if entrypoint == "billing.fn_usage_rating":
                actual = _actual_rating(service, inputs)
            elif entrypoint == "billing.fn_usage_summary":
                actual = _actual_summary(service, inputs)
            elif entrypoint == "billing.sp_finalize_rating":
                actual, rows = _actual_finalize(service, db, inputs)
            else:
                raise RuntimeError(f"{path.name}: unmapped entrypoint {entrypoint}")

            expected, rendered, ok = _compare(transcript["business_fields"], actual)
            for probe_id, want_rows in transcript.get("probes", {}).items():
                probe_rows, probe_ok = _compare_rows(want_rows, rows)
                probes_rendered[probe_id] = probe_rows
                ok = ok and probe_ok
            all_ok = all_ok and ok
            scenarios.append({
                "scenario": transcript["scenario"],
                "entrypoint": entrypoint,
                "oracle_entrypoint": transcript["oracle_entrypoint"],
                "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "inputs": inputs,
                "expected": expected,
                "actual": rendered,
                "expected_probes": transcript.get("probes", {}),
                "actual_probes": probes_rendered,
                "mutates_target": entrypoint == "billing.sp_finalize_rating",
                "match": ok,
            })

        report = {
            "unit": "U4",
            "run_mode": "fixture",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_db": args.target_db,
            "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
            "transcript_dir": str(TRANSCRIPT_DIR.relative_to(REPO_ROOT)),
            "subscription_source": (
                "read-only Oracle extract (SUBSCRIPTIONS belongs to unit U3 and is not "
                "loaded; the Mongo-backed subscription read path is declared-unexercised)"
            ),
            "scenarios": scenarios,
            "verdict": "PASS" if all_ok else "FAIL",
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        for scenario in scenarios:
            print(f"{scenario['scenario']} | {'PASS' if scenario['match'] else 'FAIL'}")
        print(f"U4 rating transcript parity | {report['verdict']} | {report_path}")
        return 0 if all_ok else 1
    finally:
        client.close()
        oracle.close()


if __name__ == "__main__":
    raise SystemExit(main())
