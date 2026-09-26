<!-- Engagement overlay of the plugin's mongo-migration/profiles/oracle.md (plugin 0.3.0), verbatim except the
tol-2 change approved at the wave-1 close (D-011): date_string_to_date params.unparseable=null.
csv_to_array has no equivalent param in recon 0.3.2, so malformed CSV values quarantined by loaders still
grade as diffs (recorded harness gap). merge_canon_rules overrides by exact name, so the spec's date aliases are declared here too (finding from the first tol-2 re-run). Pass this file as --canonicalization. -->
# Source profile: oracle

Data for the `mongo-migration` skill; not a skill.

## source_type

- family: `oracle`
- versions covered: 12c, 18c, 19c, 21c, 23ai (the catalog queries below run on all)
- client tooling: `sqlplus` (Oracle Instant Client); `python-oracledb` for the harness

## access_grants

- Assessment/read tier: `CREATE SESSION`, `SELECT` on in-scope tables (or `SELECT ANY TABLE` only if the DBA insists), and `SELECT_CATALOG_ROLE`; nothing else.
- Prefer a read-only Data Guard standby or a snapshot schema.
- Secret shape: one secret, canonical JSON `{"user":"<user>","password":"<password>","dsn":"<dsn>"}`.
  The accepted legacy forms `user/password/dsn` and `user/password@dsn` emit a deprecation warning.
- Fixture masking: Data Pump `expdp ... REMAP_DATA=schema.table.column:pkg.func`.

Oracle fixture init failures intentionally leave the container unhealthy; use it only when
`mmp_fixture_meta.scripts_failed = 0`. Bare NUMBER foreign-key columns inherit a referenced
identity key's `long` mapping. Citation files are relative to the working directory or workspace.

## type_mappings

| Oracle type | BSON type | Notes |
|---|---|---|
| NUMBER(p,0), p <= 18 | long | int if p <= 9 and the app expects 32-bit |
| NUMBER(p,s), s > 0 or p > 18 | Decimal128 | never double |
| NUMBER (no precision) | Decimal128 | PROPOSED: may be int-safe in practice; verify with a MIN/MAX/scale probe |
| VARCHAR2 / NVARCHAR2 / CHAR | string | CHAR is blank-padded: strip trailing spaces on load, add canonicalization rule |
| DATE | date | seconds precision, no timezone; decide session TZ, normalize to UTC |
| TIMESTAMP | date | BSON date is ms precision; sub-ms digits truncate (canonicalization rule) |
| TIMESTAMP WITH TIME ZONE | date | convert to UTC on load; original TZ is lost unless stored in a sibling field (PROPOSED) |
| TIMESTAMP WITH LOCAL TIME ZONE | date | already UTC |
| CLOB / NCLOB | string | check 16MB document limit; GridFS or truncation decision if exceeded |
| BLOB | binData | check 16MB limit; GridFS decision if exceeded |
| RAW | binData | |
| FLOAT / BINARY_FLOAT / BINARY_DOUBLE | double | binary floats only; NUMBER never maps to double |
| XMLTYPE | string or object | PROPOSED: raw XML string vs parse to subdocument |
| ROWID / UROWID | (none) | known incompatibility, below |

## known_incompatibilities

| Trap | Required decision |
|---|---|
| Empty string IS NULL (`'' = NULL` for VARCHAR2) | target policy: missing field vs null vs empty string; recon rule must match |
| Sequences (`.NEXTVAL`) | ObjectId, a counters collection, or app-generated UUID; per sequence |
| ROWID-based access in app code | rewrite to a real key; the census finds them (`discovery_commands`) |
| PL/SQL packages, triggers, materialized views | per object: app code, aggregation pipeline, Atlas trigger, or retire |
| CONNECT BY hierarchical queries | $graphLookup or embedded tree; per query |
| MERGE statements | bulkWrite with upserts; watch OUTPUT-clause equivalents |
| Analytic/window functions | $setWindowFields (5.0+) or app-side; verify server version |
| DATE arithmetic in days (`date + 1`) | driver-side date math; watch implicit TZ assumptions |
| Case-insensitive comparisons via NLS settings | collation-aware indexes on target, plus a recon canonicalization rule |

## discovery_commands

Catalog views are `ALL_*` (or `DBA_*` if granted).

```sql
-- tables + row estimates
SELECT owner, table_name, num_rows FROM all_tables WHERE owner = :schema ORDER BY num_rows DESC;
-- columns + types
SELECT table_name, column_name, data_type, data_precision, data_scale, nullable, char_used
FROM all_tab_columns WHERE owner = :schema ORDER BY table_name, column_id;
-- constraints (PK/FK/unique) for key strategy + cardinality rules
SELECT c.table_name, c.constraint_name, c.constraint_type, cc.column_name, c.r_constraint_name
FROM all_constraints c JOIN all_cons_columns cc ON c.constraint_name = cc.constraint_name AND c.owner = cc.owner
WHERE c.owner = :schema AND c.constraint_type IN ('P','R','U') ORDER BY c.table_name, cc.position;
-- indexes
SELECT index_name, table_name, uniqueness, index_type FROM all_indexes WHERE owner = :schema;
-- PL/SQL inventory
SELECT object_name, object_type, status FROM all_objects
WHERE owner = :schema AND object_type IN ('PACKAGE','PACKAGE BODY','PROCEDURE','FUNCTION','TRIGGER','MATERIALIZED VIEW');
-- proc/package dependencies (wave planning)
SELECT name, type, referenced_name, referenced_type FROM all_dependencies
WHERE owner = :schema AND referenced_owner = :schema;
-- sequences
SELECT sequence_name, last_number, increment_by FROM all_sequences WHERE sequence_owner = :schema;
-- ROWID usage in stored code (trap detection)
SELECT DISTINCT name, type FROM all_source WHERE owner = :schema AND UPPER(text) LIKE '%ROWID%';
-- scheduler jobs
SELECT job_name, job_type, job_action, enabled FROM all_scheduler_jobs WHERE owner = :schema;
```

## offline_discovery

When there is no source connectivity, the census comes from files and the
`discovery_commands` above are not run. Use the `schema-modeling` skill
(`skills/schema-modeling/ddl_census.py`); this section says what those files can and cannot
establish.

Accepted inputs (either or both):

| Input | Dialect the parser expects |
|---|---|
| Hand-written DDL and seed scripts | SQL*Plus: `SET`, `WHENEVER`, `PROMPT`, `@file`, `/` terminators, unquoted identifiers, inline `--` column comments |
| `DBMS_METADATA.GET_DDL` dump | quoted `"OWNER"."TABLE"`, `VARCHAR2(36 BYTE)`, `NUMBER(4,0)`, `NOT NULL ENABLE`, storage/LOB clauses, `ENABLE NOVALIDATE`, `COMMENT ON COLUMN` |

How to produce the optional dump, read-only, by someone inside the customer network:

```sql
SET LONG 2000000 LONGCHUNKSIZE 2000000 PAGESIZE 0 LINESIZE 32767 TRIMSPOOL ON
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);
SPOOL schema_ddl.sql
SELECT DBMS_METADATA.GET_DDL(object_type, object_name, owner)
FROM all_objects WHERE owner = :schema
  AND object_type IN ('TABLE','INDEX','SEQUENCE','TRIGGER','VIEW','MATERIALIZED_VIEW','PACKAGE','PROCEDURE','FUNCTION');
SELECT DBMS_METADATA.GET_DEPENDENT_DDL('REF_CONSTRAINT', table_name, owner) FROM all_tables WHERE owner = :schema;
SPOOL OFF
```

| From the files: FACT | Only PROPOSED (needs data or app evidence) |
|---|---|
| tables, columns, Oracle types, NOT NULL, defaults | row counts, table sizes, document-size risk |
| primary, unique, foreign keys, `ON DELETE` action, check constraints | FK fan-out: every relationship is `1:N` with `cardinality_basis: assumed`; `1:1` only when the FK columns are themselves unique (`derived_from_unique_constraint`) |
| indexes, sequences, trigger names and the table they fire on | what triggers, packages and jobs do (names only; each is an `unresolved` row) |
| PL/SQL unit names, scheduler job names and intervals | access patterns: read-together vs written-separately |
| seed `INSERT` counts (reference data only) | null rates, value domains, whether unenforced `*_ID` pointers resolve |
| traps visible in names and types: `*_YN` flags, `*_CSV`/`*_IDS` lists, `DD-MON-YY` text dates, `ADDR_LINE_1..6` repeating groups, `*_HIST` copies, EAV tables, `CODES` lookups | which trap columns are actually populated |

Recon in this mode: `source_access: ddl_only`. The harness runs against a local fixture only;
a fixture PASS proves the spec and load code, never production parity. The customer runs
LIVE or SNAPSHOT recon inside their network before STOP C. No MCP server is started and no
Atlas URI is read; `skills/schema-modeling/offline_guard.py` enforces both.

## conversion_patterns

- `MERGE INTO t USING s ...` -> `collection.bulkWrite([...ReplaceOne/UpdateOne(upsert=true)])`
- `CONNECT BY PRIOR id = parent_id` -> `$graphLookup` (reference model) or embed the tree at load time (embed model)
- `ROW_NUMBER() OVER (PARTITION BY ...)` -> `$setWindowFields` with `$documentNumber`
- `SELECT ... FOR UPDATE` -> `findOneAndUpdate` or transactions; flag long-held-lock patterns
- `NVL(x, y)` -> `$ifNull: [x, y]`; `DECODE` -> `$switch`
- Sequence-keyed inserts -> ObjectId where no external consumer needs the numeric key; otherwise a counters collection with `findOneAndUpdate` `$inc`
- PL/SQL bulk collect loops -> aggregation pipeline or driver bulk reads; do not port row-at-a-time cursors

## recon_canonicalization

The harness `rules` array:

```json
[
  {"rule": "decimal_round", "applies_to": "NUMBER->Decimal128", "params": {"mode": "half_even"}},
  {"rule": "datetime_utc_truncate_ms", "applies_to": "DATE,TIMESTAMP*->date", "params": {"precision": "ms"}},
  {"rule": "rstrip_spaces", "applies_to": "CHAR->string", "params": {}},
  {"rule": "empty_string_is_null", "applies_to": "VARCHAR2,NVARCHAR2,CHAR->string", "params": {"target_policy": "SET_AT_STOP_A"}},
  {"rule": "null_missing_equiv", "applies_to": "*", "params": {"policy": "SET_AT_STOP_A"}},
  {"rule": "collation_casefold", "applies_to": "string", "params": {"enabled_if": "NLS case-insensitive comparisons found in census"}},
  {"rule": "yn_to_bool", "applies_to": "CHAR(1) *_YN->bool", "params": {}},
  {"rule": "csv_to_array", "applies_to": "VARCHAR2 *_CSV,*_IDS->array", "params": {"delimiter": ",", "drop_empty": true}},
  {"rule": "date_string_to_date", "applies_to": "VARCHAR2 *_DT holding text dates; DD-MON-YY confirmed at STOP A; tol-2 (D-011): unparseable text dates are quarantined by loaders, so the grader maps them to null (== missing under null_missing_equiv)", "params": {"format": "%d-%b-%y", "unparseable": "null"}},
  {"name": "date_string_to_date:dby-b3d57e", "rule": "date_string_to_date", "applies_to": "spec alias for DD-MON-YY text dates (map-draft-2); tol-2 unparseable->null", "params": {"format": "%d-%b-%y", "unparseable": "null"}},
  {"name": "date_string_to_date:dbyHMS-30dd8b", "rule": "date_string_to_date", "applies_to": "spec alias for DD-MON-YY HH24:MI:SS history timestamps (map-draft-2); tol-2 unparseable->null", "params": {"format": "%d-%b-%y %H:%M:%S", "unparseable": "null"}}
]
```

## mcp_delegation

Every concern is `reasoning`: no MCP tool is called for Oracle. In `offline_discovery` mode
this is a requirement, not a default; the plugin ships no MCP configuration.

| Concern | Owner |
|---|---|
| schema analysis / census | reasoning |
| mapping proposal | reasoning |
| data movement | reasoning (mongoimport or driver bulk load, per size tier) |
| sync / CDC | reasoning (decision at STOP B) |
| verification tiers 1-3 | reasoning (harness) |
| app-level parity (tier 4) | reasoning (harness), never delegated |
