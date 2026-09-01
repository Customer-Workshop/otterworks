#!/usr/bin/env python3
"""Run the full-refresh agent commission summary on the serverless warehouse."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts" / "tp_dbx"))
from client import Databricks, require_ns

NS_BOUND = {
    "ow_tp.gold.mv_agent_commission_summary_cdw": "ow_tp.gold.mv_agent_commission_summary_{ns}",
    "ow_tp.silver.fact_commission_cdw": "ow_tp.silver.fact_commission_{ns}",
    "ow_tp.silver.dim_agent_cdw": "ow_tp.silver.dim_agent_{ns}",
    "ow_tp.silver.dim_product_cdw": "ow_tp.silver.dim_product_{ns}",
    "ow_tp.silver.dim_period_cdw": "ow_tp.silver.dim_period_{ns}",
    "_cdw": "_{ns}",
    "/cdw/": "/{ns}/",
}


def statements(path: Path, ns: str) -> list[str]:
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("--"))
    for literal, template in NS_BOUND.items():
        text = text.replace(literal, template.format(ns=ns))
    chunks: list[str] = []
    start = 0
    quoted = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif char == ";" and not quoted:
            chunk = text[start:index].strip()
            if chunk:
                chunks.append(chunk)
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default="cdw")
    parser.add_argument("--warehouse", default="565cd2fd713738c4")
    args = parser.parse_args()
    ns = require_ns(args.ns)
    dbx = Databricks(warehouse_id=args.warehouse)
    for name in ("ddl.sql", "load.sql"):
        for statement in statements(HERE / name, ns):
            result = dbx.sql_ok(statement)
            print(f"{name}: {' '.join(statement.split())[:100]} -> {result.state}")
    target = NS_BOUND["ow_tp.gold.mv_agent_commission_summary_cdw"].format(ns=ns)
    print(f"rows in {target}: {dbx.sql_ok(f'SELECT count(*) FROM {target}').scalar()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
