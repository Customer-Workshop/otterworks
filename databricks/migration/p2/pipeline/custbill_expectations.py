"""The expectation set from record contract §6, as SQL over the silver columns.

One definition, used twice: the pipeline decorates the silver table with it, and
the quarantine table re-evaluates the same strings to record *which* checks a row
failed. Two hand-kept copies of these conditions would drift, and a drift here is
invisible until someone trusts the quarantine table.

Every one of these is **warn-only**. The legacy parser processes all of these rows
and so must the target: quarantine is a copy, never a filter (C-6.1, C-6.3). There
is deliberately no `expect_all_or_drop` anywhere in this unit.
"""

from __future__ import annotations

# name -> condition that holds for a *good* row.
SILVER_EXPECTATIONS: dict[str, str] = {
    # The layout is 65 bytes. The legacy never checks, so short records silently
    # lose their tail fields and long ones silently lose their surplus.
    "rec_len_65": "record_bytes = 65",
    # finance_excel_report.pl skips a row with an empty first field, so a record
    # that lands here with no customer id is a record that never reaches gold.
    "cust_id_nonempty": "cust_id <> ''",
    # C-3.5: the date transform is string surgery, so '20259999' becomes
    # '2025-99-99' and eight spaces become '    -  -  '.
    "bill_date_valid_iso": "try_to_date(bill_date, 'yyyy-MM-dd') IS NOT NULL",
    # C-3.3: anything that is not 12 digits still parses, as a prefix.
    "bill_amt_all_digits": "bill_amt_raw RLIKE '^[0-9]{12}$'",
    # C-3.4: the copybook says unsigned; a leading '-' says otherwise.
    "bill_amt_non_negative": "CAST(bill_amt AS DECIMAL(38,2)) >= 0",
    # C-7.3: the group key is a raw byte string, so 'usd' is its own currency.
    "currency_known": "currency IN ('USD', 'EUR', 'GBP')",
    "rec_type_known": "rec_type IN ('01', '02')",
    # C-5.1: a '|' inside any slice shifts every downstream field by one.
    "no_delimiter_collision": "psv_field_count = 6",
    # C-1.3: one multi-byte character shifts every later field by its extra bytes.
    "ascii_only": "raw_record RLIKE '^[\\\\x00-\\\\x7F]*$'",
}

# Two per-file checks. The HDR/TRL deletion happens before parsing, so a shadowed
# data record never reaches silver at all and cannot be checked row by row; it is
# counted per file instead. C-4.3, ETL-0187: logged since 2011, never enforced -
# and still not enforced here, it raises a warning and changes no row.
FILE_AUDIT_EXPECTATIONS: dict[str, str] = {
    "trailer_count_matches": "trailer_count IS NULL OR trailer_count = parsed_count",
    "not_hdr_trl_shadowed": "shadowed_count = 0",
}


def failed_expectations_sql(expectations: dict[str, str]) -> str:
    """SQL array of the names a row fails, for the quarantine table.

    `filter(array(...), x -> x IS NOT NULL)` rather than a chain of concats so the
    order is the declaration order and an empty result is an empty array, not NULL.
    """
    cases = ",\n        ".join(
        f"CASE WHEN NOT ({condition}) THEN '{name}' END" for name, condition in expectations.items()
    )
    return f"filter(array(\n        {cases}\n    ), x -> x IS NOT NULL)"
