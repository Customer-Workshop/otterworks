"""Offline contract tests for the MongoDB PKG_OW_UTIL port."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from bson import ObjectId
from bson.errors import InvalidDocument
from pymongo.errors import PyMongoError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import ow_util


class _CodesCollection:
    def __init__(self, documents):
        self.documents = documents

    def find_one(self, query):
        return self.documents.get(query["_id"])


class _FakeDb:
    def __init__(self, codes=None, audit=None):
        self.collections = {
            "codes": _CodesCollection(codes or {}),
            "billing_audit_log": audit,
        }

    def __getitem__(self, name):
        return self.collections[name]

    def get_collection(self, name, write_concern=None):
        return self.collections[name]


class _AuditCollection:
    def __init__(self):
        self.documents = []
        self.calls = []
        self.index_calls = []
        self.write_concern = type("_Concern", (), {"document": {"w": "majority"}})()

    def insert_one(self, document, **kwargs):
        self.calls.append((document, kwargs))
        self.documents.append(document)

    def create_index(self, keys, **kwargs):
        self.index_calls.append((keys, kwargs))
        return kwargs["name"]

    def list_indexes(self):
        return iter(
            [
                {"name": "_id_", "key": {"_id": 1}},
                {
                    "name": ow_util.AUDIT_TTL_INDEX_NAME,
                    "key": {"logged_at": 1},
                    "expireAfterSeconds": ow_util.AUDIT_TTL_SECONDS,
                },
            ]
        )


def _jsonable(value):
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    return value


def test_transcript_replay():
    transcript = Path(__file__).resolve().parents[3] / ".migration/recon/U7/util_transcript.json"
    if not transcript.exists():
        pytest.skip("U7 transcript is not available")
    recorded = json.loads(transcript.read_text())
    codes = {}
    for operation in recorded["ops"]:
        if operation["fn"] == "f_code_desc" and operation["label"].startswith("hit_"):
            args = operation["args"]
            codes[f"{args['p_type']}#{int(args['p_val'])}"] = {
                "code_desc": operation["value"]
            }
    db = _FakeDb(codes=codes)
    for operation in recorded["ops"]:
        args = operation["args"]
        if operation["fn"] == "f_md5_uuid":
            function = ow_util.md5_uuid
            call_args = (args["p_input"],)
        elif operation["fn"] == "f_code_desc":
            function = ow_util.code_desc
            call_args = (db, args["p_type"], args["p_val"])
        elif operation["fn"] == "f_dt2str":
            function = ow_util.dt2str
            raw = args["p_dt"]
            call_args = (datetime.fromisoformat(raw["__datetime__"]) if raw else None,)
        elif operation["fn"] == "f_str2dt":
            function = ow_util.str2dt
            call_args = (args["p_str"],)
        else:
            raise AssertionError(f"unknown transcript function {operation['fn']}")
        if "error" in operation:
            with pytest.raises(Exception):
                function(*call_args)
        else:
            assert _jsonable(function(*call_args)) == operation["value"], operation["label"]


def test_log_msg_accepts_source_dropped_lengths_as_declared_divergence():
    # Declared divergence: the port writes module lengths the BYTE-limited source drops.
    ascii_collection = _AuditCollection()
    ascii_util = ow_util.OwUtil(_FakeDb(audit=ascii_collection))
    assert ascii_util.log_msg("M" * 40, "message") is True
    assert len(ascii_collection.documents) == 1

    multibyte_collection = _AuditCollection()
    multibyte_util = ow_util.OwUtil(_FakeDb(audit=multibyte_collection))
    assert multibyte_util.log_msg("ö" * 30, "message") is True
    assert len(multibyte_collection.documents) == 1


def test_log_msg_truncates_and_uses_independent_insert():
    collection = _AuditCollection()
    util = ow_util.OwUtil(_FakeDb(audit=collection))
    module = "M" * 40
    message = "m" * 5000

    assert util.log_msg(module, message) is True
    document, kwargs = collection.calls[0]
    assert kwargs.get("session") is None
    assert len(document["module"]) == 30
    assert len(document["message"]) == 4000
    assert document["ns"] == ow_util.NS_VALUE
    assert isinstance(document["_id"], ObjectId)
    assert document["logged_at"].microsecond == 0
    assert util.last_module == module


def test_log_msg_swallows_argument_failure_before_insert():
    collection = _AuditCollection()
    util = ow_util.OwUtil(_FakeDb(audit=collection))

    assert util.log_msg(123, "message") is False
    assert collection.documents == []
    assert util.last_module == 123


def test_log_msg_swallows_bson_encoding_failure():
    class _InvalidDocumentCollection(_AuditCollection):
        def insert_one(self, document, **kwargs):
            raise InvalidDocument("cannot encode document")

    collection = _InvalidDocumentCollection()
    util = ow_util.OwUtil(_FakeDb(audit=collection))

    assert util.log_msg("module", "message") is False
    assert collection.documents == []
    assert util.last_module == "module"


def test_log_msg_swallowing_driver_error():
    class _FailingCollection(_AuditCollection):
        def insert_one(self, document, **kwargs):
            raise PyMongoError("write failed")

    util = ow_util.OwUtil(_FakeDb(audit=_FailingCollection()))
    module = "failure-module"
    assert util.log_msg(module, "message") is False
    assert util.last_module == module


def test_f_md5_uuid_counts_success_and_failure():
    util = ow_util.OwUtil(_FakeDb(audit=_AuditCollection()))
    assert util.f_md5_uuid("ok")
    with pytest.raises(ValueError, match="ORA-06502.*raw variable length too long"):
        util.f_md5_uuid("x" * 2001)
    assert util.call_count == 2


def test_ensure_audit_indexes_requests_ttl():
    collection = _AuditCollection()
    names = ow_util.ensure_audit_indexes(_FakeDb(audit=collection))
    assert names == ["_id_", ow_util.AUDIT_TTL_INDEX_NAME]
    assert collection.index_calls == [
        (
            [("logged_at", 1)],
            {
                "expireAfterSeconds": 7776000,
                "name": ow_util.AUDIT_TTL_INDEX_NAME,
            },
        )
    ]
