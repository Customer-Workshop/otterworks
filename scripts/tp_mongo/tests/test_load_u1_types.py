"""Tests for U1 mapping type resolution and conversion."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from bson import Decimal128

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.load_u1 import _write_bson_type, converter  # noqa: E402


def _customers() -> dict:
    spec = json.loads((REPO_ROOT / ".migration/03_mapping_spec.json").read_text())
    return next(item for item in spec["collections"] if item["collection"] == "customers")


def test_grading_blanked_fields_reuse_same_source_type_write_type():
    customers = _customers()
    nonblank_by_source_type = {
        field["source_type"]: field["bson_type"]
        for field in customers["fields"]
        if field["bson_type"]
    }
    blank_fields = [field for field in customers["fields"] if not field["bson_type"]]

    assert blank_fields
    for field in blank_fields:
        assert _write_bson_type(field) == nonblank_by_source_type[field["source_type"]]
        assert "null_missing_equiv" in field["rules"]


def test_null_missing_amendment_counts():
    fields = _customers()["fields"]
    amended = [field for field in fields if "null_missing_equiv" in field["rules"]]

    assert len(amended) == 19
    assert sum(not field["bson_type"] for field in amended) == 17


def test_blank_decimal_type_converts_decimal_and_null():
    field = next(
        field
        for field in _customers()["fields"]
        if field["source_type"] == "NUMBER(14,2)" and not field["bson_type"]
    )
    convert = converter(field)

    assert convert(Decimal("1.005")) == Decimal128("1.00")
    assert convert(None) is None


def test_blank_integer_type_converts_int_and_null():
    field = next(
        field
        for field in _customers()["fields"]
        if field["source_type"] == "NUMBER(4,0)" and not field["bson_type"]
    )
    convert = converter(field)

    assert convert(7) == 7
    assert isinstance(convert(7), int)
    assert convert(None) is None


def test_blank_type_rejects_unsupported_source_type():
    field = {
        "source": "BROKEN_FIELD",
        "source_type": "VARCHAR2",
        "bson_type": "",
    }

    with pytest.raises(RuntimeError, match="blank bson_type with unsupported source_type"):
        converter(field)
