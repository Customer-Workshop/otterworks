"""Contract tests for the customers transform.

Run with `make mongo-customers-test`. These cover the branches live estate data
does not reach on its own — undecodable bytes, a NULL required key, the empty
source set — so the fail-closed behaviour is proven rather than assumed.
"""

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from bson import Decimal128

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrate import discover_batch_no  # noqa: E402
from schema import LEGACY_COLUMNS, MODELLED_COLUMNS, customers_validator  # noqa: E402
from transform import (ID_NAMESPACE, build_attribute_entry,  # noqa: E402
                       build_document, decode_text, document_id, parse_csv_list,
                       parse_legacy_date)

NS = "demo"
BATCH = 85559852


def row(**overrides):
    base = {"cust_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
            "tenant_id": "aa11bb22-cc33-dd44-ee55-ff6677889900",
            "cust_no": "DEMO-00000001", "cust_name": "Alex Otter",
            "legal_name": "Alex Otter LLC", "signup_dt": "04-JUL-19",
            "related_acct_ids": "12345,67890", "promo_codes_csv": "",
            "cur_bal_amt": 1234.5, "conversion_batch_no": BATCH}
    base.update(overrides)
    return base


def test_id_is_uuid5_and_stable():
    doc, _ = build_document(row(), NS, BATCH)
    assert doc["_id"] == uuid.uuid5(ID_NAMESPACE, f"{NS}:{row()['cust_id']}")
    assert doc["_id"].version == 5
    again, _ = build_document(row(), NS, BATCH)
    assert again["_id"] == doc["_id"]
    assert document_id("other", row()["cust_id"]) != doc["_id"]


def test_valid_date_becomes_utc_bson_date():
    doc, attributions = build_document(row(signup_dt="04-JUL-19"), NS, BATCH)
    assert doc["signup_dt"] == datetime(2019, 7, 4, tzinfo=timezone.utc)
    assert attributions == []


@pytest.mark.parametrize("dirty", ["31-FEB-24", "00-XXX-00", "99-999-99",
                                   "1/1/1900", "N/A", "29-FEB-23", "  -   -  ",
                                   "12-13-201"])
def test_dirty_dates_are_quarantined_never_coerced(dirty):
    doc, attributions = build_document(row(signup_dt=dirty), NS, BATCH)
    assert "signup_dt" not in doc, "a dirty date must not be defaulted or nulled"
    assert [a.reason for a in attributions] == ["dirty_date"]
    assert attributions[0].raw_value == dirty
    qdoc = attributions[0].document(NS, doc["customer_id"], BATCH)
    assert qdoc["raw_value"] == dirty and qdoc["namespace"] == NS


def test_empty_csv_list_is_an_empty_array():
    doc, attributions = build_document(row(related_acct_ids="",
                                           promo_codes_csv=""), NS, BATCH)
    assert doc["related_acct_ids"] == []
    assert doc["promo_codes"] == []
    assert attributions == []


def test_null_csv_column_is_omitted_not_null():
    doc, _ = build_document(row(related_acct_ids=None), NS, BATCH)
    assert "related_acct_ids" not in doc


@pytest.mark.parametrize("raw,elements", [
    (",,", []),
    ("12345,,67890,", ["12345", "67890"]),
    ("A;B;C", []),
    (" , 99 ,", []),
    ("NULL,NONE,", []),
    ("0000000000000000000000,", ["0000000000000000000000"]),
])
def test_malformed_lists_are_tolerated_and_attributed(raw, elements):
    doc, attributions = build_document(row(related_acct_ids=raw), NS, BATCH)
    assert doc["related_acct_ids"] == elements
    assert [a.reason for a in attributions] == ["malformed_csv_list"]
    assert attributions[0].raw_value == raw
    assert attributions[0].parsed_elements == elements


def test_well_formed_lists_are_not_attributed():
    doc, attributions = build_document(row(related_acct_ids="10001,20002"), NS, BATCH)
    assert doc["related_acct_ids"] == ["10001", "20002"]
    assert attributions == []


def test_sparse_columns_are_omitted_when_null():
    doc, _ = build_document(row(addr_line_1="1 Main St", addr_line_2=None,
                                flag_01=None, udf_01="x"), NS, BATCH)
    legacy = doc["legacy"]
    assert legacy["addr_line_1"] == "1 Main St"
    assert legacy["udf_01"] == "x"
    assert "addr_line_2" not in legacy and "flag_01" not in legacy


def test_missing_required_key_fails_closed():
    doc, attributions = build_document(row(cust_id=None), NS, BATCH)
    assert doc is None, "a NULL CUST_ID must never fail open into a document"
    assert [a.reason for a in attributions] == ["missing_required_field"]


def test_undecodable_bytes_are_quarantined_as_hex():
    doc, attributions = build_document(row(cust_name=b"\xff\xfeAlex"), NS, BATCH)
    assert "customer_name" not in doc
    assert [a.reason for a in attributions] == ["invalid_encoding"]
    assert attributions[0].raw_hex == "fffe416c6578"
    assert "\ufffd" not in repr(attributions[0].raw_hex)


def test_text_is_carried_through_byte_for_byte():
    doc, _ = build_document(row(cust_name="  Ålex   Otter\t"), NS, BATCH)
    assert doc["customer_name"] == "  Ålex   Otter\t"


def test_balances_are_decimal128():
    doc, _ = build_document(row(cur_bal_amt=1234.5), NS, BATCH)
    assert doc["balances"]["current_amount"] == Decimal128("1234.50")


def test_attribute_entry_preserves_name_and_value():
    entry, error = build_attribute_entry("see ticket 48213", "STR", "04-JUL-19")
    assert error is None
    assert entry["value"] == "see ticket 48213"
    assert entry["created_dt"] == datetime(2019, 7, 4, tzinfo=timezone.utc)


def test_attribute_entry_keeps_unparsable_created_dt_verbatim():
    entry, error = build_attribute_entry("blue", "STR", "31-FEB-24")
    assert error is None
    assert entry["created_dt_raw"] == "31-FEB-24"
    assert "created_dt" not in entry


@pytest.mark.parametrize("created_dt", ["31-FEB-24", "04-JUL-19"])
def test_validator_covers_attribute_entry_keys(created_dt):
    entry, error = build_attribute_entry("blue", "STR", created_dt)
    assert error is None
    properties = customers_validator()["$jsonSchema"]["properties"]["attributes"][
        "additionalProperties"
    ]["items"]["properties"]
    assert set(entry) <= set(properties)


def test_null_attribute_value_is_attributed():
    entry, error = build_attribute_entry(None, "STR", "04-JUL-19")
    assert entry is None and error == "null_attribute_value"


def test_two_digit_year_pivot():
    assert parse_legacy_date("01-JAN-49")[0].year == 2049
    assert parse_legacy_date("01-JAN-50")[0].year == 1950


def test_decode_text_passes_valid_utf8():
    assert decode_text("ötter") == ("ötter", None)
    assert decode_text(b"\xc3\xb6tter") == ("ötter", None)


def test_parse_csv_list_none_is_none():
    assert parse_csv_list(None) == (None, False)


def test_validator_covers_every_modelled_column():
    """The validator is additionalProperties:false, so it must know every field."""
    schema = customers_validator()["$jsonSchema"]
    assert schema["additionalProperties"] is False
    legacy = schema["properties"]["legacy"]["properties"]
    assert set(legacy) == set(LEGACY_COLUMNS)
    assert "cust_id" in MODELLED_COLUMNS
    assert set(LEGACY_COLUMNS) & MODELLED_COLUMNS == set()


def test_validator_rejects_the_two_legacy_shapes_by_construction():
    schema = customers_validator()["$jsonSchema"]
    assert schema["properties"]["signup_dt"]["bsonType"] == "date"
    assert "tax_region_override" not in schema["properties"]


def test_discover_batch_no_uses_literal_prefix_matching():
    class Cursor:
        def __init__(self):
            self.statement = None
            self.binds = None

        def execute(self, statement, **binds):
            self.statement = statement
            self.binds = binds

        def fetchall(self):
            return [(BATCH,)]

    cursor = Cursor()
    assert discover_batch_no(cursor, "demo") == BATCH
    assert "LIKE" not in cursor.statement.upper()
    assert "SUBSTR(cust_no, 1, LENGTH(" in cursor.statement
