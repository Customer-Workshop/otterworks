from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEGACY = ROOT / "services" / "legacy-billing" / "db" / "seed.sql"
OUTPUT = ROOT / "services" / "billing-service" / "db" / "documents.json"

COLLECTIONS = (
    "customers",
    "plans",
    "subscriptions",
    "usage_events",
    "rating_periods",
    "invoices",
    "credit_notes",
)


def _tuples(values: str) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    current: list[str | None] = []
    token: list[str] = []
    depth = 0
    quoted = False
    index = 0

    def finish_token() -> None:
        value = "".join(token).strip()
        current.append(None if value.upper() == "NULL" else value)
        token.clear()

    while index < len(values):
        character = values[index]
        if quoted:
            token.append(character)
            if character == "'":
                if index + 1 < len(values) and values[index + 1] == "'":
                    token.append(values[index + 1])
                    index += 1
                else:
                    quoted = False
            index += 1
            continue
        if character == "'":
            quoted = True
            token.append(character)
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                finish_token()
                rows.append(current)
                current = []
        elif character == "," and depth == 1:
            finish_token()
        elif depth == 1:
            token.append(character)
        index += 1
    return rows


def _value(raw: str | None):
    if raw is None:
        return None
    raw = raw.strip()
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1].replace("''", "'")
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return Decimal(raw)


def _legacy_rows(source: str, table: str) -> list[dict]:
    match = re.search(
        rf"INSERT INTO billing\.{table}\s*\((.*?)\)\s*VALUES\s*(.*?);",
        source,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match is None:
        raise RuntimeError(f"missing legacy seed section: {table}")
    columns = [column.strip() for column in match.group(1).split(",")]
    return [
        dict(zip(columns, (_value(value) for value in row), strict=True))
        for row in _tuples(match.group(2))
    ]


def _money(value: Decimal, places: int) -> str:
    return format(value, f".{places}f")


def generate() -> str:
    source = LEGACY.read_text()
    tenants = _legacy_rows(source, "tenants")
    plans = _legacy_rows(source, "plans")
    subscriptions = _legacy_rows(source, "subscriptions")
    usage_events = _legacy_rows(source, "usage_events")
    periods = _legacy_rows(source, "rating_periods")
    results = {row["period_id"]: row for row in _legacy_rows(source, "rating_results")}
    invoices = _legacy_rows(source, "invoices")
    invoice_lines: dict[str, list[dict]] = {}
    for line in _legacy_rows(source, "invoice_lines"):
        invoice_lines.setdefault(line["invoice_id"], []).append(line)
    credit_notes = _legacy_rows(source, "credit_notes")

    documents = {
        "customers": [
            {
                "_id": row["id"],
                "name": row["name"],
                "tax_exempt": row["tax_exempt"],
                "status": row["status"],
            }
            for row in tenants
        ],
        "plans": [
            {
                "_id": row["id"],
                "code": row["code"],
                "tier": row["tier"],
                "monthly_fee": _money(row["monthly_fee"], 2),
                "included_units": row["included_units"],
                "overage_rate": _money(row["overage_rate"], 6),
                "active": True,
            }
            for row in plans
        ],
        "subscriptions": [
            {
                "_id": row["id"],
                "tenant_id": row["tenant_id"],
                "plan_id": row["plan_id"],
                "starts_on": row["starts_on"],
                "ends_on": row["ends_on"],
                "status": row["status"],
                "suspended_on": row["suspended_on"],
            }
            for row in subscriptions
        ],
        "usage_events": [
            {
                "_id": row["id"],
                "tenant_id": row["tenant_id"],
                "occurred_at": row["occurred_at"],
                "units": row["units"],
                "kind": row["kind"],
            }
            for row in usage_events
        ],
        "rating_periods": [
            {
                "_id": row["id"],
                "tenant_id": row["tenant_id"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "result": (
                    {
                        "result_id": result["id"],
                        "subscription_id": result["subscription_id"],
                        "used_units": result["used_units"],
                        "quota_units": result["quota_units"],
                        "rollover_units": result["rollover_units"],
                        "billable_units": result["billable_units"],
                        "overage_amount": _money(result["overage_amount"], 2),
                        "created_at": result["created_at"],
                    }
                    if (result := results.get(row["id"])) is not None
                    else None
                ),
            }
            for row in periods
        ],
        "invoices": [
            {
                "_id": row["id"],
                "tenant_id": row["tenant_id"],
                "period_id": row["period_id"],
                "issued_at": row["issued_at"],
                "subtotal": _money(row["subtotal"], 2),
                "tax": _money(row["tax"], 2),
                "total": _money(row["total"], 2),
                "status": row["status"],
                "lines": [
                    {
                        "line_no": line["line_no"],
                        "line_type": line["line_type"],
                        "description": line["description"],
                        "amount": _money(line["amount"], 2),
                    }
                    for line in sorted(
                        invoice_lines.get(row["id"], []), key=lambda item: item["line_no"]
                    )
                ],
            }
            for row in invoices
        ],
        "credit_notes": [
            {
                "_id": row["id"],
                "tenant_id": row["tenant_id"],
                "issued_on": row["issued_on"],
                "amount": _money(row["amount"], 2),
                "remaining_amount": _money(row["remaining_amount"], 2),
            }
            for row in credit_notes
        ],
    }
    for collection in documents.values():
        collection.sort(key=lambda document: document["_id"])
    return json.dumps(documents, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(generate())
