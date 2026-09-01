#!/usr/bin/env python3
"""Replay the immutable U5 invoicing transcripts against the migrated Mongo data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.invoicing_service import InvoicingService  # noqa: E402
from tp_mongo.rating_service import RatingService, md5_uuid  # noqa: E402

TARGET_DB = "ow_tp_mongodb_032752"
TRANSCRIPT_DIR = REPO_ROOT / "procs/oracle/transcripts/invoicing"


def _args():
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
        default=str(REPO_ROOT / ".migration/recon/U5/parity_invoicing.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _decimal_of(value):
    to_decimal = getattr(value, "to_decimal", None)
    return to_decimal() if callable(to_decimal) else value


def _normalize(value, like):
    if isinstance(like, list):
        return [_normalize(v, like[0] if like else 0) for v in value]
    value = _decimal_of(value)
    if value is None:
        return None
    if isinstance(like, str):
        try:
            return f"{Decimal(str(value)).quantize(Decimal('0.01')):f}"
        except (InvalidOperation, ValueError):
            return str(value)
    if isinstance(like, bool):
        return bool(value)
    if isinstance(like, int):
        return int(value)
    return value


def _compare(expected: dict, actual: dict) -> tuple[dict, dict, bool]:
    rendered = {}
    for name, want in expected.items():
        got = actual.get(name, "<absent>")
        if isinstance(got, list):
            got = [_decimal_of(value) for value in got]
        rendered[name] = (
            _normalize(got, want) if got != "<absent>" else got
        )
    return expected, rendered, rendered == expected


def _compare_rows(expected_rows, actual_rows) -> tuple[list, bool]:
    if len(expected_rows) != len(actual_rows):
        return [
            {"row_count": {"expected": len(expected_rows), "actual": len(actual_rows)}}
        ], False
    rendered = []
    ok = True
    for expected, actual in zip(expected_rows, actual_rows):
        _, row, row_ok = _compare(expected, actual)
        rendered.append(row)
        ok = ok and row_ok
    return rendered, ok


def _actual_preview(service, inputs):
    rows = service.invoice_preview(
        inputs["tenant_id"],
        _day(inputs["period_start"]),
        _day(inputs["period_end"]),
    )
    return {
        "amounts": [row["amount"] for row in rows],
        "line_numbers": [row["line_no"] for row in rows],
        "totals": [row["total"] for row in rows],
        "line_types": [row["line_type"] for row in rows],
        "tax_amount": [row["tax_amount"] for row in rows],
    }


def _invoice_id(inputs):
    period_id = md5_uuid(
        inputs["tenant_id"] + inputs["period_start"]
    )
    return md5_uuid(period_id + "invoice")


def _render_date(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _actual_issue(service, db, inputs):
    service.issue_invoice(
        inputs["tenant_id"],
        _day(inputs["period_start"]),
        _day(inputs["period_end"]),
    )
    invoice_id = _invoice_id(inputs)
    invoice = db["invoices"].find_one({"_id": invoice_id, "ns": "mongo_032752"})
    notes = list(
        db["credit_notes"]
        .find({"tenant_id": inputs["tenant_id"], "ns": "mongo_032752"})
        .sort([("issued_on", 1), ("_id", 1)])
    )
    return {
        "status": "issued" if invoice and invoice.get("status_cd") == 20 else None,
        "tax": invoice.get("tax") if invoice else None,
        "total": invoice.get("total") if invoice else None,
        "credit_ids": [note["_id"] for note in notes],
        "issued_on": [
            _render_date(note["issued_on"])
            for note in notes
        ],
        "remaining": [note.get("remaining_amount") for note in notes],
    }, invoice


def _actual_lines(service, inputs):
    return service.invoice_lines(inputs["invoice_id"])


def _issue_probe(invoice):
    return [
        {
            "status": "issued" if invoice and invoice.get("status_cd") == 20 else None,
            "subtotal": invoice.get("subtotal") if invoice else None,
            "tax": invoice.get("tax") if invoice else None,
            "total": invoice.get("total") if invoice else None,
        }
    ]


def _restore(args):
    env = os.environ.copy()
    commands = [
        [
            sys.executable,
            str(REPO_ROOT / "scripts/tp_mongo/load_u4.py"),
            "--dsn-secret",
            args.dsn_secret,
            "--uri-secret",
            args.uri_secret,
        ],
        [
            sys.executable,
            str(REPO_ROOT / "scripts/tp_mongo/load_u5.py"),
            "--dsn-secret",
            args.dsn_secret,
            "--uri-secret",
            args.uri_secret,
        ],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True)
        if result.returncode:
            raise RuntimeError(f"restoration command failed: {command[1]}")
    return [
        "scripts/tp_mongo/load_u4.py",
        "scripts/tp_mongo/load_u5.py",
    ]


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
    restoration = []
    try:
        db = client[args.target_db]
        service = InvoicingService(db, RatingService(db))
        for path in sorted(TRANSCRIPT_DIR.glob("*.json")):
            transcript = json.loads(path.read_text())
            inputs = transcript["inputs"]
            entrypoint = transcript["entrypoint"]
            probes_rendered = {}
            if entrypoint == "billing.fn_invoice_preview":
                actual = _actual_preview(service, inputs)
            elif entrypoint == "billing.sp_issue_invoice":
                actual, invoice = _actual_issue(service, db, inputs)
            elif entrypoint == "billing.fn_invoice_lines":
                actual_lines = _actual_lines(service, inputs)
                actual = {
                    "amounts": [line["amount"] for line in actual_lines],
                    "line_types": [line["line_type"] for line in actual_lines],
                }
                invoice = None
            else:
                raise RuntimeError(f"{path.name}: unmapped entrypoint {entrypoint}")

            expected, rendered, ok = _compare(transcript["business_fields"], actual)
            if entrypoint == "billing.sp_issue_invoice":
                for probe_id, expected_rows in transcript.get("probes", {}).items():
                    probe_rows, probe_ok = _compare_rows(
                        expected_rows, _issue_probe(invoice)
                    )
                    probes_rendered[probe_id] = probe_rows
                    ok = ok and probe_ok
            all_ok = all_ok and ok
            scenarios.append(
                {
                    "scenario": transcript["scenario"],
                    "entrypoint": entrypoint,
                    "oracle_entrypoint": transcript["oracle_entrypoint"],
                    "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "inputs": inputs,
                    "expected": expected,
                    "actual": rendered,
                    "expected_probes": transcript.get("probes", {}),
                    "actual_probes": probes_rendered,
                    "mutates_target": entrypoint == "billing.sp_issue_invoice",
                    "match": ok,
                }
            )
    finally:
        client.close()
        restoration = _restore(args)

    report = {
        "kind": "recon-report",
        "unit": "U5",
        "run_mode": "fixture",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_db": args.target_db,
        "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
        "transcript_dir": str(TRANSCRIPT_DIR.relative_to(REPO_ROOT)),
        "read_source": "migrated MongoDB collections only",
        "restoration": {
            "commands": restoration,
            "required_after_mutation": True,
            "completed": True,
        },
        "scenarios": scenarios,
        "verdict": "PASS" if all_ok else "FAIL",
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    for scenario in scenarios:
        print(f"{scenario['scenario']} | {'PASS' if scenario['match'] else 'FAIL'}")
    print(f"U5 invoicing transcript parity | {report['verdict']} | {report_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
