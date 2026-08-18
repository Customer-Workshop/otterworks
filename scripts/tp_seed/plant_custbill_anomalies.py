#!/usr/bin/env python3
"""Plant deterministic content anomalies into generated CUSTBILL drop files.

Used by the parse conversion unit's golden-baseline procedure. Operates on the
three files gen_sample_data.pl wrote for a namespace (NFILES=3) and mutates:

  file 001, body row 7:  BILL-DATE (cols 41-48)  -> 20241131 (invalid calendar date)
  file 002, body row 13: BILL-AMT  (cols 49-60)  -> 0000012X4567 (non-numeric amount)
  file 003, trailer:     record count            -> body_count + 3 (trailer mismatch)

Deterministic: the same generated input always yields the same planted bytes.
Emits a JSON manifest of what was planted to stdout.

Usage: python3 scripts/tp_seed/plant_custbill_anomalies.py <NS> [--root <legacy root>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def body_rows(lines: list[str]) -> list[int]:
    return [i for i, l in enumerate(lines) if not l.startswith(("HDR", "TRL"))]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ns")
    p.add_argument("--root", default=os.environ.get("OTTERWORKS_LEGACY_ROOT", "/tmp/otterworks-legacy"))
    args = p.parse_args()
    ns = args.ns.upper()
    drop = Path(args.root) / "sftp-drop" / "upload"
    files = sorted(drop.glob(f"CUSTBILL_{ns}_*.dat"))
    if len(files) < 3:
        print(f"need 3 generated files for {ns}, found {len(files)}", file=sys.stderr)
        return 2
    planted = []

    lines = files[0].read_text().splitlines()
    r = body_rows(lines)[6]
    row = lines[r]
    lines[r] = row[:40] + "20241131" + row[48:]
    planted.append({"file": files[0].name, "kind": "invalid_calendar_date",
                    "cust_id": row[:10], "body_row": 7, "detail": "bill_date=20241131"})
    files[0].write_text("\n".join(lines) + "\n")

    lines = files[1].read_text().splitlines()
    r = body_rows(lines)[12]
    row = lines[r]
    lines[r] = row[:48] + "0000012X4567" + row[60:]
    planted.append({"file": files[1].name, "kind": "nonnumeric_amount",
                    "cust_id": row[:10], "body_row": 13, "detail": "amount=0000012X4567"})
    files[1].write_text("\n".join(lines) + "\n")

    lines = files[2].read_text().splitlines()
    n_body = len(body_rows(lines))
    for i, l in enumerate(lines):
        if l.startswith("TRL"):
            lines[i] = "TRL%010d%s" % (n_body + 3, " " * 52)
            planted.append({"file": files[2].name, "kind": "trailer_count_mismatch",
                            "cust_id": "", "body_row": None,
                            "detail": f"trailer={n_body + 3} body={n_body}"})
    files[2].write_text("\n".join(lines) + "\n")

    print(json.dumps({"namespace": args.ns, "planted_anomalies": planted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
