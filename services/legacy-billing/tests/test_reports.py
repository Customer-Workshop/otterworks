"""Contract tests for the legacy month-end report endpoints.

Run from services/legacy-billing:
    uv run --with pytest --with flask==3.1.1 pytest tests/

Any backend serving the billing report page must satisfy this contract:
same paths, same JSON shape, only source.engine and reconciliation checks
differ. See docs/tech-partnerships/billing-report-contract.md.
"""

import sys
from pathlib import Path
from shutil import copyfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import reports as reports_module
from flask import Flask
from reports import (
    ns_batch_no,
    reports,
    shape_balances,
    shape_line_rows,
    shape_status_rows,
)


@pytest.fixture
def client(monkeypatch):
    fixtures = {
        reports_module.STATUS_SQL: [("ISSUED", 100, "12345.00"), ("PAID", 50, "999.00")],
        reports_module.LINE_SQL: [("ISSUED", "CHARGE", 400, "12000.00", "345.00", 100)],
        reports_module.BALANCES_SQL: [(25000, "1234567.00", "8901.00")],
    }
    monkeypatch.setattr(reports_module, "oracle_query", lambda sql, params: fixtures[sql])
    app = Flask(__name__)
    app.register_blueprint(reports)
    return app.test_client()


def test_ns_batch_no_matches_seed_derivation():
    # sha256("demo")[:8] % 90_000_000 + 1_000_000 — must equal the seeder's batch.
    import hashlib

    seed = int(hashlib.sha256(b"demo").hexdigest()[:8], 16)
    assert ns_batch_no("demo") == seed % 90_000_000 + 1_000_000
    assert 1_000_000 <= ns_batch_no("rehearsal1") < 91_000_000


def test_shapers():
    assert shape_status_rows([("PAID", 1, "2.00")]) == [
        {"status": "PAID", "invoice_count": 1, "header_total_amt": "2.00"}
    ]
    assert shape_line_rows([("PAID", "CHARGE", 3, "4.00", "5.00", 6)]) == [
        {
            "status": "PAID",
            "line_type": "CHARGE",
            "line_count": 3,
            "line_amount": "4.00",
            "line_tax": "5.00",
            "invoices_touched": 6,
        }
    ]
    assert shape_balances((7, "8.00", "9.00")) == {
        "customer_count": 7,
        "current_balance_total": "8.00",
        "past_due_total": "9.00",
    }


def test_month_end_contract(client):
    body = client.get("/api/reports/month-end?ns=demo").get_json()
    assert body["report"] == "month-end-finance"
    assert body["namespace"] == "demo"
    assert body["batch_no"] == ns_batch_no("demo")
    assert body["source"]["engine"] == "oracle"
    assert body["by_status"][0] == {
        "status": "ISSUED", "invoice_count": 100, "header_total_amt": "12345.00"
    }
    assert body["by_status_line_type"][0]["line_type"] == "CHARGE"
    assert "generated_at" in body


def test_admin_report_aliases_require_admin_and_match_legacy(client):
    assert client.get("/api/v1/billing/admin/reports/month-end").status_code == 403
    assert client.get("/api/v1/billing/admin/reports/reconciliation").status_code == 403
    assert client.get("/api/v1/billing/admin/reports/finance").status_code == 403
    headers = {"X-User-Roles": "ADMIN"}
    alias = client.get(
        "/api/v1/billing/admin/reports/month-end?ns=demo", headers=headers,
    ).get_json()
    legacy = client.get("/api/reports/month-end?ns=demo").get_json()
    assert alias == legacy


def test_reconciliation_contract(client):
    body = client.get("/api/reports/reconciliation?ns=demo").get_json()
    assert body["source"]["engine"] == "oracle"
    assert body["balances"] == {
        "customer_count": 25000,
        "current_balance_total": "1234567.00",
        "past_due_total": "8901.00",
    }
    assert body["status"] == "baseline"
    assert body["checks"] == []


def test_estate_offline_returns_503(client, monkeypatch):
    def boom(sql, params):
        raise RuntimeError("ORA-12541: no listener")

    monkeypatch.setattr(reports_module, "oracle_query", boom)
    response = client.get("/api/reports/month-end")
    assert response.status_code == 503
    assert response.get_json()["error"] == "legacy estate unavailable"


def test_finance_report_reads_namespace_batch_fixture(client, monkeypatch, tmp_path):
    report_dir = tmp_path / "reports" / "demo"
    report_dir.mkdir(parents=True)
    copyfile(
        Path(__file__).parent / "fixtures" / "finance_billing_20260228.csv",
        report_dir / "finance_billing_20260228.csv",
    )
    (report_dir / "finance_billing_20260228.xls").write_text("not a report")
    monkeypatch.setenv("FINANCE_REPORT_DIR", str(tmp_path / "reports"))
    response = client.get("/api/reports/finance?ns=demo")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ns"] == "demo"
    assert body["source"]["system"] == "CUSTBILL month-end batch"
    assert body["source"]["file"] == "finance_billing_20260228.csv"
    assert body["rows"][0] == {
        "currency": "USD",
        "record_type": "INVOICE",
        "record_count": 2,
        "total_amount": "25.00",
    }
    assert body["totals"] == {"record_count": 3, "total_amount": "30.00"}


def test_finance_report_missing_namespace_returns_404(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_REPORT_DIR", str(tmp_path))
    response = client.get("/api/reports/finance?ns=missing")
    assert response.status_code == 404
    assert response.get_json() == {
        "error": "no finance report for namespace",
        "detail": "run make tp-month-end NS=missing",
    }


def test_finance_report_over_size_limit_returns_413(client, monkeypatch, tmp_path):
    report_dir = tmp_path / "reports" / "demo"
    report_dir.mkdir(parents=True)
    report = report_dir / "finance_billing_20260228.csv"
    copyfile(
        Path(__file__).parent / "fixtures" / "finance_billing_20260228.csv",
        report,
    )
    monkeypatch.setenv("FINANCE_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("FINANCE_REPORT_MAX_BYTES", "1")
    response = client.get("/api/reports/finance?ns=demo")
    assert response.status_code == 413
    assert response.get_json() == {"error": "finance report too large"}
