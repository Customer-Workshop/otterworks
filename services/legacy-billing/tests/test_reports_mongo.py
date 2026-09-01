"""Contract tests for the MongoDB-backed balances path of the billing report.

Run from services/legacy-billing:
    uv run --with pytest --with flask==3.1.1 pytest tests/

No live MongoDB connection: the aggregation seam is monkeypatched. The Oracle
contract in test_reports.py stays the reference for the JSON shape.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import reports as reports_module
from flask import Flask
from reports import balances_backend, balances_pipeline, fm_amount, reports


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return iter(self.rows)


class _FakeClient:
    def __init__(self, collection):
        self.collection = collection
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _no_backend_env(monkeypatch):
    monkeypatch.delenv("BILLING_BALANCES_BACKEND", raising=False)
    monkeypatch.delenv("OW_BILLING_MONGO_URI", raising=False)


def _patch_collection(monkeypatch, rows):
    collection = _FakeCollection(rows)
    client = _FakeClient(collection)
    monkeypatch.setattr(reports_module, "mongo_connect", lambda: client)
    monkeypatch.setattr(reports_module, "_customers_collection", lambda _client: collection)
    return client, collection


def test_balances_pipeline_shape():
    assert balances_pipeline(85559852) == [
        {"$match": {"conversion_batch_no": 85559852}},
        {"$group": {"_id": None,
                    "customer_count": {"$sum": 1},
                    "current_balance_total": {"$sum": "$cur_bal_amt"},
                    "past_due_total": {"$sum": "$past_due_amt"}}},
    ]


def test_fm_amount_matches_oracle_rendering():
    from bson import Decimal128

    assert fm_amount(Decimal128("39799450.31")) == "39799450.31"
    assert fm_amount(Decimal("0")) == "0.00"
    assert fm_amount(Decimal("-1.005")) == "-1.01"
    assert fm_amount(None) is None
    assert fm_amount(7) == "7.00"


def test_mongo_balances_single_row(monkeypatch):
    from bson import Decimal128

    client, collection = _patch_collection(
        monkeypatch,
        [
            {
                "customer_count": 25000,
                "current_balance_total": Decimal128("39799450.31"),
                "past_due_total": Decimal128("7330214.66"),
            }
        ],
    )
    assert reports_module.mongo_balances(85559852) == [
        (25000, "39799450.31", "7330214.66")
    ]
    assert collection.pipelines == [balances_pipeline(85559852)]
    assert client.closed is True


def test_mongo_balances_empty_matches_oracle_nulls(monkeypatch):
    _patch_collection(monkeypatch, [])
    assert reports_module.mongo_balances(85559852) == [(0, None, None)]


def test_reconciliation_contract_on_mongodb(monkeypatch):
    monkeypatch.setattr(
        reports_module,
        "mongo_balances",
        lambda batch_no: [(25000, "39799450.31", "7330214.66")],
    )
    monkeypatch.setattr(reports_module, "balances_backend", lambda: "mongodb")
    app = Flask(__name__)
    app.register_blueprint(reports)
    body = app.test_client().get("/api/reports/reconciliation?ns=demo").get_json()
    assert body["source"]["engine"] == "mongodb"
    assert body["source"]["system"] == "ow_tp_mongodb_032752 (MongoDB Atlas)"
    assert body["balances"] == {
        "customer_count": 25000,
        "current_balance_total": "39799450.31",
        "past_due_total": "7330214.66",
    }
    assert body["status"] == "baseline"
    assert body["checks"] == []
    assert body["batch_no"] == reports_module.ns_batch_no("demo")


def test_balances_backend_resolution(monkeypatch):
    assert balances_backend() == "oracle"
    monkeypatch.setenv("OW_BILLING_MONGO_URI", "env-var-name-only")
    assert balances_backend() == "mongodb"
    monkeypatch.setenv("BILLING_BALANCES_BACKEND", "Oracle")
    assert balances_backend() == "oracle"
    monkeypatch.setenv("BILLING_BALANCES_BACKEND", "cassandra")
    with pytest.raises(ValueError):
        balances_backend()
