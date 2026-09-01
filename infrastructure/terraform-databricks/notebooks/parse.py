# Databricks notebook source
"""`parse` task of job ow_tp_custbill.

Fixed-width body records are parsed on the driver so byte-level slicing and
exact decimal conversion remain explicit. Malformed rows are quarantined.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

CATALOG = "ow_tp"
BRONZE = f"{CATALOG}.bronze.custbill_raw"
SILVER = f"{CATALOG}.silver.custbill_records"
QUARANTINE = f"{CATALOG}.silver.custbill_quarantine"
NS_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
MIN_RECORD_LEN = 65
REASONS = (
    "short_record",
    "nonnumeric_amount",
    "invalid_calendar_date",
    "trailer_count_mismatch",
)
NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")


def require_ns(ns: str) -> str:
    if not NS_RE.fullmatch(ns or ""):
        raise ValueError(f"ns must match [a-z0-9][a-z0-9-]{{0,31}}: {ns!r}")
    return ns


def slice_fields(raw_line: str) -> dict[str, str]:
    return {
        "cust_id": raw_line[0:10],
        "cust_name": raw_line[10:40],
        "bill_date": raw_line[40:48],
        "bill_amt": raw_line[48:60],
        "currency": raw_line[60:63],
        "rec_type": raw_line[63:65],
    }


def rtrim_spaces(s: str) -> str:
    return re.sub(r" +$", "", s)


def parse_amount(digits: str) -> Decimal | None:
    if re.fullmatch(r"[0-9]{12}", digits) is None:
        return None
    return (Decimal(digits) / Decimal(100)).quantize(Decimal("0.00"))


def parse_bill_date(yyyymmdd: str) -> date | None:
    if re.fullmatch(r"[0-9]{8}", yyyymmdd) is None:
        return None
    try:
        return date(int(yyyymmdd[0:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
    except ValueError:
        return None


def parse_trailer_count(raw_line: str) -> int | None:
    count = raw_line[3:13]
    if re.fullmatch(r"[0-9]+", count) is None:
        return None
    return int(count)


@dataclass
class ParsedRow:
    source_file: str
    line_no: int
    cust_id: str
    cust_name: str
    bill_date: date
    bill_amt: Decimal
    currency: str
    rec_type: str


def parse_body_line(
    source_file: str, line_no: int, raw_line: str
) -> tuple[ParsedRow | None, list[str]]:
    if len(raw_line) < MIN_RECORD_LEN:
        return None, ["short_record"]

    fields = slice_fields(raw_line)
    amount = parse_amount(fields["bill_amt"])
    bill_date = parse_bill_date(fields["bill_date"])
    reasons = []
    if amount is None:
        reasons.append("nonnumeric_amount")
    if bill_date is None:
        reasons.append("invalid_calendar_date")
    if reasons:
        return None, reasons

    return (
        ParsedRow(
            source_file=source_file,
            line_no=line_no,
            cust_id=rtrim_spaces(fields["cust_id"]),
            cust_name=rtrim_spaces(fields["cust_name"]),
            bill_date=bill_date,
            bill_amt=amount,
            currency=rtrim_spaces(fields["currency"]),
            rec_type=fields["rec_type"],
        ),
        [],
    )


def trailer_defects(file_lines: list[tuple[int, str, str]]) -> list[tuple[int, str]]:
    body_count = sum(record_kind == "BODY" for _, record_kind, _ in file_lines)
    defects = []
    for line_no, record_kind, raw_line in file_lines:
        if record_kind != "TRL":
            continue
        if parse_trailer_count(raw_line) != body_count:
            defects.append((line_no, "trailer_count_mismatch"))
    return defects


def parse_file(
    source_file: str, lines: list[tuple[int, str, str]]
) -> tuple[list[ParsedRow], list[tuple[str, int, str, str]]]:
    parsed_rows = []
    quarantine_rows = []
    for line_no, record_kind, raw_line in lines:
        if record_kind != "BODY":
            continue
        parsed, reasons = parse_body_line(source_file, line_no, raw_line)
        if parsed is not None:
            parsed_rows.append(parsed)
        else:
            quarantine_rows.extend((source_file, line_no, raw_line, reason) for reason in reasons)

    for line_no, reason in trailer_defects(lines):
        raw_line = next(raw for number, kind, raw in lines if kind == "TRL" and number == line_no)
        quarantine_rows.append((source_file, line_no, raw_line, reason))
    return parsed_rows, quarantine_rows


RUN_LOG: list[str] = []


def log(**fields) -> None:
    line = " ".join(f"{key}={value}" for key, value in fields.items())
    RUN_LOG.append(line)
    print(line, flush=True)


def finish(summary: str) -> None:
    dbutils.notebook.exit(json.dumps({"summary": summary, "log": RUN_LOG}))  # noqa: F821


def main() -> None:
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        DateType,
        DecimalType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    ns = require_ns(dbutils.widgets.get("ns"))  # noqa: F821 - injected by Databricks
    log(stage="parse", ns=ns)

    non_ascii = spark.sql(  # noqa: F821
        f"SELECT count(*) FROM {BRONZE} "
        "WHERE ns = :ns AND raw_line RLIKE '[^\\x00-\\x7F]'",
        args={"ns": ns},
    ).collect()[0][0]
    if non_ascii:
        raise RuntimeError("non-ASCII raw_line values are not supported")

    rows = spark.sql(  # noqa: F821
        f"SELECT source_file, line_no, record_kind, raw_line FROM {BRONZE} "
        "WHERE ns = :ns ORDER BY source_file, line_no",
        args={"ns": ns},
    ).collect()
    file_lines: dict[str, list[tuple[int, str, str]]] = {}
    for row in rows:
        source_file, line_no, record_kind, raw_line = row
        file_lines.setdefault(source_file, []).append((line_no, record_kind, raw_line))

    if not any(record_kind == "BODY" for lines in file_lines.values() for _, record_kind, _ in lines):
        log(action="no body rows")
        finish("silver=0 quarantine=0")
        return

    silver_rows = []
    quarantine_rows = []
    for source_file in sorted(file_lines):
        parsed, quarantined = parse_file(source_file, file_lines[source_file])
        silver_rows.extend(parsed)
        quarantine_rows.extend(quarantined)
        log(
            file=source_file,
            action="parsed",
            silver=len(parsed),
            quarantine=len(quarantined),
        )

    seen_keys = set()
    for row in silver_rows:
        key = (row.source_file, row.line_no)
        if key in seen_keys:
            raise RuntimeError(f"duplicate silver natural key: {key!r}")
        seen_keys.add(key)

    files = sorted(file_lines)
    for source_file in files:
        spark.sql(  # noqa: F821
            f"DELETE FROM {SILVER} WHERE ns = :ns AND source_file = :f",
            args={"ns": ns, "f": source_file},
        )
        spark.sql(  # noqa: F821
            f"DELETE FROM {QUARANTINE} WHERE ns = :ns AND source_file = :f",
            args={"ns": ns, "f": source_file},
        )

    silver_schema = StructType([
        StructField("ns", StringType(), False),
        StructField("source_file", StringType(), False),
        StructField("line_no", IntegerType(), False),
        StructField("cust_id", StringType(), False),
        StructField("cust_name", StringType(), False),
        StructField("bill_date", DateType(), False),
        StructField("bill_amt", DecimalType(12, 2), False),
        StructField("currency", StringType(), False),
        StructField("rec_type", StringType(), False),
    ])
    silver_values = [
        (
            ns,
            row.source_file,
            row.line_no,
            row.cust_id,
            row.cust_name,
            row.bill_date,
            row.bill_amt,
            row.currency,
            row.rec_type,
        )
        for row in silver_rows
    ]
    if silver_values:
        (
            spark.createDataFrame(silver_values, silver_schema)  # noqa: F821
            .withColumn("parsed_at", F.current_timestamp())
            .write.mode("append")
            .saveAsTable(SILVER)
        )

    quarantine_schema = StructType([
        StructField("ns", StringType(), False),
        StructField("source_file", StringType(), False),
        StructField("line_no", IntegerType(), False),
        StructField("raw_line", StringType(), False),
        StructField("reason", StringType(), False),
    ])
    quarantine_values = [
        (ns, source_file, line_no, raw_line, reason)
        for source_file, line_no, raw_line, reason in quarantine_rows
    ]
    if quarantine_values:
        (
            spark.createDataFrame(quarantine_values, quarantine_schema)  # noqa: F821
            .withColumn("detected_at", F.current_timestamp())
            .write.mode("append")
            .saveAsTable(QUARANTINE)
        )

    finish(f"files={len(files)} silver={len(silver_rows)} quarantine={len(quarantine_rows)}")


if __name__ == "__main__":
    main()
