"""Declared surface of the bronze_wide unit.

The OW_BILLING billing estate exposes four wide/denormalised tables that the
nightly ksh/Perl batch chain writes to.  Everything in this module is the
*declared* shape of those tables; `source_schema.json` next to this file is the
committed column inventory (name, Oracle type, declared width) that the
extractor re-verifies against the live dictionary on every run, so that an
added or widened source column fails the unit instead of being silently
dropped.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent
UNIT = "bronze_wide"
CATALOG = "ow_tp"
SCHEMA = "bronze"
QUARANTINE_TABLE = "quarantine_bronze_wide"

# source table -> (target table, natural key column)
TABLES: dict[str, tuple[str, str]] = {
    "CUSTOMER_MASTER": ("customer_master", "CUST_ID"),
    "ENTITY_ATTR_VALUE": ("entity_attr_value", "EAV_ID"),
    "INVOICE_LINE": ("invoice_line", "LINE_ID"),
    "INVOICE_HEADER": ("invoice_header", "INVOICE_ID"),
}

# VARCHAR2(9) columns that carry a DD-MON-YY free-text date (D-05/D-06),
# including the UDF_DT_nn user-defined slots the batch chain writes.
DATE_TEXT_WIDTH = 9
DATE_TEXT_MARKER = "_DT"

# Multi-value-in-one-column surfaces (ANOM-GL-ACCT-CSV).  Values are carried
# verbatim; only a token count is derived alongside them.
CSV_COLUMNS: dict[str, list[str]] = {
    "CUSTOMER_MASTER": ["RELATED_ACCT_IDS", "CHILD_ACCT_IDS", "PROMO_CODES_CSV"],
    "INVOICE_LINE": ["GL_ACCT_CSV"],
}

# Columns that carry customer-identifying cleartext.  Values are landed as-is;
# restriction is a Unity Catalog column mask (ACC-PII-MASK).
PII_COLUMNS: dict[str, list[str]] = {
    "CUSTOMER_MASTER": [
        "CUST_NAME", "CUST_NAME_UPPER", "LEGAL_NAME", "DBA_NAME",
        "ADDR_LINE_1", "ADDR_LINE_2", "ADDR_LINE_3", "ADDR_LINE_4",
        "ADDR_LINE_5", "ADDR_LINE_6", "CITY", "ZIP",
        "MAIL_ADDR_LINE_1", "MAIL_ADDR_LINE_2", "MAIL_ADDR_LINE_3",
        "MAIL_ADDR_LINE_4", "MAIL_ADDR_LINE_5", "MAIL_ADDR_LINE_6",
        "MAIL_CITY", "MAIL_ZIP",
        "PHONE1", "PHONE2", "PHONE3", "PHONE4", "FAX",
        "EMAIL_1", "EMAIL_2", "EMAIL_3", "CONTACT_NOTES",
    ],
    "INVOICE_LINE": ["CUST_NAME"],
}

# D-15: CUST_SEQ_NO is assigned by a source trigger from a sequence and is not
# value-comparable across environments; it is landed but excluded from the
# column-by-column parity comparison.
NON_COMPARABLE_COLUMNS: dict[str, list[str]] = {
    "CUSTOMER_MASTER": ["CUST_SEQ_NO"],
}


def require_env(name: str) -> str:
    """Read a required credential/connection value from the environment.

    No default: a run against a misconfigured environment must fail rather than
    silently fall back to a guessable account.
    """
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"{name} is required (OW_BILLING credentials come from the environment)"
        )
    return value


def load_source_schema() -> dict[str, list[dict]]:
    return json.loads((SPEC_DIR / "source_schema.json").read_text())


def date_text_columns(columns: list[dict]) -> list[str]:
    return [
        c["name"] for c in columns
        if c["type"] == "VARCHAR2" and c["length"] == DATE_TEXT_WIDTH
        and DATE_TEXT_MARKER in c["name"]
    ]


def money_columns(columns: list[dict]) -> list[str]:
    return [
        c["name"] for c in columns
        if c["type"] == "NUMBER" and c.get("scale") == 2
    ]
