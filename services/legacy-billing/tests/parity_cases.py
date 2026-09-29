"""Route cases replayed against the Oracle fixture and the Mongo fixture.

Both backends are driven through the Flask app exactly as clients call it;
responses are compared after removing the only fields allowed to differ
(report source label, wall-clock stamps, the health backend name).
"""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "oracle_parity_golden.json"
INTERNAL_TOKEN = "parity-internal-token"

T1 = "00000000-0000-0000-0000-000000000001"
T2 = "00000000-0000-0000-0000-000000000002"
T3 = "00000000-0000-0000-0000-000000000003"
T4 = "00000000-0000-0000-0000-000000000004"
T5 = "00000000-0000-0000-0000-000000000005"
T9 = "00000000-0000-0000-0000-000000000009"
ADMIN = "a0000000-0000-0000-0000-000000000001"
CASEY = "c1d4ed03-8e72-5b1d-7544-d92f58aa582f"
MMPFIX = "5cfa0a67-3708-c9e4-fe22-0f031d531c0d"
NEW_TENANT = "b4000000-0000-0000-0000-00000000u4ab"
MULTI_LINE_INVOICE = "60000000-0000-0000-0000-000000000001"
GROWTH = "10000000-0000-0000-0000-000000000002"
SCALE = "10000000-0000-0000-0000-000000000003"


def _user(tenant, admin=False, email=None):
    headers = {"X-User-ID": tenant}
    if admin:
        headers["X-User-Roles"] = "USER,ADMIN"
    if email:
        headers["X-User-Email"] = email
    return headers


def _get(name, path, headers=None):
    return {"name": name, "method": "GET", "path": path, "headers": headers or {}}


def _post(name, path, headers=None, json_body=None, form=None):
    return {
        "name": name,
        "method": "POST",
        "path": path,
        "headers": headers or {},
        "json": json_body,
        "form": form,
    }


READ_CASES = [
    _get("health", "/health"),
    _get("index_page", "/"),
    _get("plans", "/plans"),
    _get("entitlement_t1", f"/plans/{T1}/entitlement?on=2026-02-28"),
    _get("entitlement_suspended_t2", f"/plans/{T2}/entitlement?on=2026-02-15"),
    _get("entitlement_before_start", f"/plans/{T1}/entitlement?on=2025-12-31"),
    _get("entitlement_unknown", "/plans/ffffffff-0000-0000-0000-000000000000/entitlement?on=2026-02-28"),
    _post("rating_preview_t4", "/api/rating/preview",
          json_body={"tenant_id": T4, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("rating_preview_mmpfix", "/api/rating/preview",
          json_body={"tenant_id": MMPFIX, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _get("invoice_preview_t4", f"/api/invoices/{T4}/preview"),
    _get("invoice_preview_t9", f"/api/invoices/{T9}/preview?period_start=2026-02-01&period_end=2026-02-28"),
    _get("invoice_preview_mmpfix", f"/api/invoices/{MMPFIX}/preview"),
    _get("invoice_lines_multi", f"/api/invoices/{MULTI_LINE_INVOICE}/lines"),
    _get("invoice_lines_missing", "/api/invoices/60000000-0000-0000-0000-0000000000ff/lines"),
    _get("overdue_feb", "/api/dunning/overdue?as_of=2026-02-28"),
    _get("overdue_mar", "/api/dunning/overdue?as_of=2026-03-31"),
    _get("facade_plans", "/api/v1/billing/plans", _user(T1)),
    _get("facade_me_t2", "/api/v1/billing/me?on=2026-02-15", _user(T2)),
    _get("facade_me_admin", "/api/v1/billing/me?on=2026-02-15", _user(ADMIN)),
    _get("facade_entitlement", "/api/v1/billing/entitlement?on=2026-02-20", _user(T5)),
    _get("facade_usage_t4", "/api/v1/billing/usage?period_start=2026-02-01&period_end=2026-02-28", _user(T4)),
    _get("facade_usage_mmpfix", "/api/v1/billing/usage?period_start=2026-02-01&period_end=2026-02-28", _user(MMPFIX)),
    _get("facade_invoices_t2", "/api/v1/billing/invoices", _user(T2)),
    _get("facade_invoice_lines_owned", f"/api/v1/billing/invoices/{MULTI_LINE_INVOICE}/lines", _user(T2)),
    _get("facade_invoice_lines_foreign", f"/api/v1/billing/invoices/{MULTI_LINE_INVOICE}/lines", _user(T5)),
    _get("facade_customer_admin_dup_attrs", "/api/v1/billing/customer", _user(ADMIN)),
    _get("facade_customer_casey", "/api/v1/billing/customer", _user(CASEY)),
    _get("facade_customer_missing", "/api/v1/billing/customer", _user(T1)),
    _get("facade_admin_overdue", "/api/v1/billing/admin/overdue?as_of=2026-03-31", _user(ADMIN, admin=True)),
    _get("facade_admin_overdue_forbidden", "/api/v1/billing/admin/overdue?as_of=2026-03-31", _user(T1)),
    _get("facade_admin_dunning", "/api/v1/billing/admin/dunning?as_of=2026-03-31", _user(ADMIN, admin=True)),
    _get("report_month_end", "/api/reports/month-end?ns=mmpfix"),
    _get("report_month_end_admin", "/api/v1/billing/admin/reports/month-end?ns=mmpfix", _user(ADMIN, admin=True)),
    _get("report_month_end_empty_ns", "/api/reports/month-end?ns=nosuchns"),
    _get("report_reconciliation", "/api/reports/reconciliation?ns=mmpfix"),
    _get("report_reconciliation_admin", "/api/v1/billing/admin/reports/reconciliation?ns=mmpfix", _user(ADMIN, admin=True)),
]

WRITE_CASES = [
    _post("finalize_t4", "/api/rating/finalize",
          json_body={"tenant_id": T4, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("finalize_t4_again", "/api/rating/finalize",
          json_body={"tenant_id": T4, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("rating_after_finalize", "/api/rating/preview",
          json_body={"tenant_id": T4, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("issue_t4", f"/api/invoices/{T4}/issue", form={"period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("issue_t4_again", f"/api/invoices/{T4}/issue", form={"period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("issue_t9", f"/api/invoices/{T9}/issue", form={"period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _post("issue_t3", f"/api/invoices/{T3}/issue", form={"period_start": "2026-02-01", "period_end": "2026-02-28"}),
    _get("invoices_t4_after_issue", "/api/v1/billing/invoices", _user(T4)),
    _get("invoices_t9_after_issue", "/api/v1/billing/invoices", _user(T9)),
    _get("invoices_t3_after_issue", "/api/v1/billing/invoices", _user(T3)),
    _get("preview_t4_after_credit", f"/api/invoices/{T4}/preview"),
    _post("schedule_dunning", "/api/dunning/schedule", form={"as_of": "2026-03-20"}),
    _post("schedule_dunning_again", "/api/dunning/schedule", form={"as_of": "2026-03-20"}),
    _get("dunning_after_schedule", "/api/v1/billing/admin/dunning?as_of=2026-12-31", _user(ADMIN, admin=True)),
    _post("suspend_overdue", "/api/dunning/suspend", form={"as_of": "2026-04-30"}),
    _post("suspend_overdue_again", "/api/dunning/suspend", form={"as_of": "2026-04-30"}),
    _get("me_t5_after_suspend", "/api/v1/billing/me?on=2026-04-30", _user(T5)),
    _get("overdue_after_suspend", "/api/dunning/overdue?as_of=2026-04-30"),
    _post("plan_change_form", f"/plans/{T1}/change", form={"plan_id": GROWTH, "effective_on": "2099-01-01"}),
    _get("entitlement_after_form_change", f"/plans/{T1}/entitlement?on=2099-01-01"),
    _post("plan_change_same_day", f"/plans/{T1}/change", form={"plan_id": SCALE, "effective_on": "2099-01-01"}),
    _get("entitlement_after_same_day", f"/plans/{T1}/entitlement?on=2099-01-01"),
    _post("facade_plan_change", "/api/v1/billing/plan-change", _user(T2),
          json_body={"plan_id": SCALE, "effective_on": "2099-03-01"}),
    _post("facade_plan_change_unknown_plan", "/api/v1/billing/plan-change", _user(T2),
          json_body={"plan_id": "nope", "effective_on": "2099-03-01"}),
    _post("facade_plan_change_new_tenant", "/api/v1/billing/plan-change", _user(NEW_TENANT, email="new.tenant@example.test"),
          json_body={"plan_id": GROWTH, "effective_on": "2099-04-01"}),
    _get("facade_me_new_tenant", "/api/v1/billing/me?on=2099-04-01", _user(NEW_TENANT)),
    _post("usage_event_record", "/internal/usage/events", {"X-Internal-Token": INTERNAL_TOKEN},
          json_body={"tenant_id": T4, "event_id": "9a000000-0000-4000-8000-000000000001",
                     "kind": "compute", "units": 250, "occurred_at": "2026-02-14T09:30:59.987Z"}),
    _post("usage_event_duplicate", "/internal/usage/events", {"X-Internal-Token": INTERNAL_TOKEN},
          json_body={"tenant_id": T4, "event_id": "9a000000-0000-4000-8000-000000000001",
                     "kind": "compute", "units": 250, "occurred_at": "2026-02-14T09:30:59.987Z"}),
    _post("usage_event_new_tenant", "/internal/usage/events", {"X-Internal-Token": INTERNAL_TOKEN},
          json_body={"tenant_id": "b4000000-0000-0000-0000-00000000u4cd", "event_id": "9a000000-0000-4000-8000-000000000002",
                     "kind": "api", "units": 7, "occurred_at": "2026-02-15T00:00:00Z", "email": "ingest@example.test"}),
    _get("usage_after_event", "/api/v1/billing/usage?period_start=2026-02-01&period_end=2026-02-28", _user(T4)),
    _post("rating_after_event", "/api/rating/preview",
          json_body={"tenant_id": T4, "period_start": "2026-02-01", "period_end": "2026-02-28"}),
]

_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")


def _normalize(value, today):
    if isinstance(value, dict):
        return {key: _normalize(item, today) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item, today) for item in value]
    if isinstance(value, str) and value == today:
        return "<today>"
    return value


def replay(client, cases):
    today = date.today().isoformat()
    results = {}
    for case in cases:
        kwargs = {"headers": case["headers"]}
        if case.get("json") is not None:
            kwargs["json"] = case["json"]
        if case.get("form") is not None:
            kwargs["data"] = case["form"]
        response = client.open(case["path"], method=case["method"], **kwargs)
        body = response.get_json(silent=True)
        if body is None:
            body = response.get_data(as_text=True)
        if isinstance(body, dict):
            if "generated_at" in body and _STAMP.match(str(body["generated_at"])):
                body["generated_at"] = "<stamp>"
            if isinstance(body.get("source"), dict) and "engine" in body["source"]:
                body["source"] = "<engine source>"
            if case["name"] == "health":
                body["backend"] = "<backend>"
        results[case["name"]] = {
            "status": response.status_code,
            "location": response.headers.get("Location"),
            "body": _normalize(body, today),
        }
    return results


def load_golden():
    return json.loads(GOLDEN_PATH.read_text())


def write_golden(golden):
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    golden = {
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "synthetic Oracle fixture (.migration/fixtures/oracle-mmpfix.manifest.json), scratch copy",
        **golden,
    }
    GOLDEN_PATH.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")


def record(client):
    return {"read": replay(client, READ_CASES), "write": replay(client, WRITE_CASES)}
