# Legacy data migration: binding cross-unit contract

Status: **binding**. Five units (source, job, azure, app, ops) implement against this file without
talking to each other. Where this file and any other document disagree, this file wins; where this
file is silent, the unit that owns the path decides and documents the choice in its own README.
Changes to this file are made only on `demo/legacy-data-migration` in a commit whose subject starts
with `contract:` (§15).

Keywords: **MUST**, **MUST NOT**, **MAY** as in RFC 2119. Offsets are 1-based and inclusive.
"Token" always means the namespace token `<run>-<state>`, e.g. `d24-after`.

Companion files (also binding, owned as noted):

| File | Content |
|---|---|
| `migration/manifest.yaml`, `migration/manifests/*.yaml` | real d24 manifest + overlays (§4) |
| `migration/source/db2/ddl/*.sql` | Db2 source DDL (§5.1) |
| `migration/source/copybooks/*.cpy`, `FIELD-DERIVATION.md` | record layouts, byte offsets (§5.3) |
| `migration/source/seed/SEED-SPEC.md` | deterministic seed + planted failures (§5.5) |
| `demos/app/complexity-manifest.json` | MIG-01..07 register (§5.5) |
| `migration/target/sql/*.sql` | Azure SQL schema (§6) |

---

## 1. Conventions shared by every unit

1. Branch: all work merges into `demo/legacy-data-migration`. Units branch from it
   (`devin/<ts>-ldm-<unit>-<slug>`) and open PRs **into it**, never into `main`. `main` is the golden
   app and is not modified (AGENTS.md); `services/admin-service/config/environments/production.rb`
   is never touched; planted golden-app bugs are not fixed.
2. No customer, requester, or organization-identifying names anywhere (files, names, commits, PRs).
   Say "the demo" / "the presenter". Owner tag value is always `otterworks-demo`.
3. No secrets in git. Secrets come from AWS Secrets Manager, Kubernetes Secrets created by
   scripts, or Azure Key Vault. Never print secret values in logs or transcripts.
4. Python: 3.12. Java in `services/report-service`: stays source/target **1.8**, Spring Boot 2.5.x.
   .NET in `services/audit-service`: `net8.0`. Terraform: >= 1.6, providers pinned with `~>`,
   `terraform fmt -check` and `terraform validate` clean.
5. Every cloud or cluster object is created only by Terraform or the ops deploy script, carries the
   token in its name, and carries the tags/labels of §3.3. Kubernetes never creates AWS resources
   (no `LoadBalancer` Services except the existing shared ingress-nginx, no dynamic EBS provisioning).
6. Timestamps in APIs and logs are UTC ISO-8601 with `Z`. Db2 `TIMESTAMP(12)` values, wherever
   shown to a person or hashed, use the Db2 text form `YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN`.
7. Decimal values in JSON/CSV are **strings** with exactly 8 fraction digits (`"2600.12345678"`).

## 2. Directory layout and ownership

A unit MAY create or change files only under the paths it owns. Anything outside its paths is
read-only for it; if a change there is needed, it states the need in its PR description.

| Unit | Owns (paths) | Delivers |
|---|---|---|
| **source** | `migration/source/**`, `infrastructure/helm/db2-archive/**`, `demos/app/complexity-manifest.json` | Db2 DDL, seed generator + loader, copybooks, COBOL `UNLOAD01` program + JCL + `run.sh` (GnuCOBOL), Db2 Helm chart, MIG-06 fixture, complexity register |
| **job** | `migration/job/**`, `migration/target/sql/**`, `infrastructure/helm/migration-job/**` | Python 3.12 package `ldm` (all stages), Dockerfile, tests, type map, Azure SQL DDL, Kubernetes Job chart |
| **azure** | `infrastructure/terraform/azure/**` | per-namespace Azure target (§11) |
| **app** | `services/report-service/**`, `services/audit-service/**`, `frontend/admin-dashboard/**` (named `services/admin-dashboard/**` in the brief; that path does not exist) | reconciliation report endpoints (§10), admin page, archive read path switch (§10.4) |
| **ops** | `scripts/deploy-demo.sh`, `scripts/demo-destroy.sh`, `scripts/demo-reaper.sh`, `Makefile` targets `demo-up` / `demo-migrate` / `demo-destroy` / `demo-verify-clean`, `.github/workflows/demo-reaper.yml`, `docs/demos/legacy-data-migration.md`, `infrastructure/terraform/demo-aws/**`, `docs/demos/**` | deploy / migrate / destroy / verify / reaper, demo AWS resources, presenter runbook + evidence |

Shared (any unit, append-only, one file per unit): `migration/sessions/<unit>.yaml` (§10.3).
The architect owns `migration/README.md`, `migration/CONTRACTS.md`, `migration/manifest.yaml`,
`migration/manifests/**`; units propose changes via their PR description.

Layout (directories exist with a one-line README):

```
migration/
  README.md  CONTRACTS.md  manifest.yaml
  manifests/{d24-before,d24-after}.yaml
  sessions/<unit>.yaml
  source/
    db2/ddl/0NN_*.sql                     # §5.1 (exists)
    copybooks/{DOCARCH,FILEAUD,RETNPLCY}.cpy, FIELD-DERIVATION.md
    seed/  SEED-SPEC.md, __init__.py, __main__.py, load.sh, fixtures/mig06_prior_run.sql
    unload/ UNLOAD01.cbl, UNLOAD01.jcl, run.sh, Makefile
  job/
    Dockerfile  pyproject.toml
    ldm/        __main__.py ...           # §9
    typemaps/db2-to-azuresql.yaml         # §8
    tests/
  target/sql/0NN_*.sql                    # §6 (exists)
infrastructure/
  helm/db2-archive/                       # §13.1
  helm/migration-job/                     # §13.2
  terraform/azure/                        # §11
  terraform/demo-aws/                     # §12.4
demos/app/complexity-manifest.json
docs/demos/legacy-data-migration.md
```

## 3. Namespacing

### 3.1 Token

`NS` MUST match `^[a-z][a-z0-9]{1,11}-(before|after)$`. `RUN = NS` before the last `-`,
`STATE = before|after`. The demo tokens are `d24-before` and `d24-after`. Tokens `main`, `main-*`
are never used. Every entry point (ldm, Terraform, scripts, Make) validates the token and fails
(ldm: exit 4; scripts: exit 2) before touching anything.

### 3.2 Derived names (all units MUST use exactly these)

| Object | Name for `NS=d24-after` | Rule |
|---|---|---|
| Kubernetes namespace | `otterworks-d24-after` | `tenant_namespace NS` (scripts/lib/tenant-common.sh) |
| App hosts | `t-d24-after.otterworks.app`, `api-t-d24-after.otterworks.app` | existing tenant rule |
| Postgres app DB | `otterworks_d24_after` | `tenant_db_name NS` |
| Db2 database name | `D24A` (before: `D24B`) | `upper(RUN[0:7]) + ("B" if before else "A")` (Db2 names are max 8 chars; isolation comes from the namespace) |
| Db2 Helm release / StatefulSet / Service | `db2-archive` in the tenant namespace; Service DNS `db2-archive.otterworks-d24-after.svc.cluster.local:50000` | fixed name, namespaced |
| Db2 EBS volume / PV | `otterworks-ldm-d24-after-db2` | ops Terraform (§12.4) |
| S3 bucket | `otterworks-ldm-d24-after-599083837640`, prefix `d24-after/` | ops Terraform |
| ECR repository for the job image | `otterworks-demo/d24-after/ldm-job` | ops Terraform |
| Azure resource group | `rg-otterworks-d24-after` | azure |
| SQL logical server | `sql-otterworks-d24-after` (FQDN `sql-otterworks-d24-after.database.windows.net`) | azure |
| SQL database | `sqldb-otterworks-d24-after` | azure |
| Storage account | `stow` + `NS` without `-` + 3 hex of `md5(subscription_id)` (<= 24 chars) | azure (global uniqueness) |
| Staging container | `staging-d24-after` | azure |
| Key Vault | `kvow` + `NS` without `-` + 2 hex of `md5(subscription_id)` (<= 24 chars) | azure |
| Managed identity | `id-otterworks-d24-after` | azure |
| Container Apps env | `cae-otterworks-d24-after` | azure |
| Container Apps | `ca-report-d24-after`, `ca-audit-d24-after` | azure |
| Container Apps job | `caj-ldm-d24-after` | azure |
| Terraform state (Azure) | backend `azurerm`; account / RG / container come from env `TFSTATE_AZ_ACCOUNT`, `TFSTATE_AZ_RESOURCE_GROUP`, `TFSTATE_AZ_CONTAINER` (the existing shared state account, supplied by the environment, not committed); key `otterworks/d24-after/terraform.tfstate` | azure + ops |
| Terraform state (AWS demo) | bucket `otterworks-terraform-state`, key `otterworks/demo/d24-after/terraform.tfstate` | ops |
| Kubernetes Job | `ldm-<stage>-<run_id>` (truncated to 63) | job chart |

`d24-before` gets the Kubernetes namespace, Db2, S3 bucket and ECR repo; it gets **no** Azure
objects and no Azure state file.

### 3.3 Tags and labels

Azure (every taggable resource, including the resource group) and AWS (every resource, via provider
`default_tags` plus explicit tags where default_tags do not apply) carry exactly these four keys:

| Key | Value |
|---|---|
| `namespace` | the token, e.g. `d24-after` |
| `owner` | `otterworks-demo` |
| `demo` | `legacy-data-migration` |
| `expires` | absolute UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` |

Additional tags MAY be added only by the owning unit; these four MUST NOT be renamed. Kubernetes
objects created by the new charts carry labels `demo/namespace: <token>`,
`demo/name: legacy-data-migration`, `app.kubernetes.io/part-of: otterworks-ldm` plus the namespace
labels `deploy-tenant.sh` already applies (`demo/expires-at` annotation on the namespace).

## 4. Manifest

### 4.1 Resolution

`ldm` receives `--manifest <base>` and `--namespace <NS>`. It loads the base, then the overlay
`<dir(base)>/manifests/<NS>.yaml`, and deep-merges overlay over base (maps merge, lists replace).
Errors, all exit 4: overlay missing; `overlay.namespace != NS`; `overlay.extends` does not resolve to
the given base; `run_token` != `RUN`; the base contains `purge`, `migrate`, `azure` or `execution`;
`migrate: false` (the BEFORE namespace is never migrated); unknown top-level key; a column named in
`key_columns`, `hash_columns`, `selection`, `class_totals` or `type_overrides` that is not a value of
`field_map`.

### 4.2 Schema (base: `migration/manifest.yaml`)

| Path | Type | Req | Meaning |
|---|---|---|---|
| `schema_version` | int | yes | `1` |
| `run_token` | string | yes | `RUN` part of every token this base serves; a throwaway overlay (`<x>-after`) MAY override it with its own `RUN` part |
| `source.driver` | enum `db2` | yes | selects the source adapter in `ldm` |
| `source.connection_env.{host,port,database,user,password}` | env var names | yes | §9.2 |
| `source.unload_command` | list of strings | yes | argv template; placeholders `{table}`, `{key_from}`, `{key_to}`, `{out_file}`, `{namespace}`, `{run_id}` |
| `source.copybook_dir` | path (repo-relative) | yes | where `tables[].copybook` lives |
| `source.record_format.recfm` | enum `F` | yes | fixed-length records, no terminator |
| `source.record_format.text_encoding` | codec name | yes | codec of non-bit-data `CHAR` (`ascii`) |
| `source.record_format.bit_data_encoding` | codec name | yes | default codec when a `FOR BIT DATA` column is converted to text (`cp037`) |
| `target.provider` | enum `azuresql` | yes | selects the target adapter |
| `target.connection_env.{server,database,user,password,auth_mode,managed_identity_client_id}` | env var names | yes | §9.2 |
| `target.ddl_dir` | path | yes | applied in file-name order at `ldm init` |
| `target.typemap` | path | yes | default type map (§8) |
| `staging.connection_env.{storage_account,container,local_dir}` | env var names | yes | §9.2 |
| `staging.blob_prefix` | template | yes | `{namespace}/{run_id}/` |
| `batch.extract_range_rows` | int > 0 | yes | rows per key range = per unload file |
| `batch.load_batch_rows` | int > 0 | yes | rows per staging insert batch |
| `batch.validate_batch_rows` | int > 0 | yes | rows per hash-compare batch |
| `batch.purge_batch_rows` | int > 0 | yes | keys per purge unit of work |
| `selection_sets.<name>` | list of strings | yes | named value sets referenced by `tables[].selection.retention_classes` |
| `report.sessions_glob` | glob | yes | session link files (§10.3) |
| `report.issue_register` | path | no | complexity register used only to annotate the report |
| `tables[]` | list | yes | processed in `order` ascending (EXTRACT/LOAD/VALIDATE), descending for PURGE |
| `tables[].name` | string | yes | Db2 table name without schema; also the `stg.`/`arch.` table name |
| `tables[].schema` | string | yes | Db2 schema |
| `tables[].role` | enum `data`, `reference` | yes | `reference` tables are migrated and validated but never purged |
| `tables[].order` | int | yes | unique |
| `tables[].copybook` | file name | yes | in `source.copybook_dir` |
| `tables[].record_length` | int | yes | LRECL; MUST equal the copybook length |
| `tables[].field_map` | map copybook-name -> Db2 column | yes | every non-FILLER elementary item, in copybook order |
| `tables[].key_columns` | list | yes | unique key; `source_key` = these columns' raw text joined by `|` (single column: the raw CHAR text **with padding**) |
| `tables[].hash_columns` | list | yes | ordered column list for the business hash (§7) |
| `tables[].selection` | map | yes | one of the forms in §4.3 |
| `tables[].class_totals` | map | data tables | §9.4.3 |
| `tables[].type_overrides.<COL>` | map | no | `target_type` (SQL type text), `trim` (`none`/`right`), `encoding` (codec), `format` (`YYYYMMDD`), `value_map` (map) |

Overlay (`migration/manifests/<NS>.yaml`):

| Path | Type | Req | Meaning |
|---|---|---|---|
| `namespace` | token | yes | MUST equal the file name stem |
| `extends` | path | yes | relative to the overlay, `../manifest.yaml` |
| `migrate` | bool | yes | `false` => ldm refuses to run (exit 4); ops never provisions Azure |
| `azure` | bool | yes | whether ops provisions `infrastructure/terraform/azure` for this token; `migrate: true` requires `azure: true` |
| `purge` | bool | yes | **only** place the purge flag may appear. `false` or absent => PURGE is a dry run |
| `execution.run_job_in_azure` | bool | no (default false) | §9.5 |
| `batch.*` | ints | no | overrides base batch sizes |

### 4.3 Selection forms

- `{all: true}` - every row.
- Predicate form (DOCARCH, FILEAUD):
  `class_column IN selection_sets[retention_classes] AND last_access_column < last_access_before`.
  EXTRACT MUST generate it from the manifest (bound parameters or quoted literals), e.g.
  `WHERE RETENTION_CLASS IN ('FIN7',...) AND LAST_ACCESS_TS < TIMESTAMP('2019-01-01-00.00.00.000000000000')`.
  Nothing in `ldm` hard-codes classes or dates.
- `parent: {table, columns, references}` (FILEAUD) - declares the FK used by VALIDATE (§9.4.3). It
  does **not** change what EXTRACT selects: children are selected by their own predicate, which is
  why orphans (MIG-05) are extracted, loaded and then rejected.

The d24 values (`closed-7y`, cutoff `2019-01-01-00.00.00.000000000000`) select exactly
40 / 180,000 / 620,000 rows from the seed (SEED-SPEC §3). The `RETENTION_CLASS.value_map` in the
base manifest is **planted test data for MIG-07**; implementers MUST NOT correct it.

## 5. Source (Db2) contract

### 5.1 DDL

Files `migration/source/db2/ddl/010..050_*.sql`, Db2 11.5 LUW, `db2 -tvf`, applied in name order to
the namespace's database created `USING CODESET UTF-8 TERRITORY US`:

| File | Object |
|---|---|
| `010_schemas.sql` | schemas `ARCHIVE`, `MIGAUDIT` |
| `020_archive_retnplcy.sql` | `ARCHIVE.RETNPLCY` (PK `POLICY_CODE`) |
| `030_archive_docarch.sql` | `ARCHIVE.DOCARCH` (PK `ARCH_KEY`, FK `RETENTION_CLASS` -> RETNPLCY) |
| `040_archive_fileaud.sql` | `ARCHIVE.FILEAUD` (PK `AUDIT_KEY`, FK `ARCH_KEY` -> DOCARCH, `ON DELETE RESTRICT`) |
| `050_migaudit_purge_audit.sql` | `MIGAUDIT.PURGE_AUDIT (RUN_ID, TABLE_NAME, SOURCE_KEY, PURGED_AT)` |

Db2 concerns carried by the schema: every text column is fixed `CHAR(n)` (blank-padded);
`STORAGE_CHARGE`/`UNIT_RATE` are `DECIMAL(31,8)`; `LAST_ACCESS_TS`/`EVENT_TS`/`EFFECTIVE_TS` are
`TIMESTAMP(12)`; `DOCARCH.OWNER_NAME CHAR(40) FOR BIT DATA` and `DOCARCH.DISPOSITION_DT CHAR(8) FOR BIT
DATA` hold **EBCDIC CCSID 037** bytes (catalog `CODEPAGE = 0`; Db2 performs no conversion, so the
bytes survive UNLOAD unchanged). All columns are `NOT NULL`.

Errors from Db2 MUST be surfaced with SQLCODE and SQLSTATE: every `ldm` log line and every
`mig.rejects` / `mig.stage_log` message that stems from a Db2 error starts with
`SQLCODE=<n> SQLSTATE=<s>: ` (ibm_db `stmt_errormsg` / `conn_errormsg` text follows).

### 5.2 Database per namespace

One Db2 instance (`db2inst1`) per tenant namespace, one database (§3.2 name) per instance. The same
DDL and the same seed files (identical SHA-256, SEED-SPEC §1) are loaded into `D24B` and `D24A`.
Db2 credentials: Kubernetes Secret `db2-archive-credentials` in the tenant namespace, keys
`DB2_USER`, `DB2_PASSWORD` (created by ops from a generated value; never committed).

### 5.3 Fixed-width record layouts

Byte-exact layouts and offsets are in `migration/source/copybooks/FIELD-DERIVATION.md` §2-4
(DOCARCH LRECL 256, FILEAUD 160, RETNPLCY 128; verified with GnuCOBOL 3.1 `LENGTH OF`). Encoding
rules (FIELD-DERIVATION §5, binding): `PIC X` text right-padded `X'20'`; `FOR BIT DATA` raw bytes;
`TIMESTAMP(12)` as 32 ASCII chars; `COMP` big-endian two's complement; `COMP-3` packed, 16 bytes,
sign nibble `C`/`D` (`F` accepted); `FILLER` spaces; RECFM=F, no terminators.
`DOCARCH.cpy` keeps its terse, uncommented names; meaning comes only from FIELD-DERIVATION.md and
the manifest `field_map`.

### 5.4 UNLOAD01 (COBOL) and `run.sh`

`migration/source/unload/run.sh <TABLE> <KEY_FROM> <KEY_TO> <OUT_FILE>` is the manifest
`unload_command`. Contract:

1. Writes to `OUT_FILE` every row of `ARCHIVE.<TABLE>` that satisfies the table's selection
   predicate **and** `KEY_FROM <= key <= KEY_TO`, ordered by key ascending, in the copybook layout.
   The predicate is passed in by `ldm` through env `LDM_SELECT_WHERE` (a complete SQL boolean
   expression, e.g. `RETENTION_CLASS IN ('FIN7') AND LAST_ACCESS_TS < TIMESTAMP('...')`, or `1=1`).
2. Implementation: `db2 EXPORT ... OF DEL` / `db2 "SELECT ..."` into a work file, then the GnuCOBOL
   program `UNLOAD01` (built by `make -C migration/source/unload`, `cobc -x`) formats the fixed-width
   records using the copybook via `COPY`. `UNLOAD01.jcl` documents the equivalent z/OS job
   (DSNTIAUL-style) in the demo-mainframe-batch style; it is not executed.
3. stdout, last line exactly: `UNLOAD01 ROWS=<n> BYTES=<n*LRECL> SHA256=<hex>`.
4. Exit 0 on success; 8 on a Db2 error (message line `SQLCODE=<n> SQLSTATE=<s>: ...` on stderr);
   12 on I/O error. It never deletes or updates Db2 rows.

`ldm` treats the unload command as opaque; a different source (Oracle, ...) changes only
`source.driver`, `unload_command`, `copybook_dir` and the type map.

### 5.5 Seed and failure register

`SEED-SPEC.md` is binding for the source unit (exact generator, counts, planted keys, MIG-06
fixture). `demos/app/complexity-manifest.json` lists the seven classes with `id`, `title`, `table`,
`planted_keys`, `expected_stage`, `expected_rule` (+ `expected_field`, `expected_sqlstate`,
`expected_count`, `headline`). Rule strings in it are the exact `rule` values the job writes.
Application code MUST NOT read it; `ldm` MAY read it only via `report.issue_register` to add an
`issue` column to report failure rows.

## 6. Target schema

### 6.0 Providers

`target.provider` in the manifest selects the driver: **`postgresql` (default)** or `azuresql`
(optional, overlays such as `manifests/r2-after.yaml`). Both apply the same logical schema (`mig`,
`stg`, `arch`, views, reader role) and the same stage semantics; only the SQL dialect differs.

**PostgreSQL** (`migration/target/postgresql/000..100_*.sql`, plain SQL, idempotent, applied by
`ldm init` in name order, each recorded in `mig.schema_version`). The target is the tenant's
**existing** `otterworks_<ID>` database on the shared RDS instance (§ AGENTS.md); the job only adds
the three schemas, so no additional database or server is provisioned. Dialect notes:

- Db2 `TIMESTAMP(12)` maps to `<COL> TIMESTAMP(6)` (fraction digits 1-6) plus
  `<COL>_NANOS_TAIL INTEGER` holding digits 7-12 (`0..999999`, `CHECK`ed). PostgreSQL has no
  7-digit timestamp, so the split point differs from Azure SQL (7 + 5) but the mapping stays
  lossless: `2016-03-01-10.15.30.123456789012` -> `2016-03-01 10:15:30.123456` + `789012`, and every
  reader (job, report-service, audit-service) rebuilds the 32-char Db2 text from the pair.
- `raw_bytes`/`row_hash` are `BYTEA`; `NVARCHAR` -> `VARCHAR`, `DECIMAL` -> `NUMERIC`, `INT` ->
  `INTEGER`, `TINYINT` -> `SMALLINT`, `DATETIME2` -> `TIMESTAMP`.
- Key and range-boundary text columns are `COLLATE "C"` so `ORDER BY`/`BETWEEN` on keys is byte
  order, matching Db2 and the job's Python range arithmetic.
- `mig.rejects.rule_name` keeps the T-SQL-safe spelling so both providers share the report views.
- Target-side hashing uses the built-in `sha256(bytea)` (PostgreSQL >= 11, no extension).
- Duplicate key = SQLSTATE `23505`; the loader bisects a failed batch so one bad row becomes one
  `mig.rejects` row (`DUPLICATE_SOURCE_KEY` or the target's message) instead of failing the batch.

**Azure SQL** files `migration/target/sql/000..100_*.sql` (T-SQL, idempotent, batches separated by a line
`GO`; applied by `ldm init` in name order, each recorded in `mig.schema_version`). Verified against
SQL Server 2022 (applied twice). Columns are defined in the files; summary:

| Object | Key | Written by | Purpose |
|---|---|---|---|
| `mig.schema_version` | `file_name` | init | applied DDL files |
| `mig.runs` | `(run_id, namespace)` | all stages; RECONCILE sets `status`, `closes`, `exit_code`, `finished_at` | one row per run |
| `mig.run_sessions` | `(run_id, namespace, ordinal)` | RECONCILE | session links (§10.3) |
| `mig.run_ledger` | `(run_id, namespace, table_name)` | each stage **only** its columns: EXTRACT `extracted, extract_files`; LOAD `loaded, rejected`; VALIDATE `validated, validate_failed`; PURGE `purge_intended, purged, purge_dry_run`; first stage inserts `table_order, table_role` | counts |
| `mig.stage_log` | identity | every stage | per-stage/per-table timing (`host` = `eks`/`aca`/`local`) |
| `mig.key_ranges` | `(run_id, namespace, table_name, range_seq)` | EXTRACT (ranges, file sha/rows), LOAD (`load_status`) | restart unit |
| `mig.rejects` | identity; unique `(run_id, namespace, table_name, source_key)` | LOAD, VALIDATE | failed rows: `rule_name`, `field`, `sqlstate`, `native_error`, `error`, `raw_bytes`, `field_bytes` |
| `mig.validation` | `(run_id, namespace, table_name, source_key)` | VALIDATE | per key: hashes, `status`, `rule_name`, `purge_safe` |
| `mig.class_totals` | `(run_id, namespace, table_name, class_code, side)` | VALIDATE | per-class counts and sums, both sides |
| `mig.purge_audit` | `(run_id, namespace, table_name, source_key)` | PURGE | Azure mirror of Db2 purge audit |
| `stg.RETNPLCY/DOCARCH/FILEAUD` | `(run_id, namespace, source_key)`; unique `(namespace, source_key)` | LOAD | provenance (`source_key`, `range_seq`, `batch_id`, `raw_bytes VARBINARY(MAX)`, `row_hash`) + converted columns named as in Db2 |
| `arch.RETNPLCY/DOCARCH/FILEAUD` | Db2 PK | VALIDATE (promotion) | migrated rows + `source_key`, `row_hash`, `namespace`, `migrated_run_id`, `migrated_at` |
| `mig.v_reconciliation_tables` | view | - | report table rows + per-table `closes` |
| `mig.v_reconciliation_failures` | view | - | report failure rows |
| role `ldm_report_reader` | - | init | `SELECT` on `mig`, `arch` |

Column naming: the report JSON key `rule` is stored as `rule_name` (`RULE` is reserved in T-SQL).
`TIMESTAMP(12)` columns map to `<COL> DATETIME2(7)` (fraction digits 1-7) plus
`<COL>_NANOS_TAIL INT` (digits 8-12, 0..99999). Example: `2016-03-01-10.15.30.123456789012` ->
`2016-03-01T10:15:30.1234567` + `89012`.

Run status: `RUNNING` (set by the first stage of a run), `CLOSED` (RECONCILE, closes = 1),
`FAILED` (any stage exited non-zero, or RECONCILE closes = 0), `ABANDONED` (fixture only).

Expected d24-after counts (the acceptance numbers; SEED-SPEC §3):

| table | extracted | loaded | rejected | validated | validate_failed | purged | failed (report) |
|---|---:|---:|---:|---:|---:|---:|---:|
| RETNPLCY | 40 | 40 | 0 | 40 | 0 | 0 | 0 |
| DOCARCH | 180,000 | 179,980 | 20 | 179,963 | 17 | 179,963 | 37 |
| FILEAUD | 620,000 | 620,000 | 0 | 619,995 | 5 | 619,995 | 5 |

## 7. Business hash

`row_hash = SHA-256( UTF-8( render(c1) || '|' || render(c2) || ... ) )` over the table's
`hash_columns` **in manifest order**, stored as `BINARY(32)`, shown as uppercase hex. The same column
list is used on both sides. Source side renders from the extracted fixed-width record (after
decoding and after `value_map`); target side renders from the `stg.<T>` converted columns.

The target expression is generated per provider by `ldm.hashing.hash_expression()`; the T-SQL form
is tabulated below, the PostgreSQL form uses `sha256(convert_to(e1 || '|' || e2 ..., 'UTF8'))` with
`RPAD`/`RTRIM`, `::numeric(38,8)::text`, `TO_CHAR(ts, 'YYYY-MM-DD-HH24.MI.SS.US') || LPAD(tail, 6)`,
`TO_CHAR(d, 'YYYYMMDD')` and `UPPER(ENCODE(b, 'hex'))`, and must produce byte-identical input.

| Source type (+override) | Source rendering | Target column | Target rendering (T-SQL) |
|---|---|---|---|
| `CHAR(n)`, column **in** `key_columns` | decoded text exactly as stored, **padding kept** | `NCHAR`/`NVARCHAR` | column as-is |
| `CHAR(n)`, column **not** in `key_columns` (incl. `FOR BIT DATA` decoded with its `encoding`) | decoded text, `rstrip(' ')` | `NCHAR`/`NVARCHAR` | `RTRIM(col)` |
| `SMALLINT`, `INTEGER`, `BIGINT` | `str(int)` | integer | `CONVERT(VARCHAR(20), col)` |
| `DECIMAL(p,s)` | fixed 8 fraction digits, `-` only when negative, leading `0` (`0.00000001`, `-12.50000000`) | `DECIMAL` | `CONVERT(VARCHAR(48), CAST(col AS DECIMAL(38,8)))` |
| `TIMESTAMP(12)` | `YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN` as unloaded | `DATETIME2(7)` + `_NANOS_TAIL` | expression below |
| `CHAR(8)` with `format: YYYYMMDD` -> `DATE` | decoded text `YYYYMMDD` | `DATE` | `CONVERT(CHAR(8), col, 112)` |

`value_map` applies before rendering (so a mapped class hashes the same on both sides; MIG-07 is
caught by class totals, not by the hash). MIG-04 follows from row 1: source key
`'MIG04-01        '` vs target `NVARCHAR` `'MIG04-01'` (trimmed by `trim: right`).

Python reference (job unit implements in `ldm/hashing.py`, byte-for-byte this behavior):

```python
from decimal import Decimal
from typing import Literal, Sequence, Tuple
Kind = Literal["char", "int", "decimal", "timestamp12", "date8"]

def render(value: str | int | Decimal, kind: Kind, is_key: bool) -> str:
    if kind == "char":
        return value if is_key else value.rstrip(" ")
    if kind == "int":
        return str(int(value))
    if kind == "decimal":
        return format(Decimal(value).quantize(Decimal("0.00000001")), "f")
    return value            # timestamp12 / date8: already canonical text

def business_hash(cols: Sequence[Tuple[str | int | Decimal, Kind, bool]]) -> bytes:
    import hashlib
    return hashlib.sha256("|".join(render(*c) for c in cols).encode("utf-8")).digest()
```

T-SQL (DOCARCH; generated per table from the manifest by `ldm`, verified equal to the Python
reference on SQL Server 2022):

```sql
HASHBYTES('SHA2_256', CAST(CONCAT_WS(N'|',
    ARCH_KEY,                                           -- key column: no trim
    RTRIM(DOC_ID),
    CONVERT(VARCHAR(20), VERSION_NO),
    RTRIM(RETENTION_CLASS),
    CONCAT(LEFT(CONVERT(CHAR(27), LAST_ACCESS_TS, 121), 10), '-',
           SUBSTRING(CONVERT(CHAR(27), LAST_ACCESS_TS, 121), 12, 2), '.',
           SUBSTRING(CONVERT(CHAR(27), LAST_ACCESS_TS, 121), 15, 2), '.',
           SUBSTRING(CONVERT(CHAR(27), LAST_ACCESS_TS, 121), 18, 2), '.',
           RIGHT(CONVERT(CHAR(27), LAST_ACCESS_TS, 121), 7),
           RIGHT(CONCAT('0000', LAST_ACCESS_TS_NANOS_TAIL), 5)),
    CONVERT(VARCHAR(48), CAST(STORAGE_CHARGE AS DECIMAL(38, 8))),
    CONVERT(VARCHAR(48), CAST(UNIT_RATE AS DECIMAL(38, 8))),
    RTRIM(OWNER_NAME),
    CONVERT(CHAR(8), DISPOSITION_DT, 112),
    RTRIM(LEGAL_HOLD_FLAG),
    RTRIM(CONTENT_SHA256),
    CONVERT(VARCHAR(20), BYTE_SIZE)
) COLLATE Latin1_General_100_BIN2_UTF8 AS VARCHAR(MAX)))
```

Test vector (DOCARCH columns in manifest order): key `MIG04-01` + 8 spaces, DOC_ID
`0f8e1c2a-3b4d-4e5f-8a9b-0c1d2e3f4a5b`, 3, `HRS7`, `2013-02-01-09.30.00.123456789012`,
`1234.50000000`, `-0.00000001`, `LOPEZ, M.` (padded), `20200201`, `N`, `ab`x32, 123456789 ->
source `7AD25FE7BB719301689DAF56882C906759EC2538C42492E99F6309B4B6C15861`; same row with the key
trimmed (target) -> `75213C04D2AAA5D907946F1F4814077BC0CBC7F7C36DEFDF9DF57E1126B51700`.

## 8. Type mapping and conversion (LOAD)

Default type map `migration/job/typemaps/db2-to-postgresql.yaml` (azuresql overlays use
`db2-to-azuresql.yaml`; both carry exactly these rules spelled for their dialect, see §6.0; a
manifest `type_overrides` entry replaces the rule for one column):

| Db2 type | Azure SQL type | Conversion |
|---|---|---|
| `CHAR(n)` | `NCHAR(n)` | decode `text_encoding`; keep padding |
| `CHAR(n) FOR BIT DATA` | `VARBINARY(n)` | bytes as-is (override with `encoding` to get text) |
| `SMALLINT` / `INTEGER` / `BIGINT` | same | `COMP` big-endian |
| `DECIMAL(p,s)` | `DECIMAL(p,s)` | unpack `COMP-3`; exact `Decimal` |
| `TIMESTAMP(12)` | `DATETIME2(7)` + `<COL>_NANOS_TAIL INT` | split fraction 7 + 5 digits, no rounding |
| `DATE` | `DATE` | - |

Override keys: `target_type` (replaces the SQL type; the converted value MUST fit it, checked in
Python before insert), `trim: right` (strip trailing `U+0020` after decoding), `encoding: cp037`
(decode bytes with this codec), `format: YYYYMMDD` (parse to `DATE`), `value_map` (after decoding
and trimming, replace whole values; unmapped values pass through).

Conversion failures (per field, first failing field wins, row goes to `mig.rejects` with
`stage = LOAD`, `raw_bytes` = full record, `field_bytes` = that field's bytes; the batch continues):

| rule_name | Condition | sqlstate | error text (prefix) |
|---|---|---|---|
| `CCSID_UNMAPPABLE` | column has `encoding` and no `format`, and a decoded character is in U+0000-U+001F or U+007F-U+009F (C0/C1 control) | NULL | `CCSID037 byte X'hh' at offset <n>` |
| `DECIMAL_OVERFLOW` | value has more integer digits than `target_type` allows | `22003` | `value <v> exceeds DECIMAL(p,s)` |
| `DATE_INVALID` | column has `format: YYYYMMDD` and its decoded text is not a valid date (incl. all `X'00'` low-values, which are never `CCSID_UNMAPPABLE`); the job passes the text to the target and reports the target error | `22007` | target driver message |
| `DUPLICATE_SOURCE_KEY` | insert into `stg.<T>` violates `UX_stg_<T>_source_key` (SQL Server 2601/2627) | `23000` | target driver message |
| `PACKED_INVALID` | invalid nibble in `COMP-3` | NULL | `invalid packed decimal at offset <n>` |
| `TIMESTAMP_INVALID` | `TIMESTAMP(12)` text does not parse | `22007` | `...` |
| `RECORD_LENGTH` | record length != LRECL (whole file rejected; stage exits 4) | NULL | - |

Batching: rows are inserted `load_batch_rows` at a time in one transaction with `fast_executemany`;
if the batch fails, the job re-inserts that batch row by row, rejecting the failing rows with the
driver's SQLSTATE and native error, and commits the rest. Target errors are recorded as
`sqlstate` = ODBC SQLSTATE, `native_error` = SQL Server error number.

## 9. Job (`ldm`) contract

### 9.1 CLI

```
python -m ldm <extract|load|validate|purge|reconcile|all> --manifest <path> --namespace <token> --run-id <id>
python -m ldm init --manifest <path> --namespace <token> [--apply-sql <file.sql> ...]
```

- `--run-id`: `^[a-z0-9][a-z0-9-]{2,62}$`; ops uses `r<UTC yyyymmddHHMMSS>` (e.g. `r20260924150000`).
  Reusing a run id resumes that run.
- `all` = `extract`, `load`, `validate`, `purge`, `reconcile` in order, stopping at the first
  non-zero exit.
- `init` (additional verb, not a stage): applies `target.ddl_dir` files, creates the reader user
  (`AZSQL_READER_USER` / `AZSQL_READER_PASSWORD`, if set) in role `ldm_report_reader`, then applies
  each `--apply-sql` file after `EXEC sp_set_session_context N'ldm.namespace', <token>`. Idempotent.
  Every stage verb also runs the DDL part of `init` first.
- Output: human log lines on stderr (`<UTC ts> <LEVEL> <stage> <table> <message>`); the last line on
  stdout is one JSON object `{"run_id","namespace","stage","exit_code","tables":{...counts}}`.

### 9.2 Environment

| Var | Used by | Meaning |
|---|---|---|
| `DB2_HOST`, `DB2_PORT`, `DB2_DATABASE`, `DB2_USER`, `DB2_PASSWORD` | extract, purge (and validate for source-side class totals) | Db2 connection (`db2-archive`, `50000`, `D24A`, from Secret `db2-archive-credentials`) |
| `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`, `PG_SSLMODE` | all (`provider: postgresql`) | the tenant's existing RDS database (`otterworks_<ID>`), from the tenant's `postgres-credentials` Secret; `PG_SSLMODE` default `prefer` |
| `S3_STAGING_BUCKET`, `AWS_REGION`, `S3_ENDPOINT_URL` | extract (upload), load (download) | shared staging bucket, keys `<blob_prefix><TABLE>/<range_seq:06d>.dat`; auth from the pod's IRSA role / default chain; endpoint only for MinIO/localstack |
| `AZSQL_SERVER` | all (`provider: azuresql`) | `sql-otterworks-<NS>.database.windows.net` |
| `AZSQL_DATABASE` | all | `sqldb-otterworks-<NS>` |
| `AZSQL_AUTH` | all | `sql` (default) or `managed-identity` |
| `AZSQL_USER`, `AZSQL_PASSWORD` | all when `AZSQL_AUTH=sql` | SQL admin credential (Key Vault secret `azsql-admin-password`, user `ldmadmin`) |
| `AZURE_CLIENT_ID` | all when `AZSQL_AUTH=managed-identity` | client id of the user-assigned identity (`ActiveDirectoryMsi`) |
| `AZSQL_READER_USER`, `AZSQL_READER_PASSWORD` | init | optional contained reader user for the app (§10.4) |
| `AZ_STORAGE_ACCOUNT`, `AZ_STAGING_CONTAINER` | extract (upload), load (download) | staging blobs `<blob_prefix><TABLE>/<range_seq:06d>.dat` |
| `AZ_STORAGE_KEY` or managed identity | same | storage auth (key from Key Vault secret `staging-storage-key`) |
| `LOCAL_STAGING_DIR` | extract, load | local copy, same relative names; default `/work/staging` |
| `LDM_HOST` | all | `eks`, `aca` or `local` (recorded in `mig.stage_log.host`) |
| `LDM_JOB_IMAGE` | all | recorded in `mig.runs.job_image` |

Staging: EXTRACT writes each range to `LOCAL_STAGING_DIR` and uploads it to S3 when
`S3_STAGING_BUCKET` is set, else to Azure Blob when `AZ_STORAGE_ACCOUNT` is set (azuresql
namespaces only), else keeps it local. LOAD reads the local file if present with the recorded
SHA-256, otherwise downloads the object; a SHA-256 mismatch is exit 4. Tenant isolation in the
shared bucket is the `<NS>/<run_id>/` key prefix; teardown deletes that prefix.

LOAD engine (`execution.load_engine`): `serial` (one process, the reference implementation, used by
the unit suite) or `spark` (default for after-namespaces). Spark runs **PySpark local mode inside
the same one-shot Job pod** (`execution.spark.master` must be `local[...]`; scratch under
`LOCAL_STAGING_DIR/spark`; no Spark Service, operator or cluster). Each task reads only its
`records_per_slice` slice of the range file, converts records with the same `convert_record` as
the serial engine, a shuffle on `source_key` resolves duplicates (first well-formed occurrence
wins, later ones `DUPLICATE_SOURCE_KEY`, malformed records keep their own reject), and sink tasks
reopen the target from the picklable `TargetSpec` and return counts only. Both engines must produce
identical `stg` rows, `mig.rejects` and ledger counts for the same input.

### 9.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | stage (or `all`) completed; for `reconcile`, the run closes |
| 1 | unexpected error (uncaught exception, Db2/Azure SQL unreachable) |
| 2 | reconciliation arithmetic failure: some table has `extracted != loaded + rejected`, `loaded != validated + validate_failed`, or `purged != validated` (dry run: `purge_intended != validated`) |
| 3 | purge guard tripped (§9.4.4); nothing from the failing batch is deleted |
| 4 | configuration error (manifest/overlay/token/env/type map invalid, `migrate: false`, copybook length != `record_length`, staging checksum mismatch) |

### 9.4 Stages

#### 9.4.1 EXTRACT (always beside Db2, on EKS)

1. Insert/refresh `mig.runs` (`RUNNING`, `purge_enabled` = overlay `purge`) and `mig.run_ledger` rows.
2. Per table in `order`: compute key ranges of `extract_range_rows` selected keys
   (`SELECT key FROM ... WHERE <predicate> ORDER BY key`, every n-th key as boundary); insert them
   into `mig.key_ranges` as `PLANNED` if the run has none for the table; reuse them otherwise.
3. For each range not `DONE`: set `RUNNING`, invoke `unload_command` with
   `{out_file} = <LOCAL_STAGING_DIR>/<blob_prefix><TABLE>/<range_seq:06d>.dat`, parse the
   `UNLOAD01 ROWS= BYTES= SHA256=` line, verify file size = rows x LRECL and SHA-256, upload, then set
   `DONE` with `rows_extracted`, `file_sha256`, `file_bytes`, `extracted_at`. A crash leaves the range
   `RUNNING`/`FAILED`; a restart redoes only those ranges.
4. `run_ledger.extracted` = sum of `rows_extracted`, `extract_files` = ranges.

#### 9.4.2 LOAD (EKS by default; ACA when `run_job_in_azure`)

Per range with `extract_status = DONE` and `load_status != DONE`: read records, convert (§8), insert
into `stg.<T>` with `run_id`, `namespace`, `source_key`, `range_seq`, `batch_id` (1-based per range),
`raw_bytes`; failures to `mig.rejects`. On restart of a `RUNNING` range, first delete that range's
`stg` and `LOAD` reject rows for this run. `run_ledger.loaded/rejected` = counts for the run.
Invariant after LOAD: `extracted = loaded + rejected` per table (else exit 2).

#### 9.4.3 VALIDATE (EKS by default; ACA when `run_job_in_azure`)

Candidates = rows of `stg.<T>` for this run. For each table in `order`:

1. **Hash**: source hash from the staged fixed-width record (`raw_bytes` decoded exactly as §7),
   target hash computed in Azure SQL from the converted columns (§7 T-SQL); write
   `stg.<T>.row_hash`. Unequal -> `HASH_MISMATCH`.
2. **Parent**: for tables with `selection.parent`, each candidate MUST have a parent row with status
   `VALIDATED` in this run (or already in `arch.<parent>`). Missing -> `ORPHAN_PARENT_NOT_SELECTED`.
3. **Counts by class**: for tables with `class_totals`: source side = rows of the candidate keys
   grouped by **system-of-record class** (`source_class_resolution`: if the Db2 class has a non-blank
   successor in the lookup table, use the successor; else the class), aggregating `COUNT(*)` and
   `SUM(<sum_columns>)` exactly (DECIMAL(38,8)); target side = the same keys grouped by the
   converted class column in `stg`. Both written to `mig.class_totals`. Any class with a different
   count -> `CLASS_COUNT_MISMATCH`; any class with a different sum (compared to the 8th decimal) ->
   `CLASS_TOTAL_MISMATCH`. The rows failed are those in a mismatched class whose source SoR class
   differs from their target class; if there are none, every row of the mismatched class fails.
   Table-level totals are computed and logged but are **never** sufficient to pass.
4. A row passing 1-3 gets `mig.validation.status = VALIDATED`; `purge_safe = 1` iff table
   `role = data`. Failed rows get `status = FAILED`, `rule_name`, and a `mig.rejects` row with
   `stage = VALIDATE`, `field` (`ARCH_KEY` for hash on key, the column name otherwise), `error`
   (e.g. `source hash 7AD2... != target hash 7521...`,
   `class FIN7 source 2600.12345678 target 2600.12345679`).
5. Promotion: VALIDATED rows are inserted into `arch.<T>` (parents first) with `row_hash`,
   `migrated_run_id`; existing `arch` rows with equal `row_hash` are left as-is.
6. `run_ledger.validated/validate_failed`. Invariant: `loaded = validated + validate_failed`.

Priority when several rules hit one row: LOAD rules, then `HASH_MISMATCH`,
`ORPHAN_PARENT_NOT_SELECTED`, `CLASS_COUNT_MISMATCH`, `CLASS_TOTAL_MISMATCH`.

#### 9.4.4 PURGE (always beside Db2, on EKS)

1. `intended` = keys with `purge_safe = 1` for this run, per data table, in reverse `order`
   (children first). Guard A: `intended != run_ledger.validated` for any data table -> exit 3.
2. Dry run (overlay `purge` false/absent): write `purge_intended`, `purged = 0`,
   `purge_dry_run = 1`; delete nothing; exit 0.
3. Otherwise per batch of `purge_batch_rows` keys:
   a. insert the keys into `mig.purge_audit` as `INTENDED` (Azure, committed);
   b. one Db2 unit of work: `INSERT INTO MIGAUDIT.PURGE_AUDIT (RUN_ID, TABLE_NAME, SOURCE_KEY)` for
      every key, **then** `DELETE FROM ARCHIVE.<T> WHERE <key> IN (...)`; Guard B: delete row count
      != batch size -> `ROLLBACK`, set the batch `ROLLED_BACK`, exit 3; FK violation (SQLSTATE
      `23504`) -> same; otherwise `COMMIT`;
   c. set the batch `PURGED` with `purged_at`.
   Keys already `PURGED` for this run are skipped on restart.
4. `run_ledger.purge_intended/purged/purge_dry_run = 0`. Reference tables are never purged.
   Failed rows remain in the source.

#### 9.4.5 RECONCILE (EKS by default; ACA when `run_job_in_azure`)

1. Load session links (§10.3) into `mig.run_sessions`.
2. Read `mig.v_reconciliation_tables`; `closes` = AND of per-table `closes`; update `mig.runs`
   (`CLOSED`/`FAILED`, `closes`, `exit_code`, `finished_at`).
3. Write `reconciliation.json`, `.csv`, `.html` (shapes §10.2) to `LOCAL_STAGING_DIR/<blob_prefix>`
   and the staging container (evidence copies; the app serves from the database, not these files).
4. On `closes`: delete this run's `stg` rows (their content is in `arch` / `mig.rejects`).
5. Exit 2 when not `closes`, else 0.

### 9.5 Execution hosts

| Stage | Default (`run_job_in_azure: false`) | `run_job_in_azure: true` |
|---|---|---|
| EXTRACT | Kubernetes Job in `otterworks-<NS>` | same (always beside Db2) |
| LOAD | Kubernetes Job | Container Apps job `caj-ldm-<NS>` reading staging blobs |
| VALIDATE | Kubernetes Job | Container Apps job; source hashes come from staged `raw_bytes`, Db2 source class lookup from staged RETNPLCY |
| PURGE | Kubernetes Job | same (always beside Db2) |
| RECONCILE | Kubernetes Job | Container Apps job |

The Kubernetes Job reaches Azure SQL over its **public endpoint**; Terraform adds a server firewall
rule per `eks_egress_cidrs` entry. Db2 has no public endpoint and is never reachable from Azure,
which is why EXTRACT and PURGE always run on EKS. In ACA mode ops runs: EKS `extract` -> ACA
`load`, `validate` -> EKS `purge` -> ACA `reconcile`.

## 10. Report and archive read path (app unit)

### 10.1 Endpoints (report-service)

| Method + path | Content-Type | Body |
|---|---|---|
| `GET /api/reports/reconciliation/{runId}` | `application/json` | §10.2 |
| `GET /api/reports/reconciliation/{runId}.csv` | `text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="reconciliation-<runId>.csv"` | §10.2 |
| `GET /api/reports/reconciliation/{runId}.html` | `text/html; charset=utf-8` | standalone page |
| `GET /api/reports/reconciliation` | `application/json` | `[{"run_id","status","started_at","finished_at","closes"}]` for this namespace, newest first |

The same handlers MUST also answer under `/api/v1/reports/reconciliation/...` (the API gateway
forwards `/api/v1/reports` unchanged). `runId` unknown -> 404 JSON `{"error":"run not found"}`.
Namespace = env `LDM_NAMESPACE`; only rows with that namespace are returned. When
`ARCHIVE_STORE=db2` (BEFORE) the endpoints return 404 `{"error":"no migration in this namespace"}`.
Data comes straight from Azure SQL: `mig.runs`, `mig.v_reconciliation_tables`,
`mig.v_reconciliation_failures`, `mig.run_sessions`, `mig.class_totals` - no caching, no files.
Java 8: use `com.microsoft.sqlserver:mssql-jdbc:<12.x>.jre8`.

### 10.2 Shapes

JSON (key order as shown; numbers are JSON integers):

```json
{
  "run_id": "r20260924150000",
  "namespace": "d24-after",
  "generated_at": "2026-09-24T15:42:07Z",
  "tables": [
    {"table": "RETNPLCY", "extracted": 40, "loaded": 40, "validated": 40, "purged": 0, "failed": 0},
    {"table": "DOCARCH", "extracted": 180000, "loaded": 179980, "validated": 179963, "purged": 179963, "failed": 37},
    {"table": "FILEAUD", "extracted": 620000, "loaded": 620000, "validated": 619995, "purged": 619995, "failed": 5}
  ],
  "failures": [
    {"table": "DOCARCH", "source_key": "MIG01-0000000001", "rule": "CCSID_UNMAPPABLE", "stage": "LOAD",
     "field": "OWNER_NAME", "sqlstate": null, "error": "CCSID037 byte X'3F' at offset 6"}
  ],
  "sessions": [{"label": "architect: contracts and scaffolding", "url": "https://..."}],
  "closes": true
}
```

- `tables`: from `mig.v_reconciliation_tables` ordered by `table_order`; `failed` = rejected +
  validate_failed. `loaded` means rows in staging (LOAD), so `extracted = loaded + rejected(LOAD)`.
- `failures`: every row of `mig.v_reconciliation_failures` for the run ordered by `table_name`,
  `source_key`; `rule` <- `rule_name`; `source_key` with trailing spaces removed for display;
  `sqlstate` and `field` may be null. MAY add keys `native_error`, `issue` (the MIG id from the
  issue register, matched on table + RTRIM(key)). All seven MIG classes appear here on d24-after.
- `sessions`: `mig.run_sessions` by `ordinal`.
- `closes`: `mig.runs.closes` (false when null).
- Optional additive key `class_totals`: `[{"table","class","source_count","target_count","source_sum","target_sum"}]`
  (sums as 8-dp strings) - the MIG-07 evidence; the HTML page SHOULD render it.

CSV: UTF-8, RFC 4180, `\r\n`, header row, two sections separated by one empty line:

```
section,table,extracted,loaded,validated,purged,failed
summary,DOCARCH,180000,179980,179963,179963,37

section,table,source_key,rule,stage,field,sqlstate,error
failure,DOCARCH,MIG01-0000000001,CCSID_UNMAPPABLE,LOAD,OWNER_NAME,,CCSID037 byte X'3F' at offset 6
```

HTML: summary table (same columns), `closes` badge, class-totals table, failed-row table, session
links. The admin dashboard page `/migration/reconciliation/:runId` (Angular, in
`frontend/admin-dashboard`) renders the JSON and links the `.csv`; it calls the API through the
existing `/api/v1` base URL.

### 10.3 Session links

Each unit adds `migration/sessions/<unit>.yaml` (`- label: "<unit>: <what>"`, `url: <session url>`)
in its own PR; RECONCILE loads `report.sessions_glob` sorted by file name, entries in file order.

### 10.4 Archive read path (`ARCHIVE_STORE`)

audit-service exposes the retention history of one archived document:

`GET /api/v1/audit/archive/{docId}` ->

```json
{"doc_id": "...", "store": "db2|postgresql|azuresql",
 "versions": [{"arch_key": "DA00000000000042", "version_no": 3, "retention_class": "FIN7",
   "last_access_ts": "2016-03-01-10.15.30.123456789012", "storage_charge": "1234.50000000",
   "owner_name": "LOPEZ, M.", "disposition_dt": "2023-03-01", "legal_hold": false,
   "events": [{"audit_key": "FA000000000000000123", "event_type": "VIEW",
     "event_ts": "2015-07-02-08.00.00.000000000001", "actor_id": "U00000000042",
     "disposition_code": "00", "client_ip": "10.1.2.3", "detail_text": "VIEW v3"}]}]}
```

Versions ordered by `version_no`, events by `event_ts`, `audit_key`. Text trimmed of trailing
spaces; timestamps in the Db2 text form (postgresql: rebuilt from `TIMESTAMP(6)` + 6-digit
`_NANOS_TAIL`; azuresql: from `DATETIME2(7)` + 5-digit `_NANOS_TAIL`),
so both stores return byte-identical JSON for a migrated document. 404 if the document has no
archived versions in the selected store.

| Env | BEFORE (`d24-before`) | AFTER (`d24-after`) |
|---|---|---|
| `ARCHIVE_STORE` | `db2` | `azuresql` |
| connection | `DB2_HOST`, `DB2_PORT`, `DB2_DATABASE`, `DB2_USER`, `DB2_PASSWORD` (reads `ARCHIVE.*`) | `AZSQL_SERVER`, `AZSQL_DATABASE`, `AZSQL_AUTH`, `AZSQL_USER`, `AZSQL_PASSWORD` (reader user) (reads `arch.*`) |
| `LDM_NAMESPACE` | `d24-before` | `d24-after` |

Any other `ARCHIVE_STORE` value, or missing connection vars for the selected store: the service
starts, logs an error, and the endpoint returns 503. The report-service uses the same env names.
The admin dashboard page `/migration/archive/:docId` shows this response, including `store`.
Presenter flow: the same `docId` (ops picks a migrated DOCARCH row with children, documented in the
runbook) opened on `t-d24-before...` and `t-d24-after...` shows identical values with different `store`.

## 11. Azure Terraform interface (azure unit)

Root module `infrastructure/terraform/azure/` (one root, one state per namespace; backend partial
config passed by ops: `-backend-config="key=otterworks/<NS>/terraform.tfstate"` plus
`storage_account_name`, `resource_group_name`, `container_name` from the `TFSTATE_AZ_*` env of §3.2). Providers: `azurerm ~> 4.x`, `random ~> 3.x` (pinned in
`versions.tf` + committed `.terraform.lock.hcl`). Authentication via `ARM_*` env vars only.

### 11.1 Variables

| Name | Type | Default | Validation / meaning |
|---|---|---|---|
| `namespace` | string | - | §3.1 regex; MUST equal `"${run_token}-${state}"` |
| `run_token` | string | - | `^[a-z][a-z0-9]{1,11}$` |
| `state` | string | - | `before` or `after` (ops never applies with `before`) |
| `location` | string | `"centralus"` | Azure SQL is not provisionable in `eastus2`/`eastus` for the demo subscription; ops may override via `AZURE_LOCATION` |
| `owner` | string | `"otterworks-demo"` | MUST equal `otterworks-demo` |
| `expires` | string | - | `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` |
| `private_networking` | bool | `false` | `true`: VNet, private endpoints for SQL + storage + Key Vault, CAE in the VNet, public network access disabled |
| `eks_egress_cidrs` | list(string) | - | one SQL firewall rule each (`cidrhost(c,0)`..`cidrhost(c,-1)`); may be empty only if `private_networking` |
| `report_image` | string | - | full image ref |
| `audit_image` | string | - | full image ref |
| `job_image` | string | - | full image ref |
| `run_job_in_azure` | bool | `false` | informational tag + job env; the job is provisioned either way |
| `registry_server` | string | `"599083837640.dkr.ecr.us-east-1.amazonaws.com"` | additional: registry for the three images |
| `registry_username` | string | `"AWS"` | additional |
| `registry_password` | string (sensitive) | - | additional: ECR token supplied by ops at apply time |
| `session_links_json` | string | `"[]"` | additional: passed to Container Apps as `LDM_SESSION_LINKS` (unused by ldm unless set) |

### 11.2 Resources (all tagged per §3.3, named per §3.2)

Resource group; SQL logical server (version 12.0, admin `ldmadmin`, password `random_password`
32 chars, minimum TLS 1.2; an Entra admin is optional); SQL database General
Purpose serverless `GP_S_Gen5_2` (2 vCores max), `min_capacity = 0.5`, `auto_pause_delay_in_minutes =
60`, max size 32 GB; firewall rules from `eks_egress_cidrs` + `AllowAzureServices` (0.0.0.0) when not
private; storage account (StorageV2, LRS, TLS 1.2, no public blob access) + private container
`staging-<NS>`; Key Vault (RBAC mode, soft-delete 7 days, purge on destroy) with secrets
`azsql-admin-user`, `azsql-admin-password`, `azsql-reader-user`, `azsql-reader-password`,
`staging-storage-key`; user-assigned identity with roles `Storage Blob Data Reader` on the container,
`Key Vault Secrets User` on the vault, and database write: by default the job authenticates with
`AZSQL_AUTH=sql` using the admin secret it reads from Key Vault through the identity; with
`AZSQL_AUTH=managed-identity`, `ldm init` creates the contained user `id-otterworks-<NS>`
(`CREATE USER ... FROM EXTERNAL PROVIDER`) with `db_datareader`, `db_datawriter`, `db_ddladmin`
(this requires the Terraform to set an Entra admin on the server); Log Analytics workspace; Container Apps environment;
Container Apps `ca-report-<NS>` (target port 8091) and `ca-audit-<NS>` (target port 8090), external
ingress, min replicas 1, env per §10.4 (`ARCHIVE_STORE=azuresql`, `LDM_NAMESPACE`); Container Apps job
`caj-ldm-<NS>` (manual trigger, 1 replica, timeout 3600 s, env §9.2 with `LDM_HOST=aca`, secrets from
Key Vault via the identity).

### 11.3 Outputs

| Output | Example |
|---|---|
| `sql_server_fqdn` | `sql-otterworks-d24-after.database.windows.net` |
| `sql_database_name` | `sqldb-otterworks-d24-after` |
| `key_vault_name` | `kvowd24after3f` |
| `storage_account_name` | `stowd24after3fa` |
| `staging_container` | `staging-d24-after` |
| `managed_identity_client_id` | GUID |
| `container_app_env_id` | ARM id |
| `report_fqdn` | `ca-report-d24-after.<env-domain>` |
| `audit_fqdn` | `ca-audit-d24-after.<env-domain>` |

No output is sensitive; secrets are read by ops from Key Vault, never output.

### 11.4 Tags contract

```hcl
locals {
  tags = { namespace = var.namespace, owner = var.owner, demo = "legacy-data-migration", expires = var.expires }
}
```

Every resource that supports `tags` sets `tags = local.tags`; nothing is created outside
`rg-otterworks-<NS>` except the state blob.

## 12. Operations interface (ops unit)

### 12.1 Make targets

| Target | Behavior |
|---|---|
| `make demo-up NS=<token>` | validate token; `scripts/deploy-demo.sh up <NS>`: AWS demo Terraform (§12.4), tenant namespace + app via existing `scripts/deploy-tenant.sh` conventions, Db2 chart, Secret, seed load (idempotent: skip if seeded with matching SHA-256s), and - only if the overlay has `azure: true` - Azure Terraform apply, `ldm init` (with the MIG-06 fixture), app env for `ARCHIVE_STORE`. Prints hostnames. |
| `make demo-migrate NS=<token> RUN_ID=<id>` | refuse if overlay `migrate: false`; run the stages per §9.5 as Kubernetes Jobs from the migration-job chart (and ACA job when configured); stream logs to `docs/demos/evidence/<NS>/<RUN_ID>/migration.log`; exit with the job exit code |
| `make demo-destroy NS=<token>` | Azure `terraform destroy` (if state exists) and AWS demo `terraform destroy`, delete the tenant namespace, then run `demo-verify-clean`; transcript to `docs/demos/evidence/<NS>/destroy-<UTC>.log` |
| `make demo-verify-clean NS=<token>` | exit 0 iff `aws resourcegroupstaggingapi get-resources --tag-filters Key=namespace,Values=<NS>` (us-east-1) returns no ARNs, `az resource list --tag namespace=<NS>` returns `[]`, `az group exists -n rg-otterworks-<NS>` is false, and `kubectl get ns otterworks-<NS>` is NotFound; else lists survivors, exit 1 |

All four validate `NS` (§3.1) first and refuse `main`/`otterworks-main`. `EXPIRES` (optional,
default now + 72 h) sets the `expires` tag.

### 12.2 Reaper

`scripts/demo-reaper.sh [--dry-run]` finds resources tagged `demo=legacy-data-migration` whose
`expires` < now (AWS tagging API, `az resource list --tag demo=legacy-data-migration`, namespaces
with `demo/expires-at` annotation) and runs `demo-destroy` for each token. Scheduled by
`.github/workflows/demo-reaper.yml` (cron hourly, `workflow_dispatch`, OIDC/secrets for AWS + Azure).

### 12.3 Evidence

`docs/demos/legacy-data-migration.md`: presenter runbook, reset procedure from a clean account with
measured per-stage timing (`mig.stage_log`), links to evidence under `docs/demos/evidence/`
(plan/apply logs, migration log, report HTML/CSV, destroy transcript from a throwaway token such as
`xy1-after`, recording link, session links). Secrets are redacted.

### 12.4 AWS demo resources

`infrastructure/terraform/demo-aws/` (one state per token, §3.2) creates: the Db2 EBS volume
(gp3, 20 GiB, in the AZ of the tenant's node group, tagged) and the static `PersistentVolume`
input values (volume id, AZ) consumed by the Db2 chart; the S3 bucket; the ECR repository for the
job image (`force_delete = true`). Egress CIDRs for `eks_egress_cidrs` are discovered by ops
(NAT gateway EIPs of the cluster VPC; if the nodes egress without NAT, the node public IPs `/32`)
and passed to the Azure apply.

## 13. Kubernetes charts

### 13.1 `infrastructure/helm/db2-archive` (source unit)

StatefulSet `db2-archive` (1 replica), image `icr.io/db2_community/db2` pinned by tag, `privileged`
security context as required by Db2 Community Edition, `LICENSE=accept`, `DBNAME` from values;
PVC bound to the static PV (`storageClassName: ""`, `volumeName` from values - no dynamic
provisioning); resources requests `500m`/`2Gi`, limits `2`/`4Gi` (fits the tenant ResourceQuota);
ClusterIP Service `db2-archive` port 50000 (no ingress); `/health` on port 8080 (sidecar) returning
200 iff `CONNECT TO <DBNAME>` succeeds, used for liveness+readiness; NetworkPolicy: ingress to 50000
only from pods in the same namespace with label `ldm/db2-client: "true"`, to 8080 only from the
monitoring namespace and kubelet. Values: `dbName`, `pv.volumeName`, `pv.size`, `credentialsSecret`
(default `db2-archive-credentials`).

### 13.2 `infrastructure/helm/migration-job` (job unit)

One `batch/v1` Job per invocation: `ldm-<stage>-<run_id>`, `backoffLimit: 0`,
`ttlSecondsAfterFinished: 86400`, pod label `ldm/db2-client: "true"`, args
`["<stage>","--manifest","/app/migration/manifest.yaml","--namespace","<NS>","--run-id","<id>"]`,
env §9.2 (`LDM_HOST=eks`) from Secret `db2-archive-credentials`, the tenant's PostgreSQL Secret
(`PG_*`, default `postgres-credentials`) and values (`S3_STAGING_BUCKET`, `AWS_REGION`, Spark
settings); `emptyDir` 10 Gi at `/work/staging`; resources requests `250m`/`512Mi`, limits
`1`/`1.5Gi` (Spark local mode: driver `1g`, `local[*]` inside the pod's CPU limit); NetworkPolicy
denying all ingress. Azure is opt-in (`azure.enabled`): Secret `ldm-azure` (keys `AZSQL_USER`,
`AZSQL_PASSWORD`, `AZ_STORAGE_KEY`) and `AZSQL_*` values only then. No Service, no ingress (a Job
serves nothing, so no `/health`). The job image contains the repo's `migration/` tree at
`/app/migration`, the Db2 CLP client and GnuCOBOL runtime (for `unload_command`), `ibm_db`,
`psycopg`, `boto3`, `pyspark` + a JRE; `pyodbc` + ODBC Driver 18 only with `--build-arg WITH_AZURE=1`.

## 14. Resolved ambiguities (decisions made by the architect)

| # | Ambiguity | Decision |
|---|---|---|
| 1 | Brief names `services/admin-dashboard/**`; the repo's dashboard is `frontend/admin-dashboard/**` | app unit owns `frontend/admin-dashboard/**`; nothing is created under `services/admin-dashboard` |
| 2 | Report path `/api/reports/...` vs repo convention `/api/v1/...` | serve both; gateway uses `/api/v1/reports/...` |
| 3 | Db2 database names are max 8 chars, token-derived names are longer | `D24A` / `D24B` rule (§3.2); isolation is the namespace + StatefulSet |
| 4 | "CCSID 037 column" in a UTF-8 Db2 database | `CHAR(n) FOR BIT DATA` holding EBCDIC 037 bytes (`OWNER_NAME`, `DISPOSITION_DT`); decoding is manifest `encoding: cp037` |
| 5 | Where MIG-01..07 come from | seed plants all seven (SEED-SPEC §7); MIG-02 via `type_overrides UNIT_RATE DECIMAL(18,8)`, MIG-07 via transposed retired-code `value_map`, MIG-06 via Azure-side prior-run fixture |
| 6 | FILEAUD selection vs orphans | children are selected by their own predicate; the parent relation is only checked in VALIDATE |
| 7 | Whether `loaded` counts rows later failed in VALIDATE | yes: `loaded` = staged; `failed` = LOAD rejects + VALIDATE failures |
| 8 | `purged != validated` on a dry run | dry run compares `purge_intended` to `validated`; reference tables never purged and excluded |
| 9 | Schema apply / fixture loading has no stage verb | additional `ldm init` verb (§9.1); stage verbs apply DDL too |
| 10 | Report column `rule` is a T-SQL reserved word | stored as `rule_name`, emitted as `rule` |
| 11 | Session links | per-unit `migration/sessions/<unit>.yaml` (no merge conflicts) |
| 12 | Container Apps pulling from ECR | additional `registry_*` variables; ops passes a fresh ECR token on each apply; min replicas 1 |
| 13 | Dynamic EBS provisioning is "creating AWS resources from Kubernetes" | Db2 volume created by ops Terraform, bound as a static PV |
| 14 | Db2 is not an HTTP service but charts need `/health` | health sidecar on 8080 (§13.1); the migration Job has no probes |
| 15 | Archive read in AFTER for documents not migrated | strict switch: `azuresql` reads only `arch.*`; unmigrated documents are 404 there |
| 16 | EKS egress for the firewall rule | discovered at deploy time (NAT EIPs or node IPs), passed as `eks_egress_cidrs` |

## 15. Change control

A unit that finds this contract wrong or insufficient does **not** diverge silently: it implements
the contract as written where possible and describes the needed change in its PR under a heading
`Contract change request`. The integrator applies accepted changes in a `contract:` commit on
`demo/legacy-data-migration`.
