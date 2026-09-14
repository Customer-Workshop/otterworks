"""Read-only OW_BILLING census for the estate inventory. Writes CSV/TSV under /home/ubuntu/probe/census/.
Never prints credential values."""
import csv, json, os, subprocess, oracledb

OUT = "/home/ubuntu/probe/census"
os.makedirs(OUT, exist_ok=True)
sec = json.loads(json.loads(subprocess.check_output(
    ["aws", "secretsmanager", "get-secret-value", "--secret-id", "ow-tp/oracle/ow_billing_ro",
     "--region", "us-east-1", "--output", "json"]))["SecretString"])
conn = oracledb.connect(user=sec["user"], password=sec["password"],
                        dsn=f'{sec["host"]}:{sec["port"]}/{sec["service"]}')
del sec
cur = conn.cursor()

QUERIES = {
 "objects": "SELECT object_name, object_type, status, created, last_ddl_time FROM dba_objects WHERE owner='OW_BILLING' ORDER BY object_type, object_name",
 "tables": "SELECT t.table_name, t.num_rows, t.last_analyzed, (SELECT COUNT(*) FROM dba_tab_columns c WHERE c.owner=t.owner AND c.table_name=t.table_name) cols, (SELECT COUNT(*) FROM dba_indexes i WHERE i.table_owner=t.owner AND i.table_name=t.table_name) idx, (SELECT COUNT(*) FROM dba_triggers g WHERE g.table_owner=t.owner AND g.table_name=t.table_name) trg FROM dba_tables t WHERE t.owner='OW_BILLING' ORDER BY 1",
 "rowcounts": None,
 "constraints": "SELECT c.constraint_name, c.constraint_type, c.table_name, c.status, c.r_constraint_name, (SELECT r.table_name FROM dba_constraints r WHERE r.owner=c.r_owner AND r.constraint_name=c.r_constraint_name) ref_table, c.search_condition_vc, (SELECT LISTAGG(cc.column_name, ',') WITHIN GROUP (ORDER BY cc.position) FROM dba_cons_columns cc WHERE cc.owner=c.owner AND cc.constraint_name=c.constraint_name) cols FROM dba_constraints c WHERE c.owner='OW_BILLING' ORDER BY c.table_name, c.constraint_type, c.constraint_name",
 "indexes": "SELECT i.index_name, i.table_name, i.uniqueness, i.index_type, i.status, (SELECT LISTAGG(ic.column_name, ',') WITHIN GROUP (ORDER BY ic.column_position) FROM dba_ind_columns ic WHERE ic.index_owner=i.owner AND ic.index_name=i.index_name) cols FROM dba_indexes i WHERE i.owner='OW_BILLING' ORDER BY 2,1",
 "triggers": "SELECT trigger_name, trigger_type, triggering_event, table_name, status, trigger_body FROM dba_triggers WHERE owner='OW_BILLING' ORDER BY table_name, trigger_name",
 "sequences": "SELECT sequence_name, min_value, increment_by, cache_size, last_number, cycle_flag FROM dba_sequences WHERE sequence_owner='OW_BILLING' ORDER BY 1",
 "routines": "SELECT object_name, procedure_name, object_type, subprogram_id FROM dba_procedures WHERE owner='OW_BILLING' AND procedure_name IS NOT NULL ORDER BY 1,4",
 "source_lines": "SELECT name, type, COUNT(*) lines FROM dba_source WHERE owner='OW_BILLING' GROUP BY name, type ORDER BY 1,2",
 "deps": "SELECT name, type, referenced_owner, referenced_name, referenced_type FROM dba_dependencies WHERE owner='OW_BILLING' AND referenced_owner NOT IN ('SYS','PUBLIC') ORDER BY 1,2,4",
 "jobs": "SELECT job_name, enabled, state, job_type, job_action, repeat_interval, last_start_date, run_count, failure_count FROM dba_scheduler_jobs WHERE owner='OW_BILLING' ORDER BY 1",
 "views": "SELECT view_name FROM dba_views WHERE owner='OW_BILLING'",
 "mviews": "SELECT mview_name FROM dba_mviews WHERE owner='OW_BILLING'",
 "synonyms": "SELECT synonym_name, table_owner, table_name FROM dba_synonyms WHERE owner='OW_BILLING' OR table_owner='OW_BILLING'",
 "tab_privs": "SELECT grantee, table_name, privilege, grantable, grantor FROM dba_tab_privs WHERE owner='OW_BILLING' ORDER BY 1,2,3",
 "sys_privs_users": "SELECT p.grantee, p.privilege, p.admin_option FROM dba_sys_privs p WHERE p.grantee IN (SELECT username FROM dba_users WHERE oracle_maintained='N') ORDER BY 1,2",
 "role_privs_users": "SELECT r.grantee, r.granted_role, r.admin_option FROM dba_role_privs r WHERE r.grantee IN (SELECT username FROM dba_users WHERE oracle_maintained='N') ORDER BY 1,2",
 "users": "SELECT username, account_status, created, profile, common FROM dba_users WHERE oracle_maintained='N' ORDER BY 1",
 "policies": "SELECT object_owner, object_name, policy_name, function, enable FROM dba_policies WHERE object_owner='OW_BILLING'",
 "redaction": "SELECT object_owner, object_name, policy_name, enable FROM redaction_policies WHERE object_owner='OW_BILLING'",
 "logging": "SELECT log_mode, supplemental_log_data_min, supplemental_log_data_pk, supplemental_log_data_all, current_scn FROM v$database",
 "tab_logging": "SELECT owner, table_name, log_group_name, log_group_type, always FROM dba_log_groups WHERE owner='OW_BILLING' ORDER BY 2",
 "dbz_user": "SELECT username, common, account_status FROM dba_users WHERE username='C##DBZUSER'",
 "identity_cols": "SELECT table_name, column_name, sequence_name, generation_type FROM dba_tab_identity_cols WHERE owner='OW_BILLING'",
 "col_defaults": "SELECT table_name, column_name, data_default FROM dba_tab_columns WHERE owner='OW_BILLING' AND data_default IS NOT NULL ORDER BY 1,2",
 "lobs": "SELECT table_name, column_name FROM dba_lobs WHERE owner='OW_BILLING'",
 "audit_unified": "SELECT COUNT(*) FROM audit_unified_enabled_policies",
}

def dump(name, rows, cols):
    with open(f"{OUT}/{name}.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t"); w.writerow(cols); w.writerows(rows)
    print(f"{name}: {len(rows)} rows")

for name, q in QUERIES.items():
    if os.path.exists(f"{OUT}/{name}.tsv"): continue
    if q is None: continue
    try:
        cur.execute(q)
        rows = [[(str(v).replace("\n", "\\n") if v is not None else "") for v in r] for r in cur.fetchall()]
        dump(name, rows, [d[0] for d in cur.description])
    except Exception as e:
        print(f"{name}: ERR {e}")

cur.execute("SELECT table_name FROM dba_tables WHERE owner='OW_BILLING' ORDER BY 1")
tables = [r[0] for r in cur.fetchall()]
cur.execute("SELECT current_scn FROM v$database"); scn = cur.fetchone()[0]
rows = []
cur.execute("SET TRANSACTION READ ONLY")
cur.execute("SELECT current_scn FROM v$database"); scn = cur.fetchone()[0]
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM ow_billing."{t}"')
    rows.append([t, cur.fetchone()[0], scn])
conn.rollback()
dump("rowcounts", rows, ["TABLE_NAME", "CNT", "SCN"])
cur.execute("SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, table_name, column_id FROM dba_tab_columns WHERE owner='OW_BILLING' ORDER BY table_name, column_id")
dump("columns", [[str(v) if v is not None else "" for v in r] for r in cur.fetchall()], [d[0] for d in cur.description])
conn.close()
