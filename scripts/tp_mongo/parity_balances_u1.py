#!/usr/bin/env python3
"""Side-by-side parity evidence for the RPT-114 balances rollup (Oracle vs MongoDB).

Both sides are shaped through the report module's own shape_balances, so the
comparison is the app-level output, not a re-implementation of the query.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
REPO_ROOT = Path(__file__).resolve().parents[1].parent
REPORTS_PATH = REPO_ROOT / "services/legacy-billing/app/reports.py"


def _load_reports(path: Path = REPORTS_PATH):
    spec = importlib.util.spec_from_file_location("ow_billing_reports", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _oracle_balances(reports, dsn_secret: str, batch_no: int):
    dsn_value = _secret_value(dsn_secret, "Oracle DSN secret")
    try:
        user, password, dsn = dsn_value.split("/", 2)
    except ValueError as exc:
        raise RuntimeError(
            f"Oracle DSN secret '{dsn_secret}' must contain user/password/dsn"
        ) from exc

    import oracledb

    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(reports.BALANCES_SQL, {"batch_no": batch_no})
            rows = cursor.fetchall()
    finally:
        connection.close()
    return reports.shape_balances(rows[0])


def _mongo_balances(reports, uri_secret: str, target_db: str, batch_no: int):
    uri_value = _secret_value(uri_secret, "Mongo URI secret")

    from pymongo import MongoClient

    client = MongoClient(uri_value)
    try:
        rows = list(
            client[target_db]["customers"].aggregate(reports.balances_pipeline(batch_no))
        )
    finally:
        client.close()
    if not rows:
        return reports.shape_balances((0, None, None))
    row = rows[0]
    return reports.shape_balances(
        (
            row["customer_count"],
            reports.fm_amount(row["current_balance_total"]),
            reports.fm_amount(row["past_due_total"]),
        )
    )


def main() -> int:
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
        "--batch-no", type=int, default=None,
        help="conversion batch number; defaults to the NS=demo batch",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / ".migration/recon/U1/parity/balances_parity.json"),
    )
    args = parser.parse_args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")

    reports = _load_reports()
    if args.batch_no is None:
        args.batch_no = reports.ns_batch_no("demo")

    oracle_balances = _oracle_balances(reports, args.dsn_secret, args.batch_no)
    mongo_balances = _mongo_balances(
        reports, args.uri_secret, args.target_db, args.batch_no
    )
    verdict = "PASS" if oracle_balances == mongo_balances else "FAIL"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "unit": "U1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "report": "rpt-114-balances",
                "batch_no": args.batch_no,
                "ns": NS_VALUE,
                "target_db": args.target_db,
                "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
                "oracle": oracle_balances,
                "mongodb": mongo_balances,
                "verdict": verdict,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"U1 balances parity | {verdict} | batch_no={args.batch_no} | {out_path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
