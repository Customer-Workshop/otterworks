"""Supplementary read-only census via DBA_* views (ALL_* hides PL/SQL objects without EXECUTE grants)."""
import json
import os
from pathlib import Path

import oracledb
from recon.adapters import parse_oracle_secret

OUT = Path(__file__).resolve().parent / "census_dba.json"
S = {"schema": "OW_BILLING"}


def rows(cur):
    names = [d[0].lower() for d in cur.description]
    return [dict(zip(names, [v if v is None or isinstance(v, (int, float, str)) else str(v) for v in r])) for r in cur.fetchall()]


def main():
    user, password, dsn = parse_oracle_secret(os.environ["OW_TP_ORACLE_RO_DSN"])
    out = {}
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cur = conn.cursor()
        cur.execute("SELECT object_name, object_type, status FROM dba_objects WHERE owner = :schema AND object_type IN ('PACKAGE','PACKAGE BODY','PROCEDURE','FUNCTION','TRIGGER','MATERIALIZED VIEW','VIEW','SEQUENCE','TYPE','SYNONYM','JOB') ORDER BY object_type, object_name", S)
        out["objects"] = rows(cur)
        cur.execute("SELECT name, type, referenced_name, referenced_type FROM dba_dependencies WHERE owner = :schema AND referenced_owner = :schema ORDER BY name, referenced_name", S)
        out["dependencies"] = rows(cur)
        cur.execute("SELECT sequence_name, last_number, increment_by, cache_size FROM dba_sequences WHERE sequence_owner = :schema ORDER BY sequence_name", S)
        out["sequences"] = rows(cur)
        cur.execute("SELECT DISTINCT name, type FROM dba_source WHERE owner = :schema AND UPPER(text) LIKE '%ROWID%'", S)
        out["rowid_usage"] = rows(cur)
        cur.execute("SELECT DISTINCT name, type FROM dba_source WHERE owner = :schema AND (UPPER(text) LIKE '%NLS_SORT%' OR UPPER(text) LIKE '%NLS_COMP%' OR UPPER(text) LIKE '%COLLATE%')", S)
        out["nls_usage"] = rows(cur)
        cur.execute("SELECT DISTINCT name, type FROM dba_source WHERE owner = :schema AND (UPPER(text) LIKE '%AUTONOMOUS_TRANSACTION%')", S)
        out["autonomous_tx"] = rows(cur)
        cur.execute("SELECT job_name, job_type, enabled, state, repeat_interval, run_count, last_start_date FROM dba_scheduler_jobs WHERE owner = :schema", S)
        out["scheduler_jobs"] = rows(cur)
        cur.execute("SELECT trigger_name, table_name, trigger_type, triggering_event, status FROM dba_triggers WHERE owner = :schema ORDER BY table_name, trigger_name", S)
        out["triggers"] = rows(cur)
        cur.execute("SELECT grantee, table_name, privilege FROM dba_tab_privs WHERE owner = :schema ORDER BY grantee, table_name, privilege", S)
        out["grants"] = rows(cur)
        cur.execute("SELECT username, COUNT(*) AS sessions FROM v$session WHERE schemaname = :schema OR username = :schema GROUP BY username", S)
        out["sessions"] = rows(cur)
        cur.execute("SELECT view_name FROM dba_views WHERE owner = :schema", S)
        out["views"] = rows(cur)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    for k, v in out.items():
        print(k, len(v))


if __name__ == "__main__":
    main()
