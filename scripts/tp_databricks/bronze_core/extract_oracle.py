"""Extract the OW_BILLING core tables and measure the source side of the recon.

One read-only transaction does both jobs, so the landed rows and the numbers they are checked
against come from the same consistent snapshot even while other sessions are writing to the
database. Rows land as text in the canonical form of `canon.py`; typing happens once, in the
notebook, against the declared spec.

Credentials come from the environment (`OW_BILLING_USER`, `OW_BILLING_PASSWORD`,
`OW_BILLING_DSN`) and are never written to the extract, the manifest or the profile.
"""

from __future__ import annotations

import json
import os
from typing import Any

import oracledb

from . import canon

ROW_LEVEL_LIMIT = 200_000  # .migration/03_recon_tolerances.md T5


def connect() -> oracledb.Connection:
    user = os.environ.get("OW_BILLING_USER", "ow_billing")
    password = os.environ.get("OW_BILLING_PASSWORD")
    dsn = os.environ.get("OW_BILLING_DSN", "localhost:52521/FREEPDB1")
    if not password:
        raise SystemExit("OW_BILLING_PASSWORD is not set; the fixture credential is not in git")
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _source_columns(cur: oracledb.Cursor, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
          FROM user_tab_columns
         WHERE table_name = :t
         ORDER BY column_id
        """,
        t=table.upper(),
    )
    return [r[0].lower() for r in cur.fetchall()]


def extract_table(cur: oracledb.Cursor, tbl: dict, out_dir: str) -> dict[str, Any]:
    source = tbl["source"]
    cols = tbl["columns"]
    select_list = ",\n       ".join(
        f'{canon.oracle_text(c["name"], c["class"])} AS {c["name"].upper()}' for c in cols
    )
    # billing_audit_log carries a VARCHAR2(4000) message and is out of parity scope (D-20), so
    # no row hash is computed for it: STANDARD_HASH is a VARCHAR2 function and the concatenated
    # canonical row would not fit.
    hash_expr = canon.oracle_row_hash(cols) if tbl["parity"] else "CAST(NULL AS VARCHAR2(32))"

    cur.execute(f"SELECT {select_list},\n       {hash_expr} AS ROW_HASH\n  FROM {source}")
    names = [d[0].lower() for d in cur.description]
    rows = cur.fetchall()

    path = os.path.join(out_dir, f"{source.lower()}.json")
    hashes: list[str] = []
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            record = dict(zip(names, row))
            row_hash = record.pop("row_hash")
            if row_hash is not None:
                hashes.append(row_hash)
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    # Aggregates are recomputed by the database in the same read-only transaction rather than
    # derived from the rows above, so a transport bug cannot make both sides agree.
    money_cols = [c["name"] for c in cols if c["class"] == "money"]
    fold = canon.hash_fold_oracle(hash_expr) if tbl["parity"] else "NULL"
    agg_select = ["COUNT(*)", f"SUM({fold})"]
    for m in money_cols:
        agg_select.append(f'TO_CHAR(SUM("{m.upper()}"), \'{canon.MASKS["money"]}\')')
    cur.execute(f"SELECT {', '.join(agg_select)} FROM {source}")
    agg = cur.fetchone()

    profile = {
        "source_table": f"OW_BILLING.{source}",
        "source_rows": int(agg[0]),
        "checksum_fold": str(agg[1]) if agg[1] is not None else ("0" if tbl["parity"] else None),
        "parity_scope": bool(tbl["parity"]),
        "money_sums": {m: (agg[2 + i] or "0.00") for i, m in enumerate(money_cols)},
        "row_hashes_captured": len(hashes),
        "row_level_comparison": len(hashes) <= ROW_LEVEL_LIMIT,
    }
    if int(agg[0]) != len(rows):
        raise RuntimeError(
            f"{source}: row query returned {len(rows)} rows but COUNT(*) in the same "
            f"transaction returned {agg[0]}"
        )

    manifest = {
        "source_table": f"OW_BILLING.{source}",
        "source_columns": _source_columns(cur, source),
        "source_rows": profile["source_rows"],
        "canonical_form": "canon.py",
    }
    with open(os.path.join(out_dir, f"{source.lower()}.manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    with open(os.path.join(out_dir, f"{source.lower()}.hashes.txt"), "w", encoding="utf-8") as fh:
        fh.writelines(h + "\n" for h in sorted(hashes))

    profile["source_columns"] = manifest["source_columns"]
    return profile


def unbounded_number_columns(cur: oracledb.Cursor, tables: list[str]) -> list[dict[str, Any]]:
    """Live metadata view of ANOM-NUMBER-UNBOUNDED: NUMBER columns with no declared scale.

    Oracle reports a scale of 0 for `NUMBER(p)`, so the DDL artefact is the only place the
    missing scale is visible; both views are reported and neither is treated as the whole story.
    """
    binds = {f"t{i}": t.upper() for i, t in enumerate(tables)}
    names = ", ".join(f":{k}" for k in binds)
    cur.execute(
        f"""
        SELECT table_name, column_name, data_type, data_precision, data_scale
          FROM user_tab_columns
         WHERE table_name IN ({names})
           AND data_type = 'NUMBER'
           AND (data_precision IS NULL OR data_scale IS NULL)
         ORDER BY table_name, column_id
        """,
        **binds,
    )
    return [
        {
            "column": f"OW_BILLING.{r[0]}.{r[1]}",
            "data_type": r[2],
            "data_precision": r[3],
            "data_scale": r[4],
        }
        for r in cur.fetchall()
    ]


def scale_undeclared_in_ddl(ddl_path: str, sources: list[str]) -> list[str]:
    """NUMBER columns declared without a scale in the source DDL artefact."""
    out: list[str] = []
    current: str | None = None
    with open(ddl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("CREATE TABLE "):
                name = upper.split()[2].strip("(").rstrip()
                current = name if name in {s.upper() for s in sources} else None
                continue
            if current is None or not stripped or stripped.startswith("--"):
                continue
            if upper.startswith(");") or upper == ")":
                current = None
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            col, decl = parts[0], parts[1].rstrip(",")
            if decl.upper().startswith("NUMBER") and "," not in decl:
                out.append(f"OW_BILLING.{current}.{col.upper()}")
    return out


def extract_all(spec: dict, out_dir: str, ddl_path: str) -> dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    sources = [t["source"] for t in spec["tables"]]
    with connect() as conn:
        cur = conn.cursor()
        cur.arraysize = 5000
        # One consistent snapshot for rows and aggregates alike.
        cur.execute("SET TRANSACTION READ ONLY")
        banner = cur.execute("SELECT banner_full FROM v$version").fetchone()
        snapshot = cur.execute(
            "SELECT TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI:SSTZH:TZM'), "
            "SYS_CONTEXT('USERENV', 'DB_NAME'), SYS_CONTEXT('USERENV', 'CURRENT_USER')"
            " FROM dual"
        ).fetchone()
        profiles = {t["target"]: extract_table(cur, t, out_dir) for t in spec["tables"]}
        anomaly = {
            "live_metadata_unbounded": unbounded_number_columns(cur, sources),
            "ddl_scale_undeclared": scale_undeclared_in_ddl(ddl_path, sources),
        }
        conn.rollback()

    source_meta = {
        "oracle_version": (banner[0] if banner else None),
        "extracted_at": snapshot[0],
        "db_name": snapshot[1],
        "schema": snapshot[2],
        "transaction": "SET TRANSACTION READ ONLY (single snapshot for rows and aggregates)",
    }
    profile = {"source": source_meta, "tables": profiles, "number_scale_scan": anomaly}
    with open(os.path.join(out_dir, "source_profile.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, sort_keys=True)
    return profile
