"""Generated CUSTBILL drop files for this unit's declared scratch namespaces.

Everything here is **generated fixture data**. It is not a migration of anything, no row of it exists
in `OW_BILLING` or in any real CUSTBILL drop, and every generated customer id is of the form
`GEN0000nnn` with the name field carrying the literal `GENERATED FIXTURE` so no artifact can present
it as customer data. It is never written into `ns=demo` — each fixture gets its own namespace — and
this unit never writes it into `ow_tp.bronze.custbill_records` itself: the files are landed on the
volume and the **merged `bronze_custbill` notebook** is run on them, which is wave 1's own writer
doing wave 1's own write.

Two namespaces, both existing because a measured zero on the `ns=demo` seed is not a detection:

* `fin_round` — `ANOM-PERL-ROUNDING` made visible at the printed cent. The `ns=demo` population's
  float accumulation and its exact decimal sum agree once rounded to cents (the artifacts are there:
  `USD|01` accumulates to `161573.37000000002`), so on that population the anomaly is real but
  invisible in the output. This namespace's `USD|01` group is 99 records of `9999999999.99` followed
  by 586 of `0.01`: the float accumulator prints `990000000004.88` where exact decimal gives
  `990000000004.87`. It also carries the populations the demo seed leaves at zero — a live
  `UNKNOWN(<rt>)` record type, a blank `CUST-ID` the source's `next if ($cust eq "")` skips — and a
  blank `CURRENCY` group, which the demo seed does have.
* `fin_halt` — a group whose cumulative total does not fit `DECIMAL(14,2)`, so every record of it is
  withheld as `NUMERIC_OVERFLOW` and the population crosses the 5% halt. Run once, to show the halt
  fires and that the rejected rows are already in the ledger when it does.

A third namespace, `fin_empty`, needs no file at all: it is the empty-input case, and its evidence is
that the unit still writes an explicit header-only report for it.

Copybook `CBCUST01`, byte positions from `parse_custbill_fixedwidth.sh`:
`CUST-ID` 1-10, `CUST-NAME` 11-40, `BILL-DATE` 41-48 (`YYYYMMDD`), `BILL-AMT` 49-60
(`9(10)V99`, implied decimal), `CURRENCY` 61-63, `REC-TYPE` 64-65. `HDR`/`TRL` records are not data;
`TRL` positions 4-13 carry the detail count, and `bronze_custbill` refuses a file whose trailer
disagrees with its detail count or whose bytes do not match a `<file>.sha256` transfer marker, so both
are produced correctly here — a refused file would measure this unit's inputs, not its behaviour.
"""

from __future__ import annotations

import decimal
import hashlib

NS_ROUND = "fin_round"
NS_HALT = "fin_halt"
NS_EMPTY = "fin_empty"
NAMESPACES = (NS_ROUND, NS_HALT, NS_EMPTY)

ORIGIN = "generated-fixture"
GENERATED_NAME = "GENERATED FIXTURE"
RECORD_LEN = 65
# 9(10)V99 at its ceiling: the largest amount one record can carry.
MAX_RECORD_CENTS = 999_999_999_999
# The target's DECIMAL(14,2) ceiling, as cents.
MONEY_MAX_CENTS = 99_999_999_999_999


def _detail(cust_id: str, bill_date: str, amt_cents: int, currency: str, rec_type: str) -> str:
    if not 0 <= amt_cents <= MAX_RECORD_CENTS:
        raise ValueError(f"{amt_cents} does not fit PIC 9(10)V99")
    record = (
        f"{cust_id:<10.10}"
        f"{GENERATED_NAME:<30.30}"
        f"{bill_date:<8.8}"
        f"{amt_cents:012d}"
        f"{currency:<3.3}"
        f"{rec_type:<2.2}"
    )
    if len(record) != RECORD_LEN:
        raise ValueError(f"generated record is {len(record)} bytes, not {RECORD_LEN}: {record!r}")
    return record


def _dat(tag: str, seq: str, details: list[str]) -> bytes:
    header = f"HDR CUSTBILL EXTRACT NS={tag} FILE={seq}".ljust(RECORD_LEN)
    trailer = f"TRL{len(details):010d}".ljust(RECORD_LEN)
    return ("\n".join([header, *details, trailer]) + "\n").encode("ascii")


def _drop(tag: str, seq: str, details: list[str]) -> dict[str, bytes]:
    """A drop file plus the completed-transfer marker `bronze_custbill` requires to ingest it."""
    name = f"CUSTBILL_{tag}_{seq}.dat"
    content = _dat(tag, seq, details)
    digest = hashlib.sha256(content).hexdigest()
    return {name: content, f"{name}.sha256": f"{digest}  {name}\n".encode("ascii")}


BIG_RECORDS = 99
SMALL_RECORDS = 586
BIG_CENTS = MAX_RECORD_CENTS  # 9999999999.99
SMALL_CENTS = 1  # 0.01
UNKNOWN_REC_TYPE = "07"
UNKNOWN_RECORDS = 2
UNKNOWN_CENTS = 10_000
BLANK_CUSTOMER_RECORDS = 2
BLANK_CUSTOMER_CENTS = 5_000
BLANK_CURRENCY_CENTS = 45_000
ROUND_DATE = "20260115"
# A second period, so the period-keyed target has more than one row per group to sum back.
ROUND_DATE_2 = "20260203"

HALT_RECORDS = 101
HALT_CLEAN_RECORDS = 9
HALT_CURRENCY = "ZZZ"
HALT_CLEAN_CENTS = 25_000
HALT_DATE = "20260220"


def _round_details() -> list[str]:
    details: list[str] = []
    n = 0

    def cust() -> str:
        nonlocal n
        n += 1
        return f"GEN{n:07d}"

    # The USD|01 group, in the order the accumulator sees it: the large records first, then the
    # small ones each of which is below the accumulated value's float resolution.
    for _ in range(BIG_RECORDS):
        details.append(_detail(cust(), ROUND_DATE, BIG_CENTS, "USD", "01"))
    for i in range(SMALL_RECORDS):
        date = ROUND_DATE if i % 2 == 0 else ROUND_DATE_2
        details.append(_detail(cust(), date, SMALL_CENTS, "USD", "01"))
    # A live UNKNOWN(<rt>) branch: the source publishes these as rows, it does not reject them.
    for _ in range(UNKNOWN_RECORDS):
        details.append(_detail(cust(), ROUND_DATE, UNKNOWN_CENTS, "GBP", UNKNOWN_REC_TYPE))
    # `next if ($cust eq "")`: an all-space CUST-ID, which the parser trims to '' and the report
    # skips silently. Its amount must therefore appear in no group.
    for _ in range(BLANK_CUSTOMER_RECORDS):
        details.append(_detail("", ROUND_DATE, BLANK_CUSTOMER_CENTS, "USD", "01"))
    # An all-space CURRENCY: key '|01', which sorts after every lettered currency byte-wise.
    details.append(_detail(cust(), ROUND_DATE_2, BLANK_CURRENCY_CENTS, "", "01"))
    return details


def _halt_details() -> list[str]:
    details: list[str] = []
    for i in range(HALT_RECORDS):
        details.append(_detail(f"GEN9{i:06d}", HALT_DATE, BIG_CENTS, HALT_CURRENCY, "01"))
    for i in range(HALT_CLEAN_RECORDS):
        details.append(_detail(f"GEN8{i:06d}", HALT_DATE, HALT_CLEAN_CENTS, "EUR", "01"))
    return details


def drops(ns: str) -> dict[str, bytes]:
    """The drop files (and transfer markers) for a fixture namespace."""
    if ns == NS_ROUND:
        return _drop("FINROUND", "001", _round_details())
    if ns == NS_HALT:
        return _drop("FINHALT", "001", _halt_details())
    if ns == NS_EMPTY:
        return {}
    raise ValueError(f"{ns} is not a gold_finance fixture namespace")


def expectations(ns: str) -> dict[str, object]:
    """What the fixture is *for*, as figures, derived here and not from the target or the notebook."""
    cent = decimal.Decimal("0.01")
    if ns == NS_ROUND:
        usd_exact = (
            decimal.Decimal(BIG_CENTS) * BIG_RECORDS + decimal.Decimal(SMALL_CENTS) * SMALL_RECORDS
        ) * cent
        accumulated = 0.0
        for _ in range(BIG_RECORDS):
            accumulated += BIG_CENTS / 100
        for _ in range(SMALL_RECORDS):
            accumulated += SMALL_CENTS / 100
        return {
            "declared": ORIGIN,
            "detail_records": BIG_RECORDS
            + SMALL_RECORDS
            + UNKNOWN_RECORDS
            + BLANK_CUSTOMER_RECORDS
            + 1,
            "rows_the_source_skips_for_a_blank_customer": BLANK_CUSTOMER_RECORDS,
            "unknown_record_type_rows": UNKNOWN_RECORDS,
            "unknown_record_type_codes": [UNKNOWN_REC_TYPE],
            "unknown_record_type_label": f"UNKNOWN({UNKNOWN_REC_TYPE})",
            "expected_quarantine_rows": 0,
            "groups": {
                "USD|01": {
                    "record_count": BIG_RECORDS + SMALL_RECORDS,
                    "exact_total": str(usd_exact),
                    "float_total_as_printed": f"{accumulated:.2f}",
                    "cent_diff": int(
                        (decimal.Decimal(f"{accumulated:.2f}") - usd_exact).scaleb(2)
                    ),
                },
                f"GBP|{UNKNOWN_REC_TYPE}": {
                    "record_count": UNKNOWN_RECORDS,
                    "exact_total": str(decimal.Decimal(UNKNOWN_CENTS * UNKNOWN_RECORDS) * cent),
                },
                "|01": {
                    "record_count": 1,
                    "exact_total": str(decimal.Decimal(BLANK_CURRENCY_CENTS) * cent),
                },
            },
        }
    if ns == NS_HALT:
        overflow_total = decimal.Decimal(BIG_CENTS) * HALT_RECORDS * cent
        rows = HALT_RECORDS + HALT_CLEAN_RECORDS
        return {
            "declared": ORIGIN,
            "detail_records": rows,
            "expected_quarantine_rows": HALT_RECORDS,
            "expected_quarantine_reason": "NUMERIC_OVERFLOW",
            "overflowing_group": f"{HALT_CURRENCY}|01",
            "overflowing_group_exact_total": str(overflow_total),
            "money_ceiling": str(decimal.Decimal(MONEY_MAX_CENTS) * cent),
            "expected_quarantine_rate_pct": round(100.0 * HALT_RECORDS / rows, 4),
            "expected_halt": True,
        }
    if ns == NS_EMPTY:
        return {
            "declared": "no fixture rows at all: this namespace is the empty-input case",
            "detail_records": 0,
            "expected_quarantine_rows": 0,
            "expected_report_lines": 1,
            "expected_report_data_rows": 0,
        }
    raise ValueError(f"{ns} is not a gold_finance fixture namespace")
