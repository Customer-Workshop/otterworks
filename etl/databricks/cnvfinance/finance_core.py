"""Report core for the finance_excel_report conversion (namespace slice cnvfinance).

Pure-Python replacement for the aggregation and rendering logic of
etl/legacy-extra/jobs/finance_excel_report.pl. No Spark imports: the
Databricks notebook wires it to Delta/Volumes, and the fixture recon wires
it to a local landing layout.

Contract: docs/tech-partnerships/contracts/finance_excel_report-cnvfinance.contract.json
- perl list-assignment split semantics: fields beyond the sixth are ignored
- rows with an empty customer id are skipped and counted (legacy: next if $cust eq '')
- non-numeric amounts and truncated rows with a missing/empty currency or
  record type are excluded and counted as malformed — NULL/missing never
  fails open into a plausible row
- amounts carried as exact integer cents; the rendered grid matches the
  legacy CSV byte-for-byte (header, C-locale key sort, %d / %.2f formats)
- record types outside 01/02 surface as UNKNOWN(rt), as the legacy report did
- deterministic ids via uuid5 over the input byte digests, never uuid4
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

NS_RE = re.compile(r"[a-z0-9_]{1,24}")
GLOB_RE = re.compile(r"^CUSTBILL.*\.psv$")
AMOUNT_RE = re.compile(r"^-?[0-9]+(\.[0-9]{1,2})?$")
CSV_HEADER = "Currency,RecordType,RecordCount,TotalAmount"


def require_ns(ns: str) -> str:
    if not NS_RE.fullmatch(ns):
        raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {ns!r}")
    return ns


def is_report_input(file_name: str) -> bool:
    """Legacy filename filter: grep { /^CUSTBILL.*\\.psv$/ } readdir(D)."""
    return GLOB_RE.match(file_name) is not None


def amount_to_cents(raw: str) -> int | None:
    """Exact cents for a well-formed decimal amount; None for anything else."""
    if not AMOUNT_RE.fullmatch(raw):
        return None
    sign = -1 if raw.startswith("-") else 1
    body = raw.lstrip("-")
    whole, _, frac = body.partition(".")
    return sign * (int(whole) * 100 + int(frac.ljust(2, "0") or "0"))


def record_type_name(rt: str) -> str:
    return "INVOICE" if rt == "01" else "CREDIT" if rt == "02" else f"UNKNOWN({rt})"


@dataclass
class ParsedBatch:
    rows: list[dict] = field(default_factory=list)
    rows_input: int = 0
    rows_skipped_empty_cust: int = 0
    rows_attributed_malformed: int = 0
    malformed: list[dict] = field(default_factory=list)


def parse_psv_bytes(data: bytes, source_file: str, batch: ParsedBatch) -> None:
    """Parse one landed PSV file into silver rows + attributed rejects.

    Line split mirrors perl's while(<F>)/chomp: newline-separated records, a
    trailing newline yields no empty final record. Input is 7-bit ASCII from
    the legacy parser; decoding is UTF-8 and a genuinely invalid byte
    sequence is attributed as a malformed row, never silently coerced.
    """
    chunks = data.split(b"\n")
    if chunks and chunks[-1] == b"":
        chunks.pop()
    for line_no, chunk in enumerate(chunks, start=1):
        batch.rows_input += 1
        try:
            line = chunk.decode("utf-8")
        except UnicodeDecodeError:
            batch.rows_attributed_malformed += 1
            batch.malformed.append({
                "source_file": source_file, "line_no": line_no,
                "raw_line": chunk.decode("latin-1"), "reason": "invalid_encoding",
            })
            continue
        # perl: ($cust,$name,$dt,$amt,$ccy,$rt) = split(/\|/); extra fields ignored
        fields = line.split("|")
        cust = fields[0] if len(fields) > 0 else ""
        name = fields[1] if len(fields) > 1 else ""
        dt = fields[2] if len(fields) > 2 else ""
        amt = fields[3] if len(fields) > 3 else ""
        ccy = fields[4] if len(fields) > 4 else ""
        rt = fields[5] if len(fields) > 5 else ""
        if cust == "":
            # legacy: next if ($cust eq "") — skip-and-count, never aggregate
            batch.rows_skipped_empty_cust += 1
            continue
        cents = amount_to_cents(amt)
        reason = None
        if cents is None:
            reason = "nonnumeric_amount"
        elif ccy == "":
            reason = "missing_currency"
        elif rt == "":
            reason = "missing_record_type"
        if reason is not None:
            # attribute-and-exclude: never coerced, never grouped under an empty key
            batch.rows_attributed_malformed += 1
            batch.malformed.append({
                "source_file": source_file, "line_no": line_no,
                "raw_line": line, "reason": reason,
            })
            continue
        batch.rows.append({
            "source_file": source_file, "line_no": line_no,
            "cust_id": cust, "cust_name": name, "bill_date": dt,
            "amount_cents": cents, "currency": ccy, "record_type": rt,
        })


def aggregate(rows: list[dict]) -> dict[tuple[str, str], list[int]]:
    """currency x record-type grid: {(ccy, rt): [record_count, total_cents]}."""
    grid: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        key = (row["currency"], row["record_type"])
        cell = grid.setdefault(key, [0, 0])
        cell[0] += 1
        cell[1] += row["amount_cents"]
    return grid


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def render_report_csv(grid: dict[tuple[str, str], list[int]]) -> bytes:
    """Byte-identical rendering of the legacy report body.

    Legacy iterates `sort keys %tot` over "$ccy|$rt" keys under LC_ALL=C, so
    rows sort by the raw key string ("EUR|01" < "EUR|02" < "GBP|01" ...).
    """
    lines = [CSV_HEADER]
    for (ccy, rt) in sorted(grid, key=lambda k: f"{k[0]}|{k[1]}"):
        count, cents = grid[(ccy, rt)]
        lines.append(f"{ccy},{record_type_name(rt)},{count},{format_cents(cents)}")
    return ("\n".join(lines) + "\n").encode("ascii")


def deterministic_run_id(ns: str, report_date: str, input_digests: dict[str, str]) -> str:
    material = ";".join(f"{name}:{sha}" for name, sha in sorted(input_digests.items()))
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"ow_tp/{ns}/finance_excel_report/{report_date}/{material}",
    ))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_legacy_report_csv(data: bytes) -> list[dict]:
    """Rows of a legacy finance_billing CSV for the ops mirror table."""
    text = data.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != CSV_HEADER:
        raise ValueError("not a legacy finance_billing CSV: header mismatch")
    rows = []
    for line in lines[1:]:
        ccy, rtname, count, total = line.split(",")
        rows.append({
            "currency": ccy, "record_type_name": rtname,
            "record_count": int(count), "total_amount": total,
        })
    return rows
