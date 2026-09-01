"""Unit tests for the customer write path replacing the Oracle triggers.

Run from the repository root:
    /home/ubuntu/.venvs/recon/bin/python -m pytest scripts/tp_mongo/tests
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import Int64, ObjectId

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.customer_write_path import (  # noqa: E402
    NS_VALUE,
    TARGET_DB,
    CustomerWritePath,
    app_cust_seq_no,
    derive_on_insert,
    hist_dt_string,
    history_doc,
    history_fields,
    next_attribute,
)


class _FakeDatabase:
    def __init__(self, name):
        self.name = name
        self.client = None

    def __getitem__(self, _collection_name):
        return None


class _AttributeFakeCollection:
    def __init__(self):
        self.pre_image = {
            "_id": "c-1",
            "attributes": [{"attr_name": "existing", "attr_value": "one"}],
        }
        self.find_sessions = []
        self.update_sessions = []
        self.updates = []

    def find_one(self, _query, session=None):
        self.find_sessions.append(session)
        return {
            "_id": self.pre_image["_id"],
            "attributes": [dict(element) for element in self.pre_image["attributes"]],
        }

    def update_one(self, _query, update, session=None):
        self.update_sessions.append(session)
        self.updates.append(update)


class _AttributeFakeSession:
    def __init__(self, collection):
        self.collection = collection
        self.with_transaction_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def with_transaction(self, callback):
        self.with_transaction_calls += 1
        result = callback(self)
        self.collection.pre_image = {
            "_id": "c-1",
            "attributes": [
                {"attr_name": "existing", "attr_value": "one"},
                {"attr_name": "concurrent", "attr_value": "two"},
            ],
        }
        result = callback(self)
        return result


class _AttributeFakeClient:
    def __init__(self, collection):
        self.collection = collection
        self.session = _AttributeFakeSession(collection)

    def start_session(self):
        return self.session


class _AttributeFakeDatabase:
    def __init__(self):
        self.name = TARGET_DB
        self.collection = _AttributeFakeCollection()
        self.client = _AttributeFakeClient(self.collection)

    def __getitem__(self, _collection_name):
        return self.collection


def test_derive_on_insert_mirrors_trigger():
    derived = derive_on_insert({"_id": "c-1", "cust_name": "otter works"})
    assert derived["cust_name_upper"] == "OTTER WORKS"
    assert derived["row_version_no"] == 1
    assert derived["ns"] == NS_VALUE
    assert isinstance(derived["cust_seq_no"], Int64)


def test_derive_on_insert_null_name_stays_null():
    derived = derive_on_insert({"_id": "c-2", "cust_name": None})
    assert derived["cust_name_upper"] is None


def test_derive_on_insert_preserves_supplied_sequence_and_version():
    derived = derive_on_insert(
        {"_id": "c-3", "cust_name": "a", "cust_seq_no": Int64(42), "row_version_no": 7}
    )
    assert derived["cust_seq_no"] == Int64(42)
    assert derived["row_version_no"] == 7


def test_derive_on_insert_generates_id_when_absent():
    derived = derive_on_insert({"cust_name": "a"})
    assert isinstance(derived["_id"], str) and derived["_id"]


def test_app_cust_seq_no_is_monotonic_long():
    first = app_cust_seq_no()
    second = app_cust_seq_no()
    assert isinstance(first, Int64)
    assert second >= first


def test_hist_dt_string_matches_legacy_format():
    now = datetime(2026, 9, 1, 5, 14, 33, tzinfo=timezone.utc)
    assert hist_dt_string(now) == "01-SEP-26 05:14:33"


def test_history_doc_copies_every_mapped_field():
    fields = history_fields()
    assert len(fields) == 157
    old_doc = {"_id": "c-9", "cust_name": "a", "attributes": [{"attr_name": "x"}]}
    now = datetime(2026, 9, 1, 5, 14, 33, tzinfo=timezone.utc)
    document = history_doc(old_doc, "UPD", now)
    assert set(document) == set(fields) | {"_id", "ns"}
    assert isinstance(document["_id"], ObjectId)
    assert document["cust_id"] == "c-9"
    assert document["hist_op"] == "UPD"
    assert document["hist_dt"] == "01-SEP-26 05:14:33"
    assert document["ns"] == NS_VALUE
    assert "attributes" not in document
    assert document["cust_name"] == "a"
    assert document["updated_dt"] is None


def test_history_doc_rejects_unknown_op():
    with pytest.raises(ValueError):
        history_doc({"_id": "c-9"}, "INS", datetime(2026, 9, 1, tzinfo=timezone.utc))


def test_history_fields_match_the_approved_spec():
    spec = json.loads((REPO_ROOT / ".migration/03_mapping_spec.json").read_text())
    entry = next(
        item for item in spec["collections"] if item["collection"] == "customer_master_hist"
    )
    assert history_fields() == [field["target"] for field in entry["fields"]]


def test_next_attribute_is_keyed_by_attr_name():
    element = next_attribute([], "TIER", "GOLD", "STR", "01-SEP-26")
    assert element == {
        "attr_name": "TIER",
        "attr_value": "GOLD",
        "attr_type": "STR",
        "created_dt": "01-SEP-26",
    }
    assert "eav_id" not in element


def test_next_attribute_preserves_migrated_eav_id():
    existing = [
        {"eav_id": Int64(11), "attr_name": "TIER"},
        {"eav_id": Int64(12), "attr_name": "OTHER"},
    ]
    element = next_attribute(existing, "TIER", "SILVER", "STR", "01-SEP-26")
    assert element["eav_id"] == Int64(11)
    assert element["attr_value"] == "SILVER"


def test_put_attribute_retries_with_fresh_pre_image():
    db = _AttributeFakeDatabase()
    path = CustomerWritePath(db)

    element = path.put_attribute("c-1", "requested", "three", "STR", "01-SEP-26")

    session = db.client.session
    assert session.with_transaction_calls == 1
    assert db.collection.find_sessions == [session, session]
    assert db.collection.update_sessions == [session, session]
    assert element["attr_name"] == "requested"
    committed = db.collection.updates[-1]["$set"]["attributes"]
    assert {item["attr_name"] for item in committed} == {
        "existing",
        "concurrent",
        "requested",
    }


def test_write_path_refuses_wrong_database():
    with pytest.raises(ValueError):
        CustomerWritePath(_FakeDatabase("ow_tp_mongodb_032752_quarantine"))
    assert CustomerWritePath(_FakeDatabase(TARGET_DB)).db.name == TARGET_DB
