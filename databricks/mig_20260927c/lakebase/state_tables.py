"""Column map shared by extract_state.py and load_state.py (run 20260927c, wave 1).

The eight unit-owned state tables in FK order: parents before children so a single TRUNCATE
of all eight and a sequential COPY satisfies referential integrity at load time.
"""
from __future__ import annotations

SOURCE_SCHEMA = "OW_BILLING"
TARGET_SCHEMA = "billing"
TARGET_DATABASE = "ow_tp"

TABLES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("SUBSCRIPTIONS", "subscriptions", [("ID", "id"), ("TENANT_ID", "tenant_id"), ("PLAN_ID", "plan_id"),
                                      ("STARTS_ON", "starts_on"), ("ENDS_ON", "ends_on"),
                                      ("STATUS_CD", "status_cd"), ("SUSPENDED_ON", "suspended_on")]),
    ("SUBSCRIPTIONS_HIST", "subscriptions_hist", [("HIST_ID", "hist_id"), ("HIST_DT", "hist_dt"),
                                                ("HIST_OP", "hist_op"), ("ID", "id"), ("TENANT_ID", "tenant_id"),
                                                ("PLAN_ID", "plan_id"), ("STARTS_ON", "starts_on"),
                                                ("ENDS_ON", "ends_on"), ("STATUS_CD", "status_cd"),
                                                ("SUSPENDED_ON", "suspended_on")]),
    ("RATING_PERIODS", "rating_periods", [("ID", "id"), ("TENANT_ID", "tenant_id"),
                                          ("PERIOD_START", "period_start"), ("PERIOD_END", "period_end")]),
    ("RATING_RESULTS", "rating_results", [("ID", "id"), ("PERIOD_ID", "period_id"),
                                          ("SUBSCRIPTION_ID", "subscription_id"), ("USED_UNITS", "used_units"),
                                          ("QUOTA_UNITS", "quota_units"), ("ROLLOVER_UNITS", "rollover_units"),
                                          ("BILLABLE_UNITS", "billable_units"), ("OVERAGE_AMOUNT", "overage_amount"),
                                          ("CREATED_AT", "created_at")]),
    ("INVOICES", "invoices", [("ID", "id"), ("TENANT_ID", "tenant_id"), ("PERIOD_ID", "period_id"),
                              ("ISSUED_AT", "issued_at"), ("SUBTOTAL", "subtotal"), ("TAX", "tax"),
                              ("TOTAL", "total"), ("STATUS_CD", "status_cd")]),
    ("INVOICE_LINES", "invoice_lines", [("ID", "id"), ("INVOICE_ID", "invoice_id"), ("LINE_NO", "line_no"),
                                        ("LINE_TYPE", "line_type"), ("DESCRIPTION", "description"),
                                        ("AMOUNT", "amount")]),
    ("CREDIT_NOTES", "credit_notes", [("ID", "id"), ("TENANT_ID", "tenant_id"), ("ISSUED_ON", "issued_on"),
                                      ("AMOUNT", "amount"), ("REMAINING_AMOUNT", "remaining_amount")]),
    ("BILLING_AUDIT_LOG", "billing_audit_log", [("LOG_ID", "log_id"), ("LOGGED_AT", "logged_at"),
                                                ("MODULE", "module"), ("MESSAGE", "message")]),
]
CHAR1_COLUMNS: set[str] = set()
