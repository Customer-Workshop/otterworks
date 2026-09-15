"""Wave 1 batch w1-b01: CUSTOMER_MASTER -> customers, CUSTOMER_MASTER_HIST -> customer_history.

The 155-column source row collapses into the PRD document: repeating groups become
addresses[]/phones[]/emails[], ENTITY_ATTR_VALUE embeds as attributes[], the 80 empty
FLAG_*/UDF_* columns and CUST_NAME_UPPER are dropped, and dirty values become null or []
with the raw string kept under legacy.<field>Raw.

    python migrations/mongodb/customers/load_customers.py [--drop]

Reads Oracle read-only through ORACLE_BILLING_URI in one snapshot transaction; writes only
ow_billing_migration.customers and ow_billing_migration.customer_history through
MONGODB_ATLAS_URI. Mapping: .migration/03_mapping_spec.json (version 1).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReplaceOne

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import (  # noqa: E402
    csv_list, decode, load_codes, money, mongo_db, oracle_connect, parse_dt, rows, set_raw,
    utc, yn,
)

COLLECTIONS = ("customers", "customer_history")
BATCH = 500

ADDR_LINES = [f"ADDR_LINE_{i}" for i in range(1, 7)]
MAIL_LINES = [f"MAIL_ADDR_LINE_{i}" for i in range(1, 7)]
PHONES = [("PHONE1", "PHONE1_TYPE_CD"), ("PHONE2", "PHONE2_TYPE_CD"),
          ("PHONE3", "PHONE3_TYPE_CD"), ("PHONE4", "PHONE4_TYPE_CD")]
EMAILS = ["EMAIL_1", "EMAIL_2", "EMAIL_3"]
DATES = [("SIGNUP_DT", "signupAt", "legacy.signupDtRaw"),
         ("LAST_ACTIVITY_DT", "lastActivityAt", "legacy.lastActivityDtRaw"),
         ("LAST_INVOICE_DT", "lastInvoiceAt", "legacy.lastInvoiceDtRaw"),
         ("LAST_PAYMENT_DT", "lastPaymentAt", "legacy.lastPaymentDtRaw"),
         ("TERMINATE_DT", "terminatedAt", "legacy.terminateDtRaw")]
MONEY = [("CUR_BAL_AMT", "current"), ("PAST_DUE_AMT", "pastDue"),
         ("YTD_BILLED_AMT", "ytdBilled"), ("LTD_BILLED_AMT", "ltdBilled"),
         ("YTD_PAID_AMT", "ytdPaid"), ("CREDIT_LIMIT_AMT", "creditLimit")]
FLAGS = [("TAX_EXEMPT_YN", "taxExempt"), ("CREDIT_HOLD_YN", "creditHold"),
         ("DUNNING_EXEMPT_YN", "dunningExempt"), ("VIP_YN", "vip")]
CSV_FIELDS = [("RELATED_ACCT_IDS", "relatedAccountIds", "legacy.relatedAcctIdsRaw", True),
              ("CHILD_ACCT_IDS", "childAccountIds", "legacy.childAcctIdsRaw", True),
              ("PROMO_CODES_CSV", "promoCodes", "legacy.promoCodesRaw", False)]

# The 80 columns the spec drops: profiling found no non-null value in any of them, which is
# the PRD's drop condition. The load re-checks it rather than trusting the profile.
DROPPED_EMPTY = ([f"FLAG_{i:02d}" for i in range(1, 21)]
                 + [f"UDF_{i:02d}" for i in range(1, 41)]
                 + [f"UDF_AMT_{i:02d}" for i in range(1, 11)]
                 + [f"UDF_DT_{i:02d}" for i in range(1, 11)])

CUSTOMER_COLUMNS = (
    ["CUST_ID", "CUST_SEQ_NO", "TENANT_ID", "CUST_NO", "CUST_NAME", "LEGAL_NAME", "DBA_NAME"]
    + ADDR_LINES + ["CITY", "STATE_CD", "ZIP", "ZIP4", "COUNTRY_CD"]
    + MAIL_LINES + ["MAIL_CITY", "MAIL_STATE_CD", "MAIL_ZIP"]
    + [c for pair in PHONES for c in pair] + ["FAX"] + EMAILS
    + [c for c, _, _ in DATES]
    + ["STATUS_CD", "SUB_STATUS_CD", "CUST_TYPE_CD", "SEGMENT_CD", "REGION_CD",
       "TERRITORY_CD", "CHANNEL_CD", "RATE_CLASS_CD"]
    + [c for c, _ in FLAGS] + [c for c, _ in MONEY] + [c for c, _, _, _ in CSV_FIELDS]
    + ["CONTACT_NOTES", "LEGACY_SYS_KEY", "MAINFRAME_ACCT_NO", "CONVERSION_BATCH_NO",
       "CREATED_BY", "CREATED_DT", "UPDATED_BY", "UPDATED_DT", "ROW_VERSION_NO"]
)
HISTORY_COLUMNS = ["HIST_ID", "HIST_DT", "HIST_OP"] + CUSTOMER_COLUMNS

# An account id list is a comma-separated list of account numbers. csv_list() flags the
# empty-item forms; a list whose items are not account numbers at all (for example
# 'A;B;C', which has no separator to split on) is malformed for the same reason and is
# reported the same way. Derived rule: see PROFILE FEEDBACK in the unit's recon report.
ACCOUNT_ID = re.compile(r"^\d+$")


def integer(value: Any) -> int | None:
    return None if value is None else int(value)


def account_id_list(value: Any) -> tuple[list[str], bool]:
    items, malformed = csv_list(value)
    if malformed:
        return [], True
    if any(not ACCOUNT_ID.match(item) for item in items):
        return [], True
    return items, False


def address(row: dict, kind: str, lines: list[str], city: str, state: str, zip_: str,
            zip4: str | None = None, country: str | None = None) -> dict:
    """One positional address element. The spec fixes index 0 as physical, 1 as mailing,
    so both elements are always present and absent components are explicit nulls."""
    out = {"kind": kind,
           "lines": [row[c] for c in lines if row[c] is not None],
           "city": row[city], "state": row[state], "zip": row[zip_]}
    if zip4 is not None:
        out["zip4"] = row[zip4]
    if country is not None:
        out["country"] = row[country]
    return out


def fax_type_code(codes) -> int | None:
    """FAX has no type column, so its phones[] element takes the PHONE_TYPE code that
    describes a fax. FAX is null on every row in this estate, so this is untravelled."""
    for (code_type, value), desc in codes.items():
        if code_type == "PHONE_TYPE" and desc == "fax":
            return value
    return None


def phones(row: dict, codes) -> list[dict]:
    out = [{"number": row[number], "kind": decode(codes, "PHONE_TYPE", row[kind])}
           for number, kind in PHONES if row[number] is not None]
    if row.get("FAX") is not None:
        out.append({"number": row["FAX"],
                    "kind": decode(codes, "PHONE_TYPE", fax_type_code(codes))})
    return out


def customer_body(row: dict, codes) -> dict:
    doc: dict[str, Any] = {
        "custNo": row["CUST_NO"],
        "tenantId": row["TENANT_ID"],
        "name": row["CUST_NAME"],
        "legalName": row["LEGAL_NAME"],
        "dbaName": row["DBA_NAME"],
        "type": decode(codes, "CUST_TYPE", row["CUST_TYPE_CD"]),
        "status": decode(codes, "CUST_STATUS", row["STATUS_CD"]),
        "subStatus": decode(codes, "CUST_STATUS", row["SUB_STATUS_CD"]),
        "segment": integer(row["SEGMENT_CD"]),
        "region": integer(row["REGION_CD"]),
        "territory": integer(row["TERRITORY_CD"]),
        "channel": integer(row["CHANNEL_CD"]),
        "rateClass": integer(row["RATE_CLASS_CD"]),
        "addresses": [
            address(row, "physical", ADDR_LINES, "CITY", "STATE_CD", "ZIP",
                    "ZIP4", "COUNTRY_CD"),
            address(row, "mailing", MAIL_LINES, "MAIL_CITY", "MAIL_STATE_CD", "MAIL_ZIP"),
        ],
        "phones": phones(row, codes),
        "emails": [row[c] for c in EMAILS if row[c] is not None],
        "flags": {},
        "dates": {},
        "balances": {target: money(row[column]) for column, target in MONEY},
        "contactNotes": row["CONTACT_NOTES"],
        "legacy": {"sysKey": row["LEGACY_SYS_KEY"],
                   "mainframeAcctNo": row["MAINFRAME_ACCT_NO"],
                   "conversionBatchNo": integer(row["CONVERSION_BATCH_NO"]),
                   "custSeqNo": integer(row["CUST_SEQ_NO"])},
        "audit": {"createdBy": row["CREATED_BY"],
                  "createdAt": utc(row["CREATED_DT"]),
                  "updatedBy": row["UPDATED_BY"],
                  "updatedAt": utc(row["UPDATED_DT"]),
                  "version": integer(row["ROW_VERSION_NO"])},
    }
    for column, target in FLAGS:
        value = yn(row[column])
        doc["flags"][target] = value
        if value is None and row[column] is not None:
            set_raw(doc, f"legacy.{target}YnRaw", row[column])
    for column, target, raw_to in DATES:
        value = parse_dt(row[column])
        doc["dates"][target] = value
        if value is None and row[column] is not None:
            set_raw(doc, raw_to, row[column])
    for column, target, raw_to, account_ids in CSV_FIELDS:
        items, malformed = (account_id_list(row[column]) if account_ids
                            else csv_list(row[column]))
        doc[target] = items
        if malformed:
            set_raw(doc, raw_to, row[column])
    return doc


def load_attributes(conn) -> dict[str, list[dict]]:
    """ENTITY_ATTR_VALUE rows for customers, as an array per customer: repeated
    (entity, attr_name) pairs are separate elements, which a map would lose."""
    out: dict[str, list[dict]] = {}
    for r in rows(conn, "SELECT eav_id, entity_id, attr_name, attr_value, created_dt "
                        "FROM entity_attr_value WHERE entity_type = 'CUSTOMER' "
                        "ORDER BY entity_id, eav_id"):
        element = {"eavId": int(r["EAV_ID"]),
                   "name": r["ATTR_NAME"],
                   "value": r["ATTR_VALUE"],
                   "createdAt": parse_dt(r["CREATED_DT"])}
        if element["createdAt"] is None and r["CREATED_DT"] is not None:
            set_raw(element, "legacy.createdDtRaw", r["CREATED_DT"])
        out.setdefault(r["ENTITY_ID"], []).append(element)
    return out


def check_dropped_empty(conn, table: str) -> None:
    """The spec drops 80 columns because they hold no value. A non-null one is a halt."""
    counts = ", ".join(f"COUNT({c}) AS {c}" for c in DROPPED_EMPTY)
    row = next(rows(conn, f"SELECT {counts} FROM {table}"))
    populated = {name: int(n) for name, n in row.items() if n}
    if populated:
        raise RuntimeError(f"{table}: dropped columns are not empty: {populated}; "
                           "the spec's drop condition no longer holds")


def build_customers(conn, codes):
    attributes = load_attributes(conn)
    check_dropped_empty(conn, "customer_master")
    columns = ", ".join(CUSTOMER_COLUMNS)
    for r in rows(conn, f"SELECT {columns} FROM customer_master"):
        doc = {"_id": r["CUST_ID"]}
        doc.update(customer_body(r, codes))
        doc["attributes"] = attributes.get(r["CUST_ID"], [])
        yield doc


def build_customer_history(conn, codes):
    """Trigger-fed history. Empty in this estate; the mapping is applied all the same so a
    row written after cutover lands in the same shape as its customer."""
    check_dropped_empty(conn, "customer_master_hist")
    columns = ", ".join(HISTORY_COLUMNS)
    for r in rows(conn, f"SELECT {columns} FROM customer_master_hist"):
        at = parse_dt(r["HIST_DT"])
        doc = {"_id": int(r["HIST_ID"]),
               "histId": int(r["HIST_ID"]),
               "op": r["HIST_OP"],
               "customerId": r["CUST_ID"],
               "at": at}
        doc.update(customer_body(r, codes))
        if at is None and r["HIST_DT"] is not None:
            set_raw(doc, "legacy.histDtRaw", r["HIST_DT"])
        yield doc


BUILDERS = {"customers": build_customers, "customer_history": build_customer_history}

INDEXES = {
    "customers": [
        ({"tenantId": ASCENDING, "custNo": ASCENDING},
         {"unique": True, "name": "tenantId_1_custNo_1"}),
        ({"name": ASCENDING},
         {"name": "name_1_ci", "collation": {"locale": "en", "strength": 2}}),
        ({"emails": ASCENDING}, {"name": "emails_1"}),
        ({"tenantId": ASCENDING, "status": ASCENDING}, {"name": "tenantId_1_status_1"}),
        ({"attributes.name": ASCENDING}, {"name": "attributes.name_1", "sparse": True}),
    ],
    "customer_history": [
        ({"customerId": ASCENDING, "at": DESCENDING}, {"name": "customerId_1_at_-1"}),
    ],
}


def load(drop: bool = False) -> dict[str, int]:
    conn = oracle_connect()
    db = mongo_db()
    counts = {}
    try:
        codes = load_codes(conn)
        for name in COLLECTIONS:
            if drop:
                db[name].drop()
            ops, n, seen = [], 0, set()
            for doc in BUILDERS[name](conn, codes):
                ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                seen.add(doc["_id"])
                n += 1
                if len(ops) == BATCH:
                    db[name].bulk_write(ops, ordered=False)
                    ops = []
            if ops:
                db[name].bulk_write(ops, ordered=False)
            stale = [i for i in db[name].distinct("_id") if i not in seen]
            if stale:
                db[name].delete_many({"_id": {"$in": stale}})
            for keys, opts in INDEXES[name]:
                db[name].create_index(list(keys.items()), **opts)
            counts[name] = n
            print(f"{name}: {n} documents"
                  + (f", {len(stale)} stale removed" if stale else ""))
    finally:
        conn.close()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drop", action="store_true",
                    help="drop both collections first (a clean reload)")
    args = ap.parse_args()
    load(drop=args.drop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
