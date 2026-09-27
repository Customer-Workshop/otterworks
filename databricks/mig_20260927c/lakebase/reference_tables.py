"""Column map shared by extract_reference.py and load_reference.py (run 20260927c, wave 0).

Mirrors .migration/units/lakebase_scaffold/mapping_spec.json: (oracle table, target table,
[(source column, target column)]) in the spec's column order; usage_events last so its FK to
tenants is satisfied at load time.
"""
from __future__ import annotations

SOURCE_SCHEMA = "OW_BILLING"
TARGET_SCHEMA = "billing"
TARGET_DATABASE = "ow_tp"

TABLES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("CODES", "codes", [("CODE_TYPE", "code_type"), ("CODE_VAL", "code_val"), ("CODE_DESC", "code_desc")]),
    ("PLANS", "plans", [("ID", "id"), ("CODE", "code"), ("TIER_CD", "tier_cd"), ("MONTHLY_FEE", "monthly_fee"),
                        ("INCLUDED_UNITS", "included_units"), ("OVERAGE_RATE", "overage_rate"),
                        ("ACTIVE_YN", "active_yn")]),
    ("TENANTS", "tenants", [("ID", "id"), ("NAME", "name"), ("TAX_EXEMPT_YN", "tax_exempt_yn"),
                            ("STATUS_CD", "status_cd")]),
    ("USAGE_EVENTS", "usage_events", [("ID", "id"), ("TENANT_ID", "tenant_id"), ("OCCURRED_AT", "occurred_at"),
                                      ("UNITS", "units"), ("KIND_CD", "kind_cd")]),
]
CHAR1_COLUMNS = {"ACTIVE_YN", "TAX_EXEMPT_YN"}
