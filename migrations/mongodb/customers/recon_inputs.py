"""Build the recon inputs for U2-customers: the unit's mapping slice, copies of the
ledger inputs, and the Tier 4 recorded operations.

    python migrations/mongodb/customers/recon_inputs.py .migration/recon/U2-customers

Three kinds of field cannot be graded by the harness's value tiers, so each is recorded as
a Tier 4 operation with a source SELECT and a read-only target pipeline:

  * Y/N flags, CSV lists and 'DD-MON-YY' date strings - the harness has no yn_to_bool,
    csv_split_trim or parse_date_string rule (raised as profile feedback in
    .migration/canonicalization.json; the harness is not patched).
  * CODES-decoded fields - the source holds an integer and the target a string.
  * The positional address fields (addresses.0.*, addresses.1.*) - the harness's field
    paths are identifiers, so an array index is not addressable at Tier 3.

The 25,000-row population makes a row-per-row Tier 4 op quadratic, so each operation is a
distribution or a digest over the whole population rather than a sample.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.unit_spec import slice_spec  # noqa: E402

UNIT = "U2-customers"
REPO = Path(__file__).resolve().parents[3]
LEDGER_INPUTS = ["02_tolerances.json", "canonicalization.json"]
POSITIONAL = re.compile(r"\.\d+\.")

CUSTOMERS = "customers"
HISTORY = "customer_history"
NUMERIC_LIST = r"^[[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9]+[[:space:]]*)*$"
PARSE_DT = "TO_DATE({col} DEFAULT NULL ON CONVERSION ERROR, 'DD-MON-YY')"
MONTH = "NVL(TO_CHAR(" + PARSE_DT + ", 'YYYY-MM'), '~null')"
PHONE_KINDS = [(1, "main"), (2, "billing"), (3, "fax"), (4, "after-hours")]


def decode_op(name: str, column: str, code_type: str, target: str, why: str) -> dict:
    decoded = (f"CASE WHEN m.{column} IS NULL THEN NULL ELSE "
               f"NVL(c.code_desc, 'UNKNOWN(' || TO_CHAR(m.{column}) || ')') END")
    return {
        "name": name, "collection": CUSTOMERS, "why": why,
        "rules": ["null_missing_equiv"],
        "source_sql": (f'SELECT {decoded} AS "{target}", COUNT(*) AS "n" '
                       f"FROM customer_master m LEFT JOIN codes c "
                       f"ON c.code_type = '{code_type}' AND c.code_val = m.{column} "
                       f"GROUP BY {decoded}"),
        "target_pipeline": [
            {"$group": {"_id": f"${target}", "n": {"$sum": 1}}},
            {"$project": {"_id": 0, target: "$_id", "n": 1}},
        ],
    }


def yn_op(column: str, target: str) -> dict:
    """Y/N to boolean, including the 'kept the raw value' branch the PRD asks for."""
    case = (f"CASE WHEN {column} IS NULL THEN 'null' "
            f"WHEN TRIM({column}) = 'Y' THEN 'true' "
            f"WHEN TRIM({column}) = 'N' THEN 'false' ELSE 'other' END")
    raw = f"legacy.{target}YnRaw"
    return {
        "name": f"yn_{target}", "collection": CUSTOMERS,
        "why": f"{column} becomes flags.{target}; the harness has no yn_to_bool rule.",
        "rules": ["null_missing_equiv"],
        "source_sql": (f'SELECT {case} AS "value", COUNT(*) AS "n" '
                       f"FROM customer_master GROUP BY {case}"),
        "target_pipeline": [
            {"$group": {"_id": {"$switch": {"branches": [
                {"case": {"$eq": [f"$flags.{target}", True]}, "then": "true"},
                {"case": {"$eq": [f"$flags.{target}", False]}, "then": "false"},
                {"case": {"$gt": [f"${raw}", None]}, "then": "other"}],
                "default": "null"}}, "n": {"$sum": 1}}},
            {"$project": {"_id": 0, "value": "$_id", "n": 1}},
        ],
    }


def month_op(name: str, column: str, target: str, why: str) -> dict:
    month = MONTH.format(col=column)
    return {
        "name": name, "collection": CUSTOMERS, "why": why,
        "rules": ["null_missing_equiv"],
        "source_sql": (f'SELECT {month} AS "month", COUNT(*) AS "n" '
                       f"FROM customer_master GROUP BY {month}"),
        "target_pipeline": [
            {"$group": {"_id": {"$ifNull": [
                {"$dateToString": {"format": "%Y-%m", "date": f"${target}"}}, "~null"]},
                "n": {"$sum": 1}}},
            {"$project": {"_id": 0, "month": "$_id", "n": 1}},
        ],
    }


def related_items_sql() -> str:
    """Account ids per list position: count and sum on each side. Only rows whose list is
    well formed contribute, which is the same set the loader parses."""
    parts = []
    for i in range(1, 5):
        item = f"TO_NUMBER(TRIM(REGEXP_SUBSTR(s, '[^,]+', 1, {i})))"
        alias = (' AS "pos"', ' AS "n"', ' AS "total"') if i == 1 else ("", "", "")
        parts.append(f"SELECT {i}{alias[0]}, COUNT({item}){alias[1]}, "
                     f"SUM(NVL({item}, 0)){alias[2]} FROM v")
    return ("WITH v AS (SELECT CASE WHEN REGEXP_LIKE(related_acct_ids, "
            f"'{NUMERIC_LIST}') THEN related_acct_ids END AS s FROM customer_master) "
            + " UNION ALL ".join(parts))


def promo_items_sql() -> str:
    parts = []
    for i in range(1, 4):
        item = f"TRIM(REGEXP_SUBSTR(promo_codes_csv, '[^,]+', 1, {i}))"
        alias = (' AS "pos"', ' AS "item"', ' AS "n"') if i == 1 else ("", "", "")
        parts.append(f"SELECT {i}{alias[0]}, {item}{alias[1]}, COUNT(*){alias[2]} "
                     f"FROM customer_master GROUP BY {item}")
    return " UNION ALL ".join(parts)


def positional_list(field: str, index: int) -> dict:
    return {"$ifNull": [{"$arrayElemAt": [f"$addresses.{field}", index]}, None]}


def ops() -> list[dict]:
    out = [
        decode_op("decode_status", "status_cd", "CUST_STATUS", "status",
                  "STATUS_CD is decoded through CODES CUST_STATUS, so the source integer "
                  "and the target string never compare raw."),
        decode_op("decode_sub_status", "sub_status_cd", "CUST_STATUS", "subStatus",
                  "SUB_STATUS_CD is decoded through CODES CUST_STATUS."),
        decode_op("decode_type", "cust_type_cd", "CUST_TYPE", "type",
                  "CUST_TYPE_CD is decoded through CODES CUST_TYPE."),
    ]
    out += [yn_op("tax_exempt_yn", "taxExempt"), yn_op("credit_hold_yn", "creditHold"),
            yn_op("dunning_exempt_yn", "dunningExempt"), yn_op("vip_yn", "vip")]
    out += [
        month_op("parse_signup_dt", "signup_dt", "dates.signupAt",
                 "SIGNUP_DT is a 'DD-MON-YY' string; graded as a month distribution over "
                 "all 25,000 rows, with the unparseable rows in the '~null' bucket."),
        month_op("parse_last_activity_dt", "last_activity_dt", "dates.lastActivityAt",
                 "LAST_ACTIVITY_DT is a 'DD-MON-YY' string."),
        {
            "name": "signup_dt_unparseable_raw", "collection": CUSTOMERS,
            "why": "the 50 unparseable SIGNUP_DT values: the date is null and the raw "
                   "string is kept under legacy.signupDtRaw.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT signup_dt AS "raw", COUNT(*) AS "n" '
                           "FROM customer_master WHERE signup_dt IS NOT NULL "
                           f"AND {PARSE_DT.format(col='signup_dt')} IS NULL "
                           "GROUP BY signup_dt"),
            "target_pipeline": [
                {"$match": {"legacy.signupDtRaw": {"$exists": True}}},
                {"$group": {"_id": "$legacy.signupDtRaw", "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "raw": "$_id", "n": 1}},
            ],
        },
        {
            "name": "parse_remaining_date_strings", "collection": CUSTOMERS,
            "why": "the three date strings that are null on every row: a parse that "
                   "invented or dropped a value would show here.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT \'lastInvoiceAt\' AS "field", '
                           'COUNT(last_invoice_dt) AS "n" FROM customer_master '
                           "UNION ALL SELECT 'lastPaymentAt', COUNT(last_payment_dt) "
                           "FROM customer_master "
                           "UNION ALL SELECT 'terminatedAt', COUNT(terminate_dt) "
                           "FROM customer_master"),
            "target_pipeline": [
                {"$group": {"_id": None, **{
                    name: {"$sum": {"$cond": [
                        {"$eq": [{"$type": f"$dates.{name}"}, "date"]}, 1, 0]}}
                    for name in ("lastInvoiceAt", "lastPaymentAt", "terminatedAt")}}},
                {"$project": {"_id": 0, "rows": [
                    {"field": name, "n": f"${name}"}
                    for name in ("lastInvoiceAt", "lastPaymentAt", "terminatedAt")]}},
                {"$unwind": "$rows"},
                {"$replaceRoot": {"newRoot": "$rows"}},
            ],
        },
        {
            "name": "csv_related_account_list_lengths", "collection": CUSTOMERS,
            "why": "RELATED_ACCT_IDS splits into an array; -1 is the malformed bucket "
                   "(empty item, stray separator, or an item that is not an account id), "
                   "which becomes [] plus legacy.relatedAcctIdsRaw.",
            "rules": ["null_missing_equiv"],
            "source_sql": (
                'SELECT CASE WHEN related_acct_ids IS NULL THEN 0 '
                f"WHEN REGEXP_LIKE(related_acct_ids, '{NUMERIC_LIST}') "
                "THEN REGEXP_COUNT(related_acct_ids, ',') + 1 ELSE -1 END "
                'AS "len", COUNT(*) AS "n" FROM customer_master '
                "GROUP BY CASE WHEN related_acct_ids IS NULL THEN 0 "
                f"WHEN REGEXP_LIKE(related_acct_ids, '{NUMERIC_LIST}') "
                "THEN REGEXP_COUNT(related_acct_ids, ',') + 1 ELSE -1 END"),
            "target_pipeline": [
                {"$project": {"len": {"$cond": [
                    {"$gt": [{"$size": {"$ifNull": ["$relatedAccountIds", []]}}, 0]},
                    {"$size": "$relatedAccountIds"},
                    {"$cond": [{"$gt": ["$legacy.relatedAcctIdsRaw", None]}, -1, 0]}]}}},
                {"$group": {"_id": "$len", "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "len": "$_id", "n": 1}},
            ],
        },
        {
            "name": "csv_related_account_malformed_raw", "collection": CUSTOMERS,
            "why": "the 31 malformed RELATED_ACCT_IDS values, compared as a set.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT related_acct_ids AS "raw", COUNT(*) AS "n" '
                           "FROM customer_master WHERE related_acct_ids IS NOT NULL "
                           f"AND NOT REGEXP_LIKE(related_acct_ids, '{NUMERIC_LIST}') "
                           "GROUP BY related_acct_ids"),
            "target_pipeline": [
                {"$match": {"legacy.relatedAcctIdsRaw": {"$exists": True}}},
                {"$group": {"_id": "$legacy.relatedAcctIdsRaw", "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "raw": "$_id", "n": 1}},
            ],
        },
        {
            "name": "csv_related_account_items", "collection": CUSTOMERS,
            "why": "the account ids themselves, per position: count and sum on each side.",
            "rules": ["null_missing_equiv"],
            "source_sql": related_items_sql(),
            "target_pipeline": [
                {"$project": {"items": {"$map": {
                    "input": {"$range": [0, 4]}, "as": "i",
                    "in": {"pos": {"$add": ["$$i", 1]},
                           "v": {"$arrayElemAt": ["$relatedAccountIds", "$$i"]}}}}}},
                {"$unwind": "$items"},
                {"$group": {"_id": "$items.pos",
                            "n": {"$sum": {"$cond": [
                                {"$eq": [{"$type": "$items.v"}, "missing"]}, 0, 1]}},
                            "total": {"$sum": {"$toLong": {"$ifNull": ["$items.v", 0]}}}}},
                {"$project": {"_id": 0, "pos": "$_id", "n": 1, "total": 1}},
            ],
        },
        {
            "name": "csv_promo_codes_items", "collection": CUSTOMERS,
            "why": "PROMO_CODES_CSV splits into promoCodes[]; every code is compared in "
                   "its position.",
            "rules": ["empty_string_is_null", "null_missing_equiv"],
            "source_sql": promo_items_sql(),
            "target_pipeline": [
                {"$project": {"items": {"$map": {
                    "input": {"$range": [0, 3]}, "as": "i",
                    "in": {"pos": {"$add": ["$$i", 1]},
                           "item": {"$ifNull": [
                               {"$arrayElemAt": ["$promoCodes", "$$i"]}, None]}}}}}},
                {"$unwind": "$items"},
                {"$group": {"_id": {"pos": "$items.pos", "item": "$items.item"},
                            "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "pos": "$_id.pos", "item": "$_id.item", "n": 1}},
            ],
        },
        {
            "name": "csv_child_account_ids_absent", "collection": CUSTOMERS,
            "why": "CHILD_ACCT_IDS is null on every row: childAccountIds must be empty "
                   "everywhere, with no raw kept.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT COUNT(child_acct_ids) AS "populated", '
                           'COUNT(*) AS "docs" FROM customer_master'),
            "target_pipeline": [
                {"$group": {"_id": None,
                            "populated": {"$sum": {"$cond": [
                                {"$or": [
                                    {"$gt": [{"$size": {"$ifNull": [
                                        "$childAccountIds", []]}}, 0]},
                                    {"$gt": ["$legacy.childAcctIdsRaw", None]}]}, 1, 0]}},
                            "docs": {"$sum": 1}}},
                {"$project": {"_id": 0, "populated": 1, "docs": 1}},
            ],
        },
        {
            "name": "address_physical_scalars", "collection": CUSTOMERS,
            "why": "addresses[0] is the physical address; its scalar fields sit behind an "
                   "array index, which the harness's field paths cannot address.",
            "rules": ["rstrip_spaces", "empty_string_is_null", "null_missing_equiv"],
            "source_sql": ('SELECT city AS "city", state_cd AS "state", zip AS "zip", '
                           'zip4 AS "zip4", country_cd AS "country", COUNT(*) AS "n" '
                           "FROM customer_master "
                           "GROUP BY city, state_cd, zip, zip4, country_cd"),
            "target_pipeline": [
                {"$group": {"_id": {name: positional_list(name, 0) for name in
                                    ("city", "state", "zip", "zip4", "country")},
                            "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "n": 1, **{
                    name: f"$_id.{name}" for name in
                    ("city", "state", "zip", "zip4", "country")}}},
            ],
        },
        {
            "name": "address_physical_lines", "collection": CUSTOMERS,
            "why": "addresses[0].lines keeps the non-null ADDR_LINE_n columns in column "
                   "order; compared as line count plus the second line's value.",
            "rules": ["empty_string_is_null", "null_missing_equiv"],
            "source_sql": (
                "SELECT "
                + " + ".join(f"CASE WHEN addr_line_{i} IS NULL THEN 0 ELSE 1 END"
                             for i in range(1, 7))
                + ' AS "lineCount", COALESCE('
                + ", ".join(f"addr_line_{i}" for i in range(2, 7))
                + ') AS "line2", COUNT(*) AS "n" FROM customer_master GROUP BY '
                + " + ".join(f"CASE WHEN addr_line_{i} IS NULL THEN 0 ELSE 1 END"
                             for i in range(1, 7))
                + ", COALESCE(" + ", ".join(f"addr_line_{i}" for i in range(2, 7)) + ")"),
            "target_pipeline": [
                {"$project": {"lines": {"$ifNull": [
                    {"$arrayElemAt": ["$addresses.lines", 0]}, []]}}},
                {"$group": {"_id": {"lineCount": {"$size": "$lines"},
                                    "line2": {"$ifNull": [
                                        {"$arrayElemAt": ["$lines", 1]}, None]}},
                            "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "lineCount": "$_id.lineCount",
                              "line2": "$_id.line2", "n": 1}},
            ],
        },
        {
            "name": "address_physical_line1_digest", "collection": CUSTOMERS,
            "why": "ADDR_LINE_1 has 25,000 near-unique values, so it is compared as a "
                   "digest rather than row by row.",
            "rules": ["empty_string_is_null", "null_missing_equiv"],
            "source_sql": ('SELECT COUNT(addr_line_1) AS "n", '
                           'COUNT(DISTINCT addr_line_1) AS "distinctLines", '
                           'MIN(addr_line_1) AS "mn", MAX(addr_line_1) AS "mx" '
                           "FROM customer_master"),
            "target_pipeline": [
                {"$project": {"line1": {"$arrayElemAt": [
                    {"$ifNull": [{"$arrayElemAt": ["$addresses.lines", 0]}, []]}, 0]}}},
                {"$match": {"line1": {"$type": "string"}}},
                {"$group": {"_id": None, "n": {"$sum": 1},
                            "lines": {"$addToSet": "$line1"},
                            "mn": {"$min": "$line1"}, "mx": {"$max": "$line1"}}},
                {"$project": {"_id": 0, "n": 1, "mn": 1, "mx": 1,
                              "distinctLines": {"$size": "$lines"}}},
            ],
        },
        {
            "name": "address_mailing_element", "collection": CUSTOMERS,
            "why": "addresses[1] is the mailing address: the element is always present in "
                   "the declared position, and every mailing column is null in the source.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT COUNT(*) AS "elements", COUNT(mail_city) AS "city", '
                           'COUNT(mail_state_cd) AS "state", COUNT(mail_zip) AS "zip", '
                           'COUNT(mail_addr_line_1) AS "line1" FROM customer_master'),
            "target_pipeline": [
                {"$group": {"_id": None,
                            "elements": {"$sum": {"$cond": [
                                {"$eq": [{"$arrayElemAt": ["$addresses.kind", 1]},
                                         "mailing"]}, 1, 0]}},
                            **{name: {"$sum": {"$cond": [
                                {"$eq": [{"$type": positional_list(name, 1)}, "string"]},
                                1, 0]}} for name in ("city", "state", "zip")},
                            "line1": {"$sum": {"$cond": [
                                {"$gt": [{"$size": {"$ifNull": [
                                    {"$arrayElemAt": ["$addresses.lines", 1]}, []]}},
                                    0]}, 1, 0]}}}},
                {"$project": {"_id": 0, "elements": 1, "city": 1, "state": 1, "zip": 1,
                              "line1": 1}},
            ],
        },
        {
            "name": "phones_kind_decode", "collection": CUSTOMERS,
            "why": "PHONE1..4 collapse into phones[]; each kind is decoded through CODES "
                   "PHONE_TYPE, so the integer and the string never compare raw.",
            "rules": ["null_missing_equiv"],
            "source_sql": "SELECT " + ", ".join(
                " + ".join(f"SUM(CASE WHEN phone{slot} IS NOT NULL "
                           f"AND phone{slot}_type_cd = {code} THEN 1 ELSE 0 END)"
                           for slot in range(1, 5))
                + f' AS "{name}"' for code, name in PHONE_KINDS)
            + ", " + " + ".join(
                f"SUM(CASE WHEN phone{slot} IS NOT NULL THEN 1 ELSE 0 END)"
                for slot in range(1, 5)) + ' AS "elements" FROM customer_master',
            "target_pipeline": [
                {"$unwind": "$phones"},
                {"$group": {"_id": None, "elements": {"$sum": 1},
                            **{name: {"$sum": {"$cond": [
                                {"$eq": ["$phones.kind", name]}, 1, 0]}}
                               for _, name in PHONE_KINDS}}},
                {"$project": {"_id": 0, "elements": 1,
                              **{name: 1 for _, name in PHONE_KINDS}}},
            ],
        },
        {
            "name": "phones_number_digest", "collection": CUSTOMERS,
            "why": "the phone numbers themselves, as a digest over every non-null slot.",
            "rules": ["empty_string_is_null", "null_missing_equiv"],
            "source_sql": ('SELECT COUNT(*) AS "elements", COUNT(DISTINCT p) AS "distinctNumbers", '
                           'MIN(p) AS "mn", MAX(p) AS "mx" FROM ('
                           + " UNION ALL ".join(
                               f"SELECT phone{slot} AS p FROM customer_master "
                               f"WHERE phone{slot} IS NOT NULL" for slot in range(1, 5))
                           + ")"),
            "target_pipeline": [
                {"$unwind": "$phones"},
                {"$group": {"_id": None, "elements": {"$sum": 1},
                            "numbers": {"$addToSet": "$phones.number"},
                            "mn": {"$min": "$phones.number"},
                            "mx": {"$max": "$phones.number"}}},
                {"$project": {"_id": 0, "elements": 1, "mn": 1, "mx": 1,
                              "distinctNumbers": {"$size": "$numbers"}}},
            ],
        },
        {
            "name": "emails_digest", "collection": CUSTOMERS,
            "why": "EMAIL_1..3 collapse into emails[]; compared as a digest over every "
                   "non-null slot.",
            "rules": ["empty_string_is_null", "null_missing_equiv"],
            "source_sql": ('SELECT COUNT(*) AS "elements", COUNT(DISTINCT e) AS "distinctEmails", '
                           'MIN(e) AS "mn", MAX(e) AS "mx" FROM ('
                           + " UNION ALL ".join(
                               f"SELECT email_{slot} AS e FROM customer_master "
                               f"WHERE email_{slot} IS NOT NULL" for slot in range(1, 4))
                           + ")"),
            "target_pipeline": [
                {"$unwind": "$emails"},
                {"$group": {"_id": None, "elements": {"$sum": 1},
                            "addresses": {"$addToSet": "$emails"},
                            "mn": {"$min": "$emails"}, "mx": {"$max": "$emails"}}},
                {"$project": {"_id": 0, "elements": 1, "mn": 1, "mx": 1,
                              "distinctEmails": {"$size": "$addresses"}}},
            ],
        },
        {
            "name": "attributes_created_dt_parse", "collection": CUSTOMERS,
            "why": "ENTITY_ATTR_VALUE.CREATED_DT is a 'DD-MON-YY' string inside the "
                   "embedded attributes[]; graded as a month distribution over all 8,333 "
                   "elements.",
            "rules": ["null_missing_equiv"],
            "source_sql": (f'SELECT {MONTH.format(col="created_dt")} AS "month", '
                           'COUNT(*) AS "n" FROM entity_attr_value '
                           "WHERE entity_type = 'CUSTOMER' "
                           f"GROUP BY {MONTH.format(col='created_dt')}"),
            "target_pipeline": [
                {"$unwind": "$attributes"},
                {"$group": {"_id": {"$ifNull": [
                    {"$dateToString": {"format": "%Y-%m",
                                       "date": "$attributes.createdAt"}}, "~null"]},
                    "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "month": "$_id", "n": 1}},
            ],
        },
        {
            "name": "attributes_per_customer", "collection": CUSTOMERS,
            "why": "attributes[] is an array, not a map: a repeated (entity, attr_name) "
                   "pair must stay a separate element, so the per-customer element count "
                   "is compared as a distribution.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT NVL(e.cnt, 0) AS "size", COUNT(*) AS "n" '
                           "FROM customer_master m LEFT JOIN (SELECT entity_id, "
                           "COUNT(*) AS cnt FROM entity_attr_value "
                           "WHERE entity_type = 'CUSTOMER' GROUP BY entity_id) e "
                           "ON e.entity_id = m.cust_id GROUP BY NVL(e.cnt, 0)"),
            "target_pipeline": [
                {"$group": {"_id": {"$size": {"$ifNull": ["$attributes", []]}},
                            "n": {"$sum": 1}}},
                {"$project": {"_id": 0, "size": "$_id", "n": 1}},
            ],
        },
        {
            "name": "history_rows", "collection": HISTORY,
            "why": "CUSTOMER_MASTER_HIST is trigger-fed and empty; the op compares the "
                   "row set itself, so a row appearing on either side is a finding.",
            "rules": ["null_missing_equiv"],
            "source_sql": ('SELECT hist_id AS "id", hist_op AS "op" '
                           "FROM customer_master_hist"),
            "target_pipeline": [{"$project": {"_id": 0, "id": "$histId", "op": "$op"}}],
        },
    ]
    return out


def mapping_for_harness() -> dict:
    """The unit's slice of the mapping spec, with the positional address fields moved to
    the Tier 4 list: the harness addresses target fields by identifier, so an array index
    is not a path it can grade. Nothing about the mapping itself changes."""
    spec = slice_spec(UNIT)
    for collection in spec["collections"]:
        graded, by_op = [], []
        for field in collection.get("fields", []):
            if POSITIONAL.search(field["target"]):
                by_op.append({**field, "grading": "tier4_op",
                              "why_ungraded": "positional path inside addresses[]: the "
                                              "harness grades identifier paths only"})
            else:
                graded.append(field)
        collection["fields"] = graded
        if by_op:
            collection["fields_positional_graded_by_op"] = by_op
        for embed in collection.get("embeds", []):
            # The harness wants both sides of an embed scoped or neither. The child_where
            # keeps CUSTOMER rows, and every one of them embeds in this collection, so the
            # matching target scope is every document.
            if embed.get("child_where") and "target_where" not in embed:
                embed["target_where"] = "{}"
    return spec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args()
    inputs = args.out_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "mapping.json").write_text(
        json.dumps(mapping_for_harness(), indent=2) + "\n")
    (inputs / f"{UNIT}.json").write_text(json.dumps(ops(), indent=2) + "\n")
    for name in LEDGER_INPUTS:
        shutil.copyfile(REPO / ".migration" / name, inputs / name)
    print(f"wrote {args.out_dir}/mapping.json, {len(ops())} ops and "
          f"{len(LEDGER_INPUTS)} ledger input copies under {inputs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
