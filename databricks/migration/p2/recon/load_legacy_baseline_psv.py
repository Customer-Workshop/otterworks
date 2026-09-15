"""Load the captured legacy `.psv` output into the recon source table.

    python3 databricks/migration/recon/with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- \
      python3 databricks/migration/p2/recon/load_legacy_baseline_psv.py

This is the SOURCE side of the p2-custbill-parse recon: the lines
parse_custbill_fixedwidth.sh itself wrote over the pinned fixture set, loaded verbatim
into ow_tp.bronze.custbill_legacy_baseline_psv. The TARGET side is ow_tp.silver.custbill,
which the Lakeflow pipeline recomputes from the raw .dat inputs. This loader never imports
custbill_parse, so a bug in the parser cannot be copied into the baseline it is judged
against.

The join key is the physical record number in the .dat file, which the .psv does not
carry, so it is re-derived here: the legacy deletes every line beginning HDR or TRL and
keeps the rest in order, so the Nth surviving physical line is the Nth psv line. The
loader asserts that the two counts agree per file rather than trusting the alignment.

The table is replaced on every run: it is derived evidence, and a half-refreshed baseline
is worse than none.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from databricks import sql as dbsql

TABLE = "ow_tp.bronze.custbill_legacy_baseline_psv"
CAPTURED = Path(__file__).resolve().parents[1] / "baseline/captured"
ENCODING = "iso-8859-1"


def _lines(body: bytes) -> list[str]:
    """Split on LF; a trailing LF closes the last line rather than opening an empty one."""
    if not body:
        return []
    parts = body.split(b"\n")
    if parts[-1] == b"":
        parts.pop()
    return [p.decode(ENCODING) for p in parts]


def surviving_record_numbers(dat: Path) -> list[int]:
    """Physical record numbers the `sed -e '/^HDR/d' -e '/^TRL/d'` pass leaves behind."""
    return [
        number
        for number, line in enumerate(_lines(dat.read_bytes()), start=1)
        if not line.startswith(("HDR", "TRL"))
    ]


def rows_for(psv: Path, inputs: Path) -> list[tuple[str, int, str]]:
    dat = inputs / f"{psv.stem}.dat"
    psv_lines = _lines(psv.read_bytes())
    record_numbers = surviving_record_numbers(dat)
    if len(psv_lines) != len(record_numbers):
        raise SystemExit(
            f"{psv.name}: {len(psv_lines)} psv lines against {len(record_numbers)} "
            f"surviving records in {dat.name} - the baseline cannot be keyed"
        )
    return [
        (dat.name, record_no, line)
        for record_no, line in zip(record_numbers, psv_lines)
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--captured", default=str(CAPTURED))
    args = ap.parse_args()

    captured = Path(args.captured)
    rows: list[tuple[str, int, str]] = []
    for psv in sorted((captured / "parsed").glob("CUSTBILL*.psv")):
        rows.extend(rows_for(psv, captured / "inputs"))

    creds = json.loads(os.environ["DATABRICKS_MIGRATION_SQL"])
    with dbsql.connect(server_hostname=creds["server_hostname"],
                       http_path=creds["http_path"],
                       access_token=creds["access_token"]) as conn, conn.cursor() as cur:
        cur.execute(f"CREATE OR REPLACE TABLE {TABLE} ("
                    "source_file STRING, record_no BIGINT, psv_line STRING)")
        for chunk_start in range(0, len(rows), 200):
            chunk = rows[chunk_start:chunk_start + 200]
            values = ", ".join("(?, ?, ?)" for _ in chunk)
            cur.execute(f"INSERT INTO {TABLE} VALUES {values}",
                        [v for row in chunk for v in row])
        cur.execute(f"SELECT count(*), count(DISTINCT source_file) FROM {TABLE}")
        loaded, files = cur.fetchone()

    print(json.dumps({"table": TABLE, "rows": loaded, "files": files}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
