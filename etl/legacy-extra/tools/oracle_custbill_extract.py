#!/usr/bin/env python3
"""Extract Oracle invoice headers into the legacy CUSTBILL feed layout."""

import argparse
import hashlib
import os
import unicodedata
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import oracledb

ADMIN_TENANT_ID = "a0000000-0000-0000-0000-000000000001"
EXTRACT_SQL = """
SELECT h.invoice_id,
       c.cust_no,
       c.cust_name,
       TO_DATE(h.invoice_dt, 'DD-MON-RR') AS period_end,
       h.total_amt,
       CASE WHEN h.total_amt < 0 THEN '02' ELSE '01' END AS record_type
  FROM invoice_header h
  JOIN customer_master c ON c.cust_id = h.cust_id
  LEFT JOIN tenants t ON t.id = h.tenant_id
 WHERE h.batch_no = :batch_no
    OR h.tenant_id = :admin_tenant_id
 ORDER BY period_end, c.cust_no, h.invoice_id
"""


def ns_batch_no(ns):
    seed = int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)
    return seed % 90_000_000 + 1_000_000


def _period_text(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y%m%d")


def _amount_cents(value):
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def format_record(row):
    cust_no = _ascii_text(row["cust_no"])[:10].ljust(10)
    name = _ascii_text(row["cust_name"])[:30].ljust(30)
    period_end = _period_text(row["period_end"])
    cents = _amount_cents(row["total_amt"])
    record_type = "02" if cents < 0 else str(row.get("record_type") or "01")[:2].rjust(2, "0")
    return f"{cust_no}{name}{period_end}{abs(cents):012d}USD{record_type}"


def _ascii_text(value):
    return (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "replace")
        .decode()
    )


def _row_mapping(row):
    if isinstance(row, dict):
        return row
    return {
        "invoice_id": row[0],
        "cust_no": row[1],
        "cust_name": row[2],
        "period_end": row[3],
        "total_amt": row[4],
        "record_type": row[5],
    }


def sort_rows(rows):
    return sorted(rows, key=lambda row: (
        _period_text(row["period_end"]),
        str(row["cust_no"] or ""),
        str(row["invoice_id"] or ""),
    ))


def extract(ns, out_dir, connection=None):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    filename = f"CUSTBILL_{ns.upper()}_ORACLE.dat"
    if connection is None:
        connection = oracledb.connect(
            user=os.getenv("ORACLE_USER", "ow_billing"),
            password=os.getenv("ORACLE_PASSWORD", "ow_billing"),
            host=os.getenv("ORACLE_HOST", "localhost"),
            port=int(os.getenv("ORACLE_PORT", "52521")),
            service_name=os.getenv("ORACLE_SERVICE", "FREEPDB1"),
        )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                EXTRACT_SQL,
                {"batch_no": ns_batch_no(ns), "admin_tenant_id": ADMIN_TENANT_ID},
            )
            rows = [_row_mapping(row) for row in cursor.fetchall()]
    finally:
        if connection is not None:
            connection.close()

    rows = sort_rows(rows)
    destination = out_path / filename
    temporary = destination.with_name(f"{destination.name}.tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as output:
        for row in rows:
            output.write(format_record(row))
            output.write("\n")
    os.replace(temporary, destination)
    return destination, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ns", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    destination, count = extract(args.ns, args.out)
    print(f"wrote {destination} ({count} records)")


if __name__ == "__main__":
    main()
