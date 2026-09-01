#!/usr/bin/env python3
"""Execute the dim_product unit end-to-end (ddl.sql then load.sql) on the serverless warehouse.

  python3 dbx/commission_dw/dim_product/run.py --ns cdw

Before any write the bronze feed row count is asserted against the manifest-declared source
volume, so the unit can never load a population it did not receive from the legacy extract.
Every run drops and recreates ow_tp.silver.dim_product_<ns> (idempotent; the unit owns only
that table). Statements run in order and the first failure aborts the run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "tp_dbx"))
from client import Databricks, require_ns

HERE = Path(__file__).resolve().parent
UNIT = "dim_product"
FEED_OBJECT = "PRODUCTS"


def statements(path: Path) -> list[str]:
    body = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ns", default="cdw")
    p.add_argument("--warehouse", default="565cd2fd713738c4")
    args = p.parse_args()
    ns = require_ns(args.ns)
    if ns != "cdw":
        raise SystemExit("this unit's SQL is bound to namespace cdw")

    manifest = json.loads((REPO / "etl" / "legacy-extra" / "commission_dw" / ns / "manifest.json").read_text())
    declared = manifest["files"][f"{FEED_OBJECT}.csv"]["rows"]
    dbx = Databricks(warehouse_id=args.warehouse)
    feed_rows = int(dbx.sql_ok(f"SELECT COUNT(*) FROM ow_tp.bronze.{FEED_OBJECT.lower()}_{ns}").scalar())
    if feed_rows != declared:
        raise SystemExit(f"feed ow_tp.bronze.{FEED_OBJECT.lower()}_{ns} has {feed_rows} rows; manifest declares {declared}")

    for name in ("ddl.sql", "load.sql"):
        for stmt in statements(HERE / name):
            dbx.sql_ok(stmt)
    n = int(dbx.sql_ok(f"SELECT COUNT(*) FROM ow_tp.silver.{UNIT}_{ns}").scalar())
    print(f"OK ow_tp.silver.{UNIT}_{ns} rows={n} (feed rows={feed_rows}, declared={declared})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
