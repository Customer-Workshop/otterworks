#!/usr/bin/env python3
"""Replay the immutable U6 dunning transcripts against the migrated Mongo data."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.dunning_service import DunningService  # noqa: E402
from tp_mongo.rating_service import NS_VALUE  # noqa: E402

TARGET_DB = "ow_tp_mongodb_032752"
TRANSCRIPT_DIR = REPO_ROOT / "procs/oracle/transcripts/dunning"
STATUS_LABELS = {10: "scheduled", 20: "sent", 30: "skipped"}
NOTIFICATION_LABELS = {1: "invoice", 2: "dunning", 3: "suspension"}
SUBSCRIPTION_LABELS = {10: "active", 20: "suspended", 30: "cancelled"}


def _args():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn-secret",
        default="OW_BILLING_FIXTURE_DSN",
        help="environment variable name containing the Oracle fixture DSN",
    )
    parser.add_argument(
        "--uri-secret",
        default="MONGODB_ATLAS_URI",
        help="environment variable name containing the Mongo URI",
    )
    parser.add_argument("--target-db", default=TARGET_DB)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U6/parity_dunning.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _date_text(value) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _datetime_text(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(value) -> str:
    return STATUS_LABELS.get(value, "UNKNOWN")


def _notification_kind(value) -> str:
    return NOTIFICATION_LABELS.get(value, "UNKNOWN")


def _subscription_status(value) -> str:
    return SUBSCRIPTION_LABELS.get(value, "UNKNOWN")


def _restore(args, scenario: str) -> list[str]:
    env = os.environ.copy()
    commands = [
        ("load_u0.py", "u0"),
        ("load_u3.py", "u3"),
        ("load_u5.py", "u5"),
        ("load_u6.py", "u6"),
    ]
    used = []
    for script, unit in commands:
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts/tp_mongo" / script),
            "--dsn-secret",
            args.dsn_secret,
            "--uri-secret",
            args.uri_secret,
            "--report",
            f"/tmp/u6-{scenario}-{unit}-load-report.json",
        ]
        result = subprocess.run(
            command, cwd=REPO_ROOT, env=env, text=True, check=False
        )
        if result.returncode:
            raise RuntimeError(f"restoration command failed: {script}")
        used.append(" ".join(command))
    return used


def _schedule_rows(db) -> list[dict]:
    rows = []
    for invoice in db["invoices"].find({"ns": NS_VALUE}):
        for attempt in invoice.get("dunning_attempts", []):
            rows.append(
                {
                    "invoice_id": invoice["_id"],
                    "attempt_no": int(attempt["attempt_no"]),
                    "scheduled_for": _date_text(attempt["scheduled_for"]),
                    "status": _status(attempt.get("status_cd")),
                }
            )
    return sorted(rows, key=lambda row: (row["invoice_id"], row["attempt_no"]))


def _suspension_notifications(db) -> list[dict]:
    rows = []
    for notification in db["notifications"].find(
        {"kind_cd": 3, "ns": NS_VALUE}
    ).sort([("tenant_id", 1), ("sent_at", 1)]):
        rows.append(
            {
                "id": notification["_id"],
                "tenant_id": notification["tenant_id"],
                "kind": _notification_kind(notification.get("kind_cd")),
                "sent_at": _datetime_text(notification["sent_at"]),
            }
        )
    return rows


def _actual(service, db, scenario: str, inputs: dict) -> tuple[dict, dict]:
    as_of = _day(inputs["as_of"])
    if scenario == "DUNNING-001":
        rows = service.overdue_accounts(as_of)
        return {
            "tenant_ids": [row["tenant_id"] for row in rows],
            "days_overdue": [row["days_overdue"] for row in rows],
        }, {}
    if scenario == "DUNNING-002":
        service.schedule_dunning(as_of)
        invoice = db["invoices"].find_one(
            {"_id": "60000000-0000-0000-0000-000000000001", "ns": NS_VALUE}
        )
        attempt = max(invoice["dunning_attempts"], key=lambda row: row["attempt_no"])
        return {
            "scheduled_for": _date_text(attempt["scheduled_for"]),
            "status": _status(attempt.get("status_cd")),
        }, {"schedule_rows": _schedule_rows(db)}
    if scenario == "DUNNING-003":
        service.schedule_dunning(as_of)
        invoice = db["invoices"].find_one(
            {"_id": "60000000-0000-0000-0000-000000000002", "ns": NS_VALUE}
        )
        attempt = max(invoice["dunning_attempts"], key=lambda row: row["attempt_no"])
        return {
            "attempt_no": int(attempt["attempt_no"]),
            "scheduled_for": _date_text(attempt["scheduled_for"]),
        }, {"schedule_rows": _schedule_rows(db)}
    if scenario == "DUNNING-004":
        service.suspend_overdue(as_of)
        subscriptions = list(
            db["subscriptions"]
            .find(
                {
                    "tenant_id": "00000000-0000-0000-0000-000000000005",
                    "ns": NS_VALUE,
                }
            )
            .sort("_id", 1)
        )
        return {
            "status": _subscription_status(subscriptions[0].get("status_cd")),
            "suspended_on": _date_text(subscriptions[0]["suspended_on"]),
        }, {"suspension_notifications": _suspension_notifications(db)}
    if scenario == "DUNNING-005":
        service.suspend_overdue(as_of)
        notification_kinds = [
            _notification_kind(notification.get("kind_cd"))
            for notification in db["notifications"]
            .find(
                {
                    "tenant_id": "00000000-0000-0000-0000-000000000005",
                    "kind_cd": 3,
                    "ns": NS_VALUE,
                }
            )
            .sort("sent_at", 1)
        ]
        service.suspend_overdue(as_of)
        return {"notification_kinds": notification_kinds}, {
            "suspension_notifications": _suspension_notifications(db)
        }
    raise RuntimeError(f"{scenario}: unmapped scenario")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    uri_value = _secret_value(args.uri_secret, "Mongo URI secret")
    _secret_value(args.dsn_secret, "Oracle DSN secret")

    from pymongo import MongoClient

    client = MongoClient(uri_value)
    scenarios = []
    all_ok = True
    try:
        db = client[args.target_db]
        for path in sorted(TRANSCRIPT_DIR.glob("DUNNING-*.json")):
            transcript = json.loads(path.read_text())
            restoration = _restore(args, transcript["scenario"])
            actual, actual_probes = _actual(
                DunningService(db), db, transcript["scenario"], transcript["inputs"]
            )
            expected = transcript["business_fields"]
            expected_probes = transcript.get("probes", {})
            match = actual == expected and actual_probes == expected_probes
            scenario = {
                "scenario": transcript["scenario"],
                "entrypoint": transcript["entrypoint"],
                "oracle_entrypoint": transcript["oracle_entrypoint"],
                "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "inputs": transcript["inputs"],
                "expected": expected,
                "actual": actual,
                "expected_probes": expected_probes,
                "actual_probes": actual_probes,
                "restoration": {
                    "commands": restoration,
                    "completed": True,
                },
                "match": match,
            }
            scenarios.append(scenario)
            all_ok = all_ok and match
    finally:
        client.close()

    report = {
        "kind": "recon-report",
        "unit": "U6",
        "run_mode": "fixture",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_db": args.target_db,
        "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
        "transcript_dir": str(TRANSCRIPT_DIR.relative_to(REPO_ROOT)),
        "read_source": "migrated MongoDB collections only",
        "scenarios": scenarios,
        "verdict": "PASS" if all_ok else "FAIL",
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    for scenario in scenarios:
        print(f"{scenario['scenario']} | {'PASS' if scenario['match'] else 'FAIL'}")
    print(f"U6 dunning transcript parity | {report['verdict']} | {report_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
