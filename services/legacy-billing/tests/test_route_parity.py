import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app import app


DOCUMENTED_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/plans"),
    ("GET", "/plans/<tenant_id>/entitlement"),
    ("POST", "/plans/<tenant_id>/change"),
    ("POST", "/api/rating/finalize"),
    ("POST", "/api/rating/preview"),
    ("GET", "/api/invoices/<tenant_id>/preview"),
    ("POST", "/api/invoices/<tenant_id>/issue"),
    ("GET", "/api/invoices/<invoice_id>/lines"),
    ("GET", "/api/dunning/overdue"),
    ("POST", "/api/dunning/schedule"),
    ("POST", "/api/dunning/suspend"),
    ("GET", "/api/reports/month-end"),
    ("GET", "/api/reports/reconciliation"),
    ("GET", "/api/reports/finance"),
    ("GET", "/api/v1/billing/plans"),
    ("GET", "/api/v1/billing/me"),
    ("GET", "/api/v1/billing/entitlement"),
    ("POST", "/api/v1/billing/plan-change"),
    ("GET", "/api/v1/billing/usage"),
    ("GET", "/api/v1/billing/invoices"),
    ("GET", "/api/v1/billing/invoices/<invoice_id>/lines"),
    ("GET", "/api/v1/billing/customer"),
    ("GET", "/api/v1/billing/admin/overdue"),
    ("GET", "/api/v1/billing/admin/dunning"),
    ("POST", "/internal/usage/events"),
}


def test_flask_route_map_matches_documented_routes():
    actual = {
        (method, rule.rule)
        for rule in app.url_map.iter_rules()
        if not rule.rule.startswith("/static/")
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    assert actual == DOCUMENTED_ROUTES
