# OW_BILLING estate inventory — STOP B (run 20260927b)

Every row is FACT (with citation: `file:line` or the dictionary view read at
`.migration/inventory/oracle_dictionary_20260927b.json`) or PROPOSED/INFERRED (marked).

Scope slice: signup → subscription → `issue_invoice` → nightly CUSTBILL fixed-width
file → finance close total (`00_context.md`).

## 1. Live Oracle census (one dictionary read, OW_BILLING_RO, FREEPDB1)

Raw read: `.migration/inventory/oracle_dictionary_20260927b.json` and
`.migration/inventory/row_counts_20260927b.json` (script
`/home/ubuntu/bin/ow_inventory_read.py`, connected as `OW_BILLING_RO`, `read_at`
2026-09-27T17:5xZ, one pass: dictionary + governance views + `COUNT(*)` per table;
the run-20260927 read `.migration/inventory/oracle_dictionary_20260927.json` is kept
as the prior baseline). Delta vs that baseline after the estate reset: zero object,
constraint or column changes except `FIXTURE_META.INITIALIZED_AT TIMESTAMP(6)`
(fixture-infra); row counts identical (CODES 32, CREDIT_NOTES 5, RATING_PERIODS 3,
RATING_RESULTS 3, DUNNING_ATTEMPTS 1, NOTIFICATIONS 1, INVOICES 3, INVOICE_LINES 2,
INVOICE_HEADER 18,750, INVOICE_LINE 150,000, CUSTOMER_MASTER 25,000,
ENTITY_ATTR_VALUE 8,333, TENANTS 69, SUBSCRIPTIONS 69, USAGE_EVENTS 814).

**N = 45 objects visible in `ALL_OBJECTS` for `owner='OW_BILLING'`: 20 TABLE + 25 INDEX, all VALID.**
Packages, package bodies, triggers, sequences and scheduler jobs are **invisible to
`OW_BILLING_RO`** (`ALL_OBJECTS` shows none; `ALL_DEPENDENCIES`, `ALL_TRIGGERS`,
`ALL_SEQUENCES`, `ALL_SCHEDULER_JOBS` all empty) — consistent with DEP-013
(SELECT-only principal, no EXECUTE grants). Their existence and shape are therefore
FACT from the repo DDL that seeded the estate (`services/legacy-billing/db/oracle/`),
not from the dictionary. `ALL_TAB_PRIVS` read with `TABLE_SCHEMA='OW_BILLING'`
in the same pass (1 row, see §10). `ALL_SYNONYMS` returned zero rows (no synonyms over OW_BILLING).

Coverage arithmetic (ALL_OBJECTS-visible objects only):

```
N = 45 = slice(20 tables' indexes 25 + 16 slice tables) + shared 0 + proposed-unused 3 + fixture-infra 1
  slice tables (16): CODES, PLANS, TENANTS, SUBSCRIPTIONS, SUBSCRIPTIONS_HIST,
    USAGE_EVENTS, RATING_PERIODS, RATING_RESULTS, INVOICES, INVOICE_LINES,
    CREDIT_NOTES, BILLING_AUDIT_LOG, INVOICE_HEADER, INVOICE_LINE,
    CUSTOMER_MASTER, ENTITY_ATTR_VALUE   (all 25 indexes sit on these)
  proposed-unused tables (3): DUNNING_ATTEMPTS, NOTIFICATIONS, CUSTOMER_MASTER_HIST
  fixture-infra (1): FIXTURE_META
  16 + 3 + 1 = 20 tables + 25 indexes = 45 ✓ (closes against ALL_OBJECTS)
```

### Live row counts (COUNT(*) per table — metadata only)

| Table | Rows | | Table | Rows |
|---|---|---|---|---|
| BILLING_AUDIT_LOG | 0 | | INVOICE_LINES | 2 |
| CODES | 32 | | INVOICE_HEADER | 18,750 |
| CREDIT_NOTES | 5 | | INVOICE_LINE | 150,000 |
| CUSTOMER_MASTER | 25,000 | | NOTIFICATIONS | 1 |
| CUSTOMER_MASTER_HIST | 0 | | PLANS | 3 |
| DUNNING_ATTEMPTS | 1 | | RATING_PERIODS | 3 |
| ENTITY_ATTR_VALUE | 8,333 | | RATING_RESULTS | 3 |
| FIXTURE_META | 1 | | SUBSCRIPTIONS | 69 |
| INVOICES | 3 | | SUBSCRIPTIONS_HIST | 0 |
|  |  | | TENANTS | 69 |
|  |  | | USAGE_EVENTS | 814 |

`ALL_TAB_COLUMNS` + `ALL_CONSTRAINTS` captured for all 20 tables (122 constraint rows;
e.g. `PK_CODES (CODE_TYPE,CODE_VAL)`, `PK_BILLING_AUDIT_LOG (LOG_ID)`). `NUM_ROWS`
(optimizer stats) also captured per table.

### Census of repo-declared objects not visible to OW_BILLING_RO

FACT from `services/legacy-billing/db/oracle/` (these files seeded the estate —
`startup/00_init.sh`, `setup/01_users.sql`):

| Object | Type | Slice class | Citation |
|---|---|---|---|
| PKG_OW_UTIL (spec+body), 5 members | PACKAGE | slice — shared utility, called by every package | `packages/01_pkg_util.sql` |
| PKG_PLANS, 3 members | PACKAGE | slice — signup/subscription | `packages/02_pkg_plans.sql` |
| PKG_RATING, 4 members | PACKAGE | slice — rating inside issue_invoice | `packages/03_pkg_rating.sql` |
| PKG_INVOICING, 4 members | PACKAGE | slice — issue_invoice | `packages/04_pkg_invoicing.sql` |
| PKG_DUNNING, 3 members | PACKAGE | **PROPOSED-unused** (DEP-010; closure fact below) | `packages/05_pkg_dunning.sql` |
| TRG_BILLING_AUDIT_LOG_ID | TRIGGER (BEFORE INSERT billing_audit_log) | slice — fires on every log_msg write | `schema/01_tables.sql:179` |
| TRG_SUBSCRIPTIONS_HIST | TRIGGER (AFTER UPD/DEL subscriptions → subscriptions_hist) | slice — fires on sp_change_plan (and dunning's suspend) | `schema/01_tables.sql:206` |
| TRG_SUB_NO_UNCANCEL | TRIGGER (BEFORE UPDATE OF status_cd subscriptions) | slice — enforces cancelled-stays-cancelled | `schema/01_tables.sql:228` |
| TRG_USAGE_EVENTS_CHECK | TRIGGER (BEFORE INSERT usage_events; validates against CODES) | slice — gates usage writes | `schema/01_tables.sql:239` |
| TRG_CUSTOMER_MASTER_SEQ / _HIST | TRIGGERs on customer_master | slice (CUSTBILL chain table) | `schema/02_horror.sql:346,358` |
| TRG_ENTITY_ATTR_VALUE_SEQ | TRIGGER | slice (CUSTBILL chain table) | `schema/02_horror.sql:391` |
| SEQ_BILLING_AUDIT_LOG, SEQ_SUBSCRIPTIONS_HIST, SEQ_CUSTOMER_MASTER, SEQ_CUSTOMER_MASTER_HIST, SEQ_ENTITY_ATTR_VALUE | SEQUENCE (5) | slice — serve the triggers above | `schema/01_tables.sql:177,204`; `02_horror.sql:343,344,389` |
| JOB_NIGHTLY_DUNNING | SCHEDULER JOB (DISABLED) | excluded — dunning path only | `schema/04_jobs.sql:10` |
| JOB_PURGE_AUDIT_LOG | SCHEDULER JOB (DISABLED), DELETEs billing_audit_log >90d | excluded from slice; **writes a slice table** — noted as finding | `schema/04_jobs.sql:21` |

## 2. Shared-object ownership map (tables written by >1 writer)

| Table | Writers |
|---|---|
| BILLING_AUDIT_LOG | `pkg_ow_util.log_msg` (every package, autonomous txn, `01_pkg_util.sql:65`); `JOB_PURGE_AUDIT_LOG` DELETE (`04_jobs.sql:21`) |
| SUBSCRIPTIONS | `pkg_plans.sp_change_plan` UPDATE+INSERT (`02_pkg_plans.sql`); `pkg_dunning.sp_suspend_overdue` UPDATE (`05_pkg_dunning.sql:507`); app `backends/oracle.py` `change_plan` UPDATE + `ensure_tenant` INSERT (`oracle.py:71-80,160-177`) |
| TENANTS | `pkg_dunning.sp_suspend_overdue` UPDATE (`05_pkg_dunning.sql:506`); app `ensure_tenant` INSERT (`oracle.py:152`) |
| SUBSCRIPTIONS_HIST | `trg_subscriptions_hist`, fired by writers of SUBSCRIPTIONS (both slice and dunning) |
| CREDIT_NOTES | `pkg_invoicing.sp_issue_invoice` burn-down UPDATE (`04_pkg_invoicing.sql:407-414`) — single package writer, but also read by `compute_preview` |
| CUSTOMER_MASTER_HIST | `trg_customer_master_hist` only (`02_horror.sql:358`) |

## 3. Batch chain — `etl/legacy-extra/` (CUSTBILL nightly)

| Step | Reads | Writes | Edge | Class |
|---|---|---|---|---|
| `tools/oracle_custbill_extract.py` | Oracle `invoice_header` JOIN `customer_master` LEFT JOIN `tenants`, `batch_no = sha256(NS)-derived` (`:32` `ns_batch_no`) | `$ROOT/incoming/CUSTBILL_<NS>_ORACLE.dat`, fixed-width 65-char records (`:44-68`) | extract → incoming/ | FACT (file read) |
| `jobs/sftp_ingest_poll.ksh` | `$SFTP_DROP/CUSTBILL*.dat` | copies to `$ROOT/incoming/`, archives to `$ROOT/archive/`, removes source | sftp-drop → incoming | FACT |
| `jobs/parse_custbill_fixedwidth.sh` | `$ROOT/incoming/CUSTBILL*.dat` | `$ROOT/parsed/<base>.psv` (pipe-delimited); renames input `.done` | incoming → parsed | FACT |
| `jobs/finance_excel_report.pl` | `$ROOT/parsed/CUSTBILL*.psv` | `$ROOT/reports/finance_billing_YYYYMMDD.csv` + `.xls` copy; sendmail dead-code | parsed → reports | FACT |
| `run_all.sh` | — | chains the three jobs with `sleep $RUN_ALL_SLEEP` (default 600) between stages | orchestration | FACT |
| `make tp-month-end NS=<ns>` (Makefile:637-654) | replaces the sftp stage: extract → parse → finance report under `${OTTERWORKS_LEGACY_ROOT:-/tmp/otterworks-legacy}/<NS>/`, then copies newest CSV+.xls to `etl/legacy-extra/reports/<NS>/` | — | demo wiring | FACT |

**CUSTBILL record layout** (`parse_custbill_fixedwidth.sh` header + `format_record`
in `oracle_custbill_extract.py:44-68`): cust_no X(10), cust_name X(30),
period_end 9(8) YYYYMMDD, amount 9(10)V99 implied-decimal, currency X(3) literal
`USD`, rec_type X(2) (`01` invoice / `02` credit, negative amounts → `02`). Record
length asserted = 65 (`:62`). Parse strips `HDR`/`TRL` lines, `cut` fields, divides
amount by 100, reformats date; trailer count logged only, never reconciled.

**Finance close total**: `finance_excel_report.pl` sums `amount` grouped by
`currency|record_type` over every `CUSTBILL*.psv` in `parsed/` → CSV
`Currency,RecordType,RecordCount,TotalAmount`. `GET /api/reports/finance?ns=<ns>`
(`app/reports.py:254`) serves the newest `finance_billing_*.csv` under
`etl/legacy-extra/reports/<ns>/` (or `FINANCE_REPORT_DIR`), summing RecordCount and
TotalAmount across rows (`reports.py:228-251`). The close total is therefore a sum
over the fixed-width file, not a direct Oracle aggregate. Other Oracle-backed
endpoints: `/api/reports/month-end` (`STATUS_SQL`/`LINE_SQL` over `invoice_header`/
`invoice_line`), `/api/reports/reconciliation` (`BALANCES_SQL`) — `reports.py:1-200`.

**Overlap/latency notes (FACT, crontab comments)**: ingest `*/15`, parse `5-59/15`,
finance `02:10` overlapping analytics `02:00`; `run_all.sh` Sunday `06:00` overlaps
all; lock files checked but never removed; no write-once/rename protocol.

## 4. App routine contract (`services/legacy-billing/app/`)

Dispatch: `backends/__init__.py:5` — `BILLING_BACKEND=oracle` → `backends/oracle.py`,
else `postgres.py` (default). Oracle connect env: `ORACLE_USER/PASSWORD/HOST/PORT/
SERVICE` (`oracle_conn.py:10-14`); Postgres env: `DB_HOST/PORT/NAME/USER/PASSWORD`
(`postgres.py:10-17`).

| App method | Oracle side | Postgres side (target contract) |
|---|---|---|
| `list_plans` | `pkg_plans.fn_list_plans` | `billing.fn_list_plans()` |
| `entitlement` | `pkg_plans.fn_entitlement` | `billing.fn_entitlement` |
| `change_plan` | direct `UPDATE subscriptions` + `pkg_plans.sp_change_plan` | `billing.sp_change_plan` |
| `usage_rating` | `pkg_rating.fn_usage_rating` | `billing.fn_usage_rating` |
| `usage_summary` | `pkg_rating.fn_usage_summary` | (no postgres counterpart in postgres.py) |
| `finalize_rating` | `pkg_rating.sp_finalize_rating` | `billing.sp_finalize_rating` |
| `invoice_preview` | `pkg_invoicing.fn_invoice_preview` | `billing.fn_invoice_preview` |
| `issue_invoice` | `pkg_invoicing.sp_issue_invoice` | `billing.sp_issue_invoice` |
| `invoice_lines` | `pkg_invoicing.fn_invoice_lines` | `billing.fn_invoice_lines` |
| `overdue` / `schedule_dunning` / `suspend_overdue` | `pkg_dunning.*` | `billing.fn_overdue_accounts` / `sp_schedule_dunning` / `sp_suspend_overdue` — declared in `postgres.py` but dunning is outside the slice |
| `ensure_tenant` | direct INSERT `tenants` + `subscriptions` (`oracle.py:150-177`) | n/a |

## 5. Findings-only exclusions (no migration)

| Item | Evidence |
|---|---|
| Analytics crons: `analytics_daily.py`, `audit_archive_weekly.py`, `search_reindex_weekly.py`, `storage_cleanup_daily.py`, `user_activity_daily.py` | `etl/legacy-extra/crontab` (python estate block) |
| CUSTBILL scheduler jobs `JOB_NIGHTLY_DUNNING`, `JOB_PURGE_AUDIT_LOG` | `schema/04_jobs.sql`, created DISABLED |
| Scala batch `services/analytics-service` (`UsageRollupJob.scala` etc.) | services/analytics-service/src/main/scala/…/batch/; analytics Postgres DB (`AppConfig.scala`, `PostgresMetricsRepository.scala`), no `OW_BILLING`/Oracle refs — not coupled to the estate |
| `gen_history_data.pl`, `gen_sample_data.pl` | `etl/legacy-extra/tools/` — data generators, not runtime |

## 6. Lineage DAG

```mermaid
flowchart LR
    subgraph App["legacy-billing app"]
        UI["facade.py / reports.py"]
        BE["backends (BILLING_BACKEND)"]
    end
    subgraph Oracle["Oracle OW_BILLING (read-only)"]
        PU["pkg_ow_util<br/>(f_md5_uuid, f_code_desc, log_msg)"]
        PP["pkg_plans"]
        PR["pkg_rating"]
        PI["pkg_invoicing"]
        PD["pkg_dunning (PROPOSED-unused)"]
        T1["plans/tenants/subscriptions/usage_events"]
        T2["rating_periods/rating_results/invoices/invoice_lines/credit_notes"]
        T3["invoice_header/invoice_line/customer_master/entity_attr_value"]
        AUD["billing_audit_log"]
        DUN["dunning_attempts/notifications"]
    end
    subgraph ETL["etl/legacy-extra batch chain"]
        EXT["oracle_custbill_extract.py"]
        SFTP["sftp_ingest_poll.ksh"]
        PARSE["parse_custbill_fixedwidth.sh"]
        FIN["finance_excel_report.pl"]
        CSV["finance_billing_*.csv"]
        API["GET /api/reports/finance"]
    end
    UI --> BE
    BE -->|signup/entitlement/change_plan| PP
    BE -->|usage/finalize| PR
    BE -->|preview/issue/lines| PI
    BE -->|overdue/dunning (not in slice)| PD
    PP --> PU & T1
    PR --> PU & T1 & T2
    PI --> PU & PR & T1 & T2
    PD --> DUN
    PU --> AUD
    EXT --> T3
    EXT --> SFTP
    SFTP --> PARSE --> FIN --> CSV --> API
    J1["JOB_NIGHTLY_DUNNING (disabled)"] -.-> PD
    J2["JOB_PURGE_AUDIT_LOG (disabled)"] -.-> AUD
```

## 7. Parallelism note

Independent conversion lanes (no call edges between them):
- **pkg_ow_util** — leaf; everything depends on it (wave 0, DEP-001).
- **pkg_plans** — needs only pkg_ow_util; independent of rating/invoicing.
- **pkg_rating** — needs only pkg_ow_util; independent of plans/invoicing.
- **pkg_invoicing** — needs pkg_ow_util + pkg_rating (DEP-002); must come after rating or in a later batch of the same wave.
- **CUSTBILL chain** (extract → pipeline → finance close + dashboard) — no routine
  calls; touches only `invoice_header/invoice_line/customer_master/entity_attr_value`
  reads. Fully parallel with the package lanes.
- **pkg_dunning** — isolated (its own tables + shared tenants/subscriptions writes);
  proposed out of scope per closure fact below.

## 8. pkg_dunning closure fact (decides its scope — reported, not decided)

`.migration/units/_slice/callgraph.md`: no `calls` edge from the slice closure
(`sp_issue_invoice`, `sp_change_plan`, signup path, CUSTBILL extract, finance close)
reaches `PKG_DUNNING`, and no closure member touches `DUNNING_ATTEMPTS` or
`NOTIFICATIONS` (its exclusive tables). Consistent with DEP-010 (PROPOSED: not in
scope) and `00_context.md` ("unless `04_dependency_register.md` shows a call edge —
it does not"). Caveat: `tenants`/`subscriptions` are shared-write tables — if
dunning is excluded, its `sp_suspend_overdue` writes are outside the migrated
surface, and `trg_subscriptions_hist` still fires on those updates (no slice
dependency either way).

## 9. Contradictions / gaps vs `04_dependency_register.md`

- DEP-008 says the scheduler jobs are "all disabled in the baseline" — confirmed by
  repo DDL (`enabled => FALSE`, `04_jobs.sql`); live `ALL_SCHEDULER_JOBS` is empty
  for the RO user, so live state is unverifiable from this principal (gap, not a
  contradiction).
- DEP-010 confirmed by the closure fact (§8).
- New table `FIXTURE_META` (1 row) exists in live but not in the slice tables list —
  classified fixture-infra.
- `CUSTOMER_MASTER_HIST` (0 rows) is trigger-maintained but unused by any slice path
  — classified proposed-unused.

## 10. Governance (grantee, privilege, object; cited view)

Governance views, same single pass (`"governance"` in
`.migration/inventory/oracle_dictionary_20260927b.json`).

| View | Rows | Fact |
|---|---|---|
| `ALL_TAB_PRIVS` (`TABLE_SCHEMA='OW_BILLING'`) | 1 | grantor OW_BILLING → grantee PUBLIC, `INHERIT PRIVILEGES` on `OW_BILLING` (schema-level privilege Oracle grants automatically), grantable=NO. **No table/column SELECT grants to any named user or role** — access comes via system privileges only. |
| `SESSION_PRIVS` | 3 | `CREATE SESSION`, `SELECT ANY TABLE`, `SELECT ANY DICTIONARY`. **`FLASHBACK ANY TABLE` is gone** — live-confirms D-026 (DBA revoke after STOP A). |
| `USER_SYS_PRIVS` | 3 | same three, all `admin_option=NO` (direct grants, not via role) |
| `USER_ROLE_PRIVS` | 0 | no roles granted to OW_BILLING_RO |
| `ROLE_SYS_PRIVS` | 0 | n/a (no roles) |

Implication: the RO principal is SELECT-only on the estate, holds no roles, and no
per-object grants exist beyond the automatic PUBLIC `INHERIT PRIVILEGES`. Nothing
in the estate's privilege surface contradicts DEP-013; the D-023/D-026 excess
privilege is verified revoked.
