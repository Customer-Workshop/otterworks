#!/usr/bin/env python3
"""The converted form of the Oracle history triggers and their sequences.

Legacy behaviour being replaced (OW_BILLING):

    CREATE SEQUENCE seq_customer_master_hist START WITH 1 INCREMENT BY 1 NOCACHE;
    CREATE OR REPLACE TRIGGER trg_customer_master_hist
    AFTER UPDATE OR DELETE ON customer_master FOR EACH ROW ...
        INSERT INTO customer_master_hist (hist_id, hist_dt, hist_op, <every other column>)
        VALUES (seq_customer_master_hist.NEXTVAL,
                TO_CHAR(SYSDATE,'DD-MON-YY HH24:MI:SS'),
                'UPD' | 'DEL',
                :OLD.<every other column>);

    seq_subscriptions_hist / trg_subscriptions_hist are the same shape on `subscriptions`.

Row-level AFTER triggers do not exist in Delta, so the behaviour moves from the source
table to the writer: whoever applies an UPDATE or DELETE to the parent silver table appends
the pre-change image here in the same run. This module renders that append as one
INSERT ... SELECT over a caller-supplied old-image relation (the parent's CDC pre-images,
e.g. `table_changes()` output filtered to `update_preimage` / `delete`), so the history row
is written from the same rows the parent write consumed.

What is preserved, deliberately:

  - full row copy, column for column, including magic status codes, CHAR(1) Y/N flags and
    the comma-separated id lists, which stay verbatim text;
  - `hist_op` is 'UPD' for an update and 'DEL' for a delete, and only those two events
    write history - an INSERT into the parent writes nothing, exactly as in Oracle;
  - `hist_dt` is a STRING in Oracle's `DD-MON-YY HH24:MI:SS` shape, uppercase month, not a
    timestamp. It is written with the same format and converted to UTC explicitly (plan
    decision P1-D3), so the text does not move with the writer's session timezone;
  - the parsed companions of the `DD-MON-YY` string dates are recomputed by the same
    shared `oracle_dates.parse_date` expression the backfill uses, so an append and a
    reload of the same value cannot disagree.

The sequence: Delta has no sequences, and this batch may write nothing except the two
history tables, so `hist_id` is allocated from the history table itself -
`max(hist_id) + row_number()`. That reproduces what the legacy code depends on (a unique,
monotonically increasing id per appended row; Oracle's NOCACHE sequence already permits
gaps and gives no other guarantee) without inventing a counter table outside the declared
write targets. It assumes one writer per history table at a time, which is the same
assumption the single-threaded nightly batch already makes; a concurrent writer would need
the allocation moved into the parent's own transaction.

Default output is SQL on stdout; `--apply` runs it against the warehouse.

    python3 silver_hist_trigger.py \
        --mapping .migration/units/p1-subscriptions-hist/mapping_spec.json \
        --old-image ow_tp.silver.subscriptions_preimage --op UPD
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from oracle_dates import HIST_DT, parse_date

CATALOG = "ow_tp"
SILVER = "silver"
WAREHOUSE = "565cd2fd713738c4"

WRITABLE = {"customer_master_hist", "subscriptions_hist"}
HEADER = ("hist_id", "hist_dt", "hist_op")
OPS = {"UPD", "DEL"}

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
QUALIFIED = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*){0,2}$")
TYPE = re.compile(r"^[A-Z_]+(\(\d+(,\s*\d+)?\))?$")

ZONELESS_SOURCE = ("DATE", "TIMESTAMP")


def ident(name: str) -> str:
    if not IDENT.match(name or ""):
        raise SystemExit(f"refusing non-identifier {name!r}")
    return name


def qualified(name: str) -> str:
    if not QUALIFIED.match((name or "").strip()):
        raise SystemExit(f"refusing non-table reference {name!r}")
    return name.strip()


def sql_type(name: str) -> str:
    if not TYPE.match((name or "").strip()):
        raise SystemExit(f"refusing non-type {name!r}")
    return name.strip()


def target_type(field: dict) -> str:
    declared = sql_type(field["target_type"])
    source = (field.get("source_type") or "").split("(")[0].strip().upper()
    if source in ZONELESS_SOURCE and declared in ("TIMESTAMP", "DATE"):
        return "TIMESTAMP_NTZ"
    return declared


def append_sql(table: dict, old_image: str, op: str) -> str:
    target = ident(table["target_table"])
    if target not in WRITABLE:
        raise SystemExit(f"{target!r} is not a declared write target of this batch")
    if op not in OPS:
        raise SystemExit(f"hist_op must be one of {sorted(OPS)}")

    body = [f for f in table["fields"] if f["target"] not in HEADER]
    derived = table.get("derived_fields", [])
    columns = list(HEADER) + [ident(f["target"]) for f in body] \
        + [ident(d["target"]) for d in derived]

    # Oracle's NOCACHE sequence: unique and increasing, gaps allowed. row_number() over the
    # parent key gives the same contract for a batch of pre-images.
    order = ", ".join(ident(f["source"]) for f in body[:1]) or "1"
    hist_id = (f"(SELECT coalesce(max(hist_id), 0) FROM {CATALOG}.{SILVER}.{target}) "
               f"+ row_number() OVER (ORDER BY {order})")

    values = [hist_id, HIST_DT, f"'{op}'"]
    values += [f"cast({ident(f['source'])} AS {target_type(f)})" for f in body]
    values += [f"cast({parse_date(ident(d['raw']))} AS TIMESTAMP_NTZ)"
               for d in derived]

    return (f"INSERT INTO {CATALOG}.{SILVER}.{target} ({', '.join(columns)}) "
            f"SELECT {', '.join(values)} FROM {qualified(old_image)}")


def sql_conn():
    from databricks.sdk.core import Config, oauth_service_principal

    from databricks import sql as dbsql

    cfg = Config(host=os.environ["DATABRICKS_HOST"],
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    return dbsql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
        credentials_provider=lambda: oauth_service_principal(cfg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--old-image", required=True,
                    help="relation holding the parent's pre-change rows (:OLD), "
                         "column names as in the parent table")
    ap.add_argument("--op", required=True, choices=sorted(OPS))
    ap.add_argument("--apply", action="store_true",
                    help="execute the append; default prints the statement")
    args = ap.parse_args()

    with open(args.mapping) as fh:
        spec = json.load(fh)
    statements = [append_sql(t, args.old_image, args.op) for t in spec["tables"]]

    if not args.apply:
        for statement in statements:
            print(statement)
        return 0

    with sql_conn() as conn, conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print(json.dumps({"unit": spec["unit"], "op": args.op,
                      "appended_from": args.old_image}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
