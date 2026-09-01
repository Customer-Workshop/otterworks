"""Tests for U3 mapping type conversion and SQL planning."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.load_u3 import (  # noqa: E402
    _document,
    _plan,
    _select,
    converter,
)


def _entry(collection):
    spec = json.loads((REPO_ROOT / ".migration/03_mapping_spec.json").read_text())
    return next(item for item in spec["collections"] if item["collection"] == collection)


def test_converter_handles_varchar2_empty_as_null():
    field = next(field for field in _entry("subscriptions")["fields"] if field["target"] == "tenant_id")
    convert = converter(field)
    assert convert("") is None
    assert convert("t1") == "t1"


def test_converter_truncates_date_to_utc_milliseconds():
    field = next(field for field in _entry("subscriptions")["fields"] if field["target"] == "starts_on")
    result = converter(field)(datetime(2026, 9, 1, 1, 2, 3, 456789))
    assert result == datetime(2026, 9, 1, 1, 2, 3, 456000, tzinfo=timezone.utc)


def test_converter_maps_number_four_zero_to_int_and_null():
    field = next(field for field in _entry("subscriptions")["fields"] if field["target"] == "status_cd")
    convert = converter(field)
    assert convert(20) == 20
    assert isinstance(convert(20), int)
    assert convert(None) is None


def test_document_keeps_null_fields_explicit_and_coerces_history_key():
    plan = _plan(_entry("subscriptions_hist"))
    row = {"HIST_ID": 7, **{column: None for column in plan["columns"][1:]}}
    document = _document(row, plan)
    assert document["_id"] == 7
    assert document["hist_dt"] is None
    assert document["status_cd"] is None
    assert document["ns"] == "mongo_032752"


def test_select_sql_shape_uses_approved_columns_and_ordering():
    plan = _plan(_entry("subscriptions"))
    assert _select(plan) == (
        "SELECT ID, TENANT_ID, PLAN_ID, STARTS_ON, ENDS_ON, STATUS_CD, SUSPENDED_ON "
        "FROM SUBSCRIPTIONS ORDER BY ID"
    )
