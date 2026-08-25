from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bson.decimal128 import Decimal128

from app.docstore import convert_document, load_seed


def test_document_conversion_uses_bson_money_and_utc_datetimes() -> None:
    document = convert_document(
        "invoices",
        {
            "_id": "invoice",
            "issued_at": "2026-02-01T00:00:00Z",
            "subtotal": "149.00",
            "tax": "12.29",
            "total": "161.29",
            "lines": [{"line_no": 1, "amount": "149.00"}],
        },
    )
    assert document["subtotal"] == Decimal128("149.00")
    assert document["lines"][0]["amount"] == Decimal128("149.00")
    assert document["issued_at"] == datetime(2026, 2, 1, tzinfo=UTC)

    subscription = convert_document("subscriptions", {"starts_on": "2026-01-01"})
    assert subscription["starts_on"] == datetime(2026, 1, 1, tzinfo=UTC)


def test_document_seed_has_embedded_children_and_expected_catalog() -> None:
    seed = load_seed()
    assert len(seed["customers"]) == 9
    assert len(seed["plans"]) == 3
    assert all("result" in period for period in seed["rating_periods"])
    assert all(
        line["line_no"] < next_line["line_no"]
        for invoice in seed["invoices"]
        for line, next_line in zip(invoice["lines"], invoice["lines"][1:], strict=False)
    )
    assert seed["rating_periods"][0]["result"]["result_id"]


def test_generated_document_seed_matches_checked_in_file() -> None:
    from scripts.generate_document_seed import generate

    seed_path = Path(__file__).parents[1] / "db" / "documents.json"
    assert seed_path.read_text() == generate()
