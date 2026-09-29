"""Differential parity: the Mongo backend against the Oracle backend.

Every read route and every write operation in parity_cases is replayed through
the Flask app with BILLING_BACKEND=mongo on a freshly loaded mongo-billing-fixture
and compared with the Oracle responses recorded from a scratch copy of the
synthetic Oracle fixture (fixtures/oracle_parity_golden.json).

With U4_PARITY_ORACLE=1 and ORACLE_PORT pointing at a scratch Oracle fixture the
same cases are replayed live against both backends instead of the recording.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("pymongo")
if not os.getenv("BILLING_MONGO_URI") or not os.getenv("OW_TP_MMP_FIXTURE_URI"):
    pytest.skip("BILLING_MONGO_URI and OW_TP_MMP_FIXTURE_URI select the Mongo fixture", allow_module_level=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))

import parity_cases
from app import app

SEED = HERE.parent / "migration" / "U4-app-backend" / "seed.py"
LIVE_ORACLE = os.getenv("U4_PARITY_ORACLE") == "1"


def _seed_module():
    spec = importlib.util.spec_from_file_location("u4_seed", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reload_fixture():
    seed = _seed_module()
    return seed.load(seed._fixture_uri())


@pytest.fixture(scope="module")
def backends_env():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("USAGE_INTERNAL_TOKEN", parity_cases.INTERNAL_TOKEN)
        patch.delenv("BILLING_READONLY", raising=False)
        yield patch


def _replay(patch, backend, cases):
    patch.setenv("BILLING_BACKEND", backend)
    return parity_cases.replay(app.test_client(), cases)


def _expected(patch, group, cases):
    if LIVE_ORACLE:
        return _replay(patch, "oracle", cases)
    return parity_cases.load_golden()[group]


def _assert_same(expected, actual):
    assert set(expected) == set(actual)
    mismatched = [name for name in expected if expected[name] != actual[name]]
    assert not mismatched, {name: {"oracle": expected[name], "mongo": actual[name]} for name in mismatched}


def test_mongo_serves_oracle_responses_for_every_read_and_write(backends_env):
    counts = _reload_fixture()
    assert counts["customers"] == 25001 and counts["invoices"] == 18750

    expected_reads = _expected(backends_env, "read", parity_cases.READ_CASES)
    _assert_same(expected_reads, _replay(backends_env, "mongo", parity_cases.READ_CASES))

    expected_writes = _expected(backends_env, "write", parity_cases.WRITE_CASES)
    _assert_same(expected_writes, _replay(backends_env, "mongo", parity_cases.WRITE_CASES))


def test_parity_cases_cover_the_brief(backends_env):
    golden = parity_cases.load_golden()
    reads = golden["read"]
    attrs = [a["attr_name"].upper() for a in reads["facade_customer_admin_dup_attrs"]["body"]["attributes"]]
    assert len(attrs) != len(set(attrs))
    assert reads["facade_customer_casey"]["body"]["cust_name"].startswith("Casey")
    assert len(reads["invoice_lines_multi"]["body"]) > 1
    assert reads["report_month_end_admin"]["status"] == 200
    assert reads["report_month_end_admin"]["body"]["by_status"]
    writes = golden["write"]
    assert writes["issue_t4"]["status"] in (200, 302)
    assert writes["usage_event_duplicate"]["body"] == {"status": "duplicate"}


def test_reports_label_the_mongo_source(backends_env):
    backends_env.setenv("BILLING_BACKEND", "mongo")
    body = app.test_client().get("/api/reports/reconciliation?ns=mmpfix").get_json()
    assert body["source"]["engine"] == "mongodb"


def test_readonly_skips_provisioning_and_audit(backends_env, monkeypatch):
    from backends import mongo

    monkeypatch.setenv("BILLING_BACKEND", "mongo")
    monkeypatch.setenv("BILLING_READONLY", "1")
    tenant = "b4000000-0000-0000-0000-00000000r0n1"
    audit_before = mongo.db.billing_audit_log.count_documents({})
    response = app.test_client().get("/api/v1/billing/plans", headers={"X-User-ID": tenant})
    assert response.status_code == 200
    assert mongo.db.tenants.find_one({"_id": tenant}) is None
    assert mongo.db.billing_audit_log.count_documents({}) == audit_before


def test_pymongo_errors_map_to_unavailable(backends_env, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    from backends import mongo

    def down(*args, **kwargs):
        raise ServerSelectionTimeoutError("fixture down")

    monkeypatch.setenv("BILLING_BACKEND", "mongo")
    monkeypatch.setattr(mongo, "list_plans", down)
    response = app.test_client().get("/api/v1/billing/plans", headers={"X-User-ID": parity_cases.T1})
    assert response.status_code == 503
    assert response.get_json()["error"] == "legacy estate unavailable"
