"""Load the captured legacy finance report into the recon source table.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/load_legacy_baseline_close.py

This is the SOURCE side of the p2-finance-close recon: the CSV that
finance_excel_report.pl itself wrote over the pinned fixture set, loaded line by line
into ow_tp.bronze.custbill_legacy_baseline_close. The TARGET side is
ow_tp.gold.custbill_finance_close, which the pipeline recomputes from silver. The
loader imports nothing from the converted code, so a bug in the close cannot be copied
into the baseline that judges it.

Two things it has to reconstruct, because the report does not carry them:

- the raw record type, which the report prints as a display name. The mapping is
  invertible: INVOICE is `01`, CREDIT is `02`, and `UNKNOWN(x)` is x.
- the sort key, `"$ccy|$rt"`, which is what the Perl actually sorted on. The loader
  rebuilds it and then asserts that the file's own line order is that key's ascending
  byte order - which is also what catches a mis-split of a line, since the report is
  unquoted and a currency holding a comma would slide the fields.

The table is replaced on every run: it is derived evidence, and a half-refreshed
baseline is worse than none.
"""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from databricks import sql as dbsql

TABLE = "ow_tp.bronze.custbill_legacy_baseline_close"
CAPTURED = Path(__file__).resolve().parents[1] / "baseline/captured"
ENCODING = "iso-8859-1"
HEADER = "Currency,RecordType,RecordCount,TotalAmount"
RAW_REC_TYPE = {"INVOICE": "01", "CREDIT": "02"}


def raw_record_type(display: str) -> str:
    if display in RAW_REC_TYPE:
        return RAW_REC_TYPE[display]
    if display.startswith("UNKNOWN(") and display.endswith(")"):
        return display[len("UNKNOWN(") : -1]
    raise SystemExit(f"unrecognised record type in the captured report: {display!r}")


def report_rows(csv: Path) -> list[tuple[str, int, str, str, int, Decimal]]:
    lines = csv.read_bytes().decode(ENCODING).split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != HEADER:
        raise SystemExit(f"{csv.name}: unexpected header {lines[:1]}")

    rows = []
    for order, line in enumerate(lines[1:], start=1):
        rest, count, total = line.rsplit(",", 2)
        currency, record_type = rest.split(",", 1)
        sort_key = f"{currency}|{raw_record_type(record_type)}"
        rows.append((sort_key, order, currency, record_type, int(count), Decimal(total)))

    if [row[0] for row in rows] != sorted(row[0] for row in rows):
        raise SystemExit(f"{csv.name}: line order is not the sort key's byte order")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(CAPTURED / "reports/finance_billing_20260915.csv"))
    args = ap.parse_args()

    rows = report_rows(Path(args.report))

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        cur.execute(f"CREATE OR REPLACE TABLE {TABLE} ("
                    "sort_key STRING, row_order INT, currency STRING, record_type STRING, "
                    "record_count BIGINT, total_amount DECIMAL(38,2))")
        values = ", ".join("(?, ?, ?, ?, ?, ?)" for _ in rows)
        cur.execute(f"INSERT INTO {TABLE} VALUES {values}",
                    [v for row in rows for v in row])
        cur.execute(f"SELECT count(*), sum(record_count) FROM {TABLE}")
        loaded, records = cur.fetchone()

    print(json.dumps({"table": TABLE, "rows": loaded, "records": int(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
