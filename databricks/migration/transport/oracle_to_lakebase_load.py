#!/usr/bin/env python3
"""Copy one Oracle reference table into its Lakebase table, driven by the unit mapping spec.

    python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w1 -- \
    python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/oracle_to_lakebase_load.py \
      --mapping .migration/units/p1-tenants/mapping_spec.json \
      --source-dsn-secret OW_TP_ORACLE_RO --target-secret OW_TP_LAKEBASE_DSN \
      --target-catalog ow_tp --target-schema billing

Scope: the operational tables of pipeline 1 that fit in one read (tens of rows up to the
25,000-row CUSTOMER_MASTER). The whole table is read in one statement and written in one
transaction, which is why this is not the watermarked, chunked loader used for the Delta
track (transport/jdbc_watermark_load.py).

A mapping spec's `derived_fields` are computed on the target by the converted
`billing.f_str2dt`, the same function the application will call, so the DD-MON-YY companions
carry the measured Oracle TO_DATE semantics (wave 0's date-parity probe) instead of a second
parser written here. The raw string column is still carried across byte-exact.

Idempotent by construction: rows are upserted on the mapping spec's key and rows the source
no longer has are deleted, so a rerun converges to the source rather than accumulating. That
is also what lets the recon gate prove idempotency by rerunning the load.

Column types are the target table's own (created by the reviewed DDL in
databricks/migration/lakebase/); this script never issues DDL. Values are carried across with
the mapping spec's per-field rules and nothing else - no cleaning, no defaulting, no
type-widening, so malformed strings and legacy oddities arrive as they are (D8-01).

Secrets are read from the environment by name and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# The write allowlist is the committed one or none at all; a caller cannot point the loader
# at a file of its own that authorizes somewhere else.
ALLOWED_TARGETS = Path(__file__).resolve().parents[3] / ".migration" / "allowed_targets.json"


def ident(name: str) -> str:
    """Reject anything that is not a plain identifier before it reaches a statement."""
    if not IDENT.match(name):
        raise SystemExit(f"refusing non-identifier name {name!r}")
    return name


def qualified(name: str) -> str:
    return ".".join(ident(part) for part in name.split("."))


def oracle_connect(secret_env: str):
    import oracledb

    # NUMBER arrives as a Python float unless decimals are asked for, which silently rounds
    # the money columns recon compares exactly.
    oracledb.defaults.fetch_decimals = True
    raw = os.environ.get(secret_env)
    if not raw:
        raise SystemExit(f"secret {secret_env} is not set in this shell; pass secrets by name")
    parts = json.loads(raw)
    return oracledb.connect(user=parts["user"], password=parts["password"],
                            dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def apply_rules(value, rules: list[str]):
    """The mapping spec's field rules, and only those."""
    if isinstance(value, str):
        if "rstrip_spaces" in rules:
            value = value.rstrip(" ")
        if "empty_string_is_null" in rules and value == "":
            value = None
    return value


def scale_of(target_type: str) -> int | None:
    m = re.fullmatch(r"numeric\((\d+),\s*(\d+)\)", target_type.strip(), re.I)
    return int(m.group(2)) if m else None


def quantize(value, target_type: str):
    """Land a NUMBER on the target column's declared scale, exactly.

    `decimal_round` in the mapping spec means the value is carried at the scale the target
    column declares. Oracle already enforces that scale on the source column, so this is a
    no-op on well-formed data and a visible failure - not a silent float - if it ever is not.
    """
    scale = scale_of(target_type)
    if scale is None or value is None:
        return value
    return Decimal(value).quantize(Decimal(1).scaleb(-scale))


def generated_columns(pg, schema: str, table_name: str) -> set[str]:
    """Names of the target's stored generated columns, read from the target catalog."""
    with pg.cursor() as cur:
        rows = cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s AND is_generated = 'ALWAYS'",
            (schema, table_name)).fetchall()
    return {r[0] for r in rows}


def load_table(table: dict, ora, pg, schema: str) -> dict:
    source_table = qualified(table["source_table"])
    target = f'{ident(schema)}.{ident(table["target_table"])}'
    fields = table["fields"]
    derived = table.get("derived_fields", [])
    src_cols = [ident(f["source"]) for f in fields]
    tgt_cols = [ident(f["target"]) for f in fields]
    key_cols = [ident(c) for c in table["key"]["target"]]
    key_idx = [tgt_cols.index(c) for c in key_cols]
    # A derived companion the target computes for itself (a stored generated column) rejects
    # any explicit value, so only the writable ones are carried in the insert.
    computed = generated_columns(pg, schema, table["target_table"])
    derived = [d for d in derived if d["target"] not in computed]
    raw_idx = [[f["target"] for f in fields].index(d["raw"]) for d in derived]
    tgt_cols += [ident(d["target"]) for d in derived]

    with ora.cursor() as cur:
        cur.execute(f"SELECT {', '.join(src_cols)} FROM {source_table}")
        rows = cur.fetchall()

    prepared = []
    for row in rows:
        out = []
        for value, field in zip(row, fields):
            value = apply_rules(value, field.get("rules", []))
            if "decimal_round" in field.get("rules", []):
                value = quantize(value, field["target_type"])
            out.append(value)
        # the parsed companion's argument is the raw string as it was carried across
        out += [out[i] for i in raw_idx]
        prepared.append(tuple(out))

    updates = [c for c in tgt_cols if c not in key_cols]
    set_clause = (", ".join(f"{c} = EXCLUDED.{c}" for c in updates) if updates
                  else f"{key_cols[0]} = EXCLUDED.{key_cols[0]}")
    values = (["%s"] * len(fields)
              + [f"{ident(schema)}.f_str2dt(%s)::timestamp"] * len(derived))
    insert = (f"INSERT INTO {target} ({', '.join(tgt_cols)}) "
              f"VALUES ({', '.join(values)}) "
              f"ON CONFLICT ({', '.join(key_cols)}) DO UPDATE SET {set_clause}")
    keys = [tuple(row[i] for i in key_idx) for row in prepared]
    # Keys are compared as text so one statement works for any key type; these tables are
    # tens of rows, so the cast costs nothing and keeps the code free of per-type branches.
    delete = (f"DELETE FROM {target} "
              f"WHERE ({', '.join(c + '::text' for c in key_cols)}) NOT IN "
              f"(SELECT * FROM unnest({', '.join(['%s::text[]'] * len(key_cols))}))")

    # Rows the source dropped go first: a value under a UNIQUE constraint that moved to a new
    # key would otherwise collide with its retiring owner and abort the whole load.
    with pg.cursor() as cur:
        # A converted BEFORE INSERT trigger would recompute derived columns over the migrated
        # rows and hide a source row that disagrees with its own trigger (Oracle fires these
        # on INSERT only, so an UPDATE can leave one stale). The backfill carries the values
        # the source holds; the trigger is back on for application writes before commit.
        cur.execute(f"ALTER TABLE {target} DISABLE TRIGGER USER")
        if keys:
            columns = [[str(k[i]) for k in keys] for i in range(len(key_cols))]
            cur.execute(delete, columns)
            removed = cur.rowcount
        else:  # an empty source truncates the target rather than leaving it stale
            cur.execute(f"DELETE FROM {target}")
            removed = cur.rowcount
        cur.executemany(insert, prepared)
        cur.execute(f"ALTER TABLE {target} ENABLE TRIGGER USER")
        advance_sequence(cur, table, target, schema)
        (count,) = cur.execute(f"SELECT count(*) FROM {target}").fetchone()
    return {"object": table["object"], "source_rows": len(prepared),
            "target_rows": count, "deleted": removed}


def advance_sequence(cur, table: dict, target: str, schema: str) -> None:
    """Move the converted sequence past the highest surrogate the backfill just loaded.

    The Oracle sequence's own NEXTVAL is not migrated (it is session state on a source we may
    not read twice), so the target sequence is set from the data it feeds, which is what the
    source sequence would have returned next.

    Two shapes are covered. A mapping that names an `identity` field owns a standalone
    sequence (`seq_<table>`, the converted Oracle sequence). A key column declared GENERATED
    BY DEFAULT owns an implicit sequence which an explicit insert does not move, so it would
    hand out 1 again and collide with a migrated row.

    Either way the sequence only ever goes forwards: an Oracle sequence does not rewind when
    its top rows are deleted, so neither may this one, or a rerun would reissue keys the
    source has already handed out. An empty table leaves the sequence where it is.
    """
    identity = table.get("identity")
    if identity:
        sequence = f'{ident(schema)}.{ident("seq_" + table["target_table"])}'
        (exists,) = cur.execute("SELECT to_regclass(%s) IS NOT NULL", (sequence,)).fetchone()
        if exists:
            forward(cur, sequence, target, ident(identity["target"]))
            return
    for col in (ident(c) for c in table["key"]["target"]):
        (sequence,) = cur.execute("SELECT pg_get_serial_sequence(%s, %s)",
                                  (target, col)).fetchone()
        if sequence:
            forward(cur, sequence, target, col)


def forward(cur, sequence: str, target: str, column: str) -> None:
    """setval the sequence to the data's next value, or leave it alone if it is already past.

    `setval` is absolute, so it can hand back numbers the sequence has already issued: rows
    deleted off the top, a rolled-back insert or a cached block all leave the sequence ahead
    of max(column).
    """
    last, is_called = cur.execute(
        f"SELECT last_value, is_called FROM {sequence}").fetchone()
    (from_data,) = cur.execute(
        f"SELECT coalesce(max({column}), 0) + 1 FROM {target}").fetchone()
    nxt = max(last + 1 if is_called else last, from_data)
    cur.execute("SELECT setval(%s, %s, false)", (sequence, nxt))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--source-dsn-secret", required=True, help="ENV VAR NAME, never a value")
    p.add_argument("--target-secret", required=True, help="ENV VAR NAME, never a value")
    p.add_argument("--target-catalog", required=True)
    p.add_argument("--target-schema", required=True)
    p.add_argument("--allowed-targets-file", type=Path, default=ALLOWED_TARGETS,
                   help=f"must be {ALLOWED_TARGETS}; accepted only so the recon commands "
                        "can pass it explicitly")
    args = p.parse_args(argv)

    if args.allowed_targets_file.resolve() != ALLOWED_TARGETS:
        raise SystemExit(f"--allowed-targets-file must be the committed {ALLOWED_TARGETS}, "
                         f"not {args.allowed_targets_file}")
    allowed = json.loads(ALLOWED_TARGETS.read_text())
    catalog = ident(args.target_catalog)
    if catalog not in allowed.get("catalogs", []) and catalog not in allowed:
        raise SystemExit(f"--target-catalog {catalog!r} is not in {args.allowed_targets_file}")
    # The allowlist file names the catalog, not the schema, so the schema is pinned here:
    # `billing` is the only Lakebase schema pipeline 1 may write, and the loader refuses the
    # rest rather than trusting whatever the caller passes.
    schema = ident(args.target_schema)
    allowed_schemas = allowed.get("lakebase_schemas", ["billing"])
    if schema not in allowed_schemas:
        raise SystemExit(f"--target-schema {schema!r} is not writable by a migration session "
                         f"(allowed: {', '.join(allowed_schemas)})")

    spec = json.loads(args.mapping.read_text())
    dsn = os.environ.get(args.target_secret)
    if not dsn:
        raise SystemExit(f"secret {args.target_secret} is not set in this shell")

    with oracle_connect(args.source_dsn_secret) as ora, psycopg.connect(dsn) as pg:
        (database,) = pg.execute("SELECT current_database()").fetchone()
        if database != catalog:
            raise SystemExit(f"target DSN connects to {database!r}, not the allowlisted "
                             f"{catalog!r}")
        results = [load_table(t, ora, pg, schema) for t in spec["tables"]]
        pg.commit()

    for r in results:
        print(f"loaded {spec['unit']}.{r['object']}: source_rows={r['source_rows']} "
              f"target_rows={r['target_rows']} deleted={r['deleted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
