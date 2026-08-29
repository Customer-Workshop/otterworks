# OW_BILLING unit inventory and complexity ranking

Scope: `OW_BILLING` only (`COMMISSION_DW` excluded at intake). Framework pinned at STOP B:
**Databricks Workflows + notebook tasks with Delta `MERGE`** — one unit is one job (`ow_tp_<unit>`),
restart-safe via `MERGE` on a declared natural key plus `ns`.

Census (live `user_objects`, 2026-08-28): 20 tables, 25 indexes, 5 packages (+5 bodies),
5 sequences, 7 triggers, 2 scheduler jobs, **0 views**. Zero views is the defining shape of this
estate: there is no declarative layer to lift, so every business rule sits in PL/SQL, in a trigger,
or in the batch chain — which is why the complexity weight lands on procedures, not SQL.

## Units

| Unit | Source | Layer | Weight | Why |
| --- | --- | --- | --- | --- |
| `dict` | wave 0 — `.migration/09_semantic_dictionary.md` | shared | **XL** | No Oracle→Databricks dialect skill exists in these repos; every Oracle semantic is decided here once. Blocks every other unit. |
| `bronze_core` | `01_tables.sql` (14 transactional tables) | bronze | M | Federated JDBC read → bronze Delta. Typed columns, real `DATE`s, FK-clean. Mostly mechanical. |
| `bronze_wide` | `02_horror.sql` (`CUSTOMER_MASTER` 155 cols, `INVOICE_LINE`, `INVOICE_HEADER`, `ENTITY_ATTR_VALUE`) | bronze | **L** | String dates (`VARCHAR2(9)` `DD-MON-YY`), EAV, denormalized copies, `GL_ACCT_CSV` splits, no FKs. Quarantine path lives here. PII masks land here. |
| `bronze_hist` | `CUSTOMER_MASTER_HIST`, `SUBSCRIPTIONS_HIST` | bronze | M | First-class tables per STOP A. `HIST_DT` is a `DD-MON-YY HH24:MI:SS` string; `HIST_OP` carries `UPD`/`DEL`; a deleted customer's last state may exist only here. |
| `bronze_custbill` | `etl/legacy-extra/jobs/sftp_ingest_poll.ksh` + `parse_custbill_fixedwidth.sh` | bronze | M | Fixed-width copybook `CBCUST01`, implied decimal `PIC 9(10)V99`, no validation in source. Lands to `/Volumes/ow_tp/bronze/landing/<ns>/custbill/`. |
| `silver_plans` | `02_pkg_plans.sql` | silver | M | `(+)` outer joins, `DECODE` tier mapping, `ROWNUM = 1` without `ORDER BY`, `31-DEC-99` sentinel, row-by-row subscription close-out. |
| `silver_rating` | `03_pkg_rating.sql` | silver | **XL** — pilot | Critical path. Cursor-loop usage summation on string date compares, three-month rollover bank, double cap, tier break at 101, suspension proration, and a persisted `rollover_units` that does not equal the computed one. |
| `silver_invoicing` | `04_pkg_invoicing.sql` | silver | **XL** — pilot | Depends on `silver_rating` through package globals, not through a table. Hardcoded `0.0825` tax split into two unrounded halves, `LEAST` credit cap, and a sequential credit burn-down that over-applies. |
| `silver_dunning` | `05_pkg_dunning.sql` + `JOB_NIGHTLY_DUNNING` | silver | L | Two scheduler entrypoints in one job action, `WHEN OTHERS THEN NULL` around the attempt insert, weekend shift by `DECODE` on `TO_CHAR(...,'DY')`, 14-day suspension sweep that mutates `tenants` and `subscriptions`. |
| `gold_finance` | `etl/legacy-extra/jobs/finance_excel_report.pl` | gold | M | The one consumer we can actually see. Its output is the closest thing to an acceptance test the business will recognise. |
| `recon` | parent-owned | shared | L | `LIVE` mode over federated JDBC; per-unit `*.recon.json`, rerunnable, `ns`-scoped. |

`pkg_ow_util` is not a unit. It is four primitives (`f_md5_uuid`, `f_code_desc`, `f_dt2str`,
`f_str2dt`) plus an autonomous-transaction logger; all five are dictionary entries in wave 0 and
shared helpers thereafter. Giving it its own job would make every other unit wait on it.

`JOB_PURGE_AUDIT_LOG` is not a unit either: 90-day retention on `BILLING_AUDIT_LOG`, hardcoded in
the job text, with its exception swallowed. It becomes a table property, not a job.

## Dependency edges that matter

- `silver_invoicing` **calls** `pkg_rating.compute_rating` and then reads `pkg_rating.g_overage_amount`
  directly. It does not read `RATING_RESULTS`. So invoicing must recompute rating inline in its own
  dataflow; wiring it to the persisted rating table changes results (see D-09).
- `silver_dunning` reads `INVOICES.status_cd = 40` and writes `TENANTS` and `SUBSCRIPTIONS` —
  tables `bronze_core` owns and `silver_plans` also writes. This is the only **write-target
  collision** in the estate, and it is why dunning cannot run in the same wave as plans.
- `gold_finance` reads the invoice estate and `CUSTOMER_MASTER`; it is a PII egress point, so it is
  the unit most likely to be rejected by the mask policy if written carelessly.
- Every silver unit depends on `dict`. No exceptions: a child that hits an Oracle semantic not in
  the dictionary stops and reports rather than deciding for itself.

## Where the schedule risk actually is

The three `XL` units are `dict`, `silver_rating`, and `silver_invoicing`, and they are serially
dependent. Rating and invoicing are also the two pilot units chosen at intake, which is the right
call for evidence quality and the wrong call for wall-clock: the pilot is the critical path, not a
side quest. Widening fan-out does not shorten it — only the gold and remaining bronze units
parallelize usefully.
