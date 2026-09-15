# Pipeline 1 — monthly invoicing: migration plan (STOP C)

Oracle `OW_BILLING` → Lakebase Postgres (operational) + Unity Catalog Delta (analytical),
with a CDC leg. This plan turns the approved analysis
(`docs/migration/Pipeline1_invoicing_analysis.md`, STOP B accepted) into something executable:
every dependency decided or escalated, the wave manifests the fan-out workflow reads, the
mechanical recon gate, and the governance mapping.

Nothing here has been executed. No wave has launched, no unit has been converted, no PR is
open, and no grant has been run. This document is the STOP C artifact.

- Run branch (base for every PR): `tp-run/databricks-20260915T045714Z`
- Manifests: `.migration/waves/wave-0.json` … `wave-4.json`
- Mappings and cost: `.migration/units/<unit>/mapping_spec.json`, `ops.json`, `cost_estimate.json`
- Governance: `databricks/migration/governance/p1_governance_map.json`,
  `p1_grants_approved.sql`
- Canonicalization profile: `databricks/migration/recon/canonicalization.oracle.json`
- Generators (idempotent, `--check` in CI): `databricks/migration/tools/gen_mapping_specs.py`,
  `gen_recon_estimates.py`, `gen_wave_manifests.py`

## 1. Scope

27 units, 63 pipeline-1 objects, exactly as approved at STOP B. `FIXTURE_META` and the two
Perl fixture generators stay out.

| Track | Units |
|---|---|
| Operational → Lakebase `ow_tp.billing` | U-01 TENANTS, U-02 PLANS, U-03 SUBSCRIPTIONS, U-04 RATING_PERIODS, U-05 RATING_RESULTS, U-06 INVOICES (modern), U-07 INVOICE_LINES (modern), U-08 CREDIT_NOTES, U-09 DUNNING_ATTEMPTS, U-10 NOTIFICATIONS, U-11 CODES, U-12 CUSTOMER_MASTER, U-13 ENTITY_ATTR_VALUE |
| Analytical → Delta `ow_tp.silver` | U-14 CUSTOMER_MASTER_HIST, U-15 SUBSCRIPTIONS_HIST, U-16 INVOICE_HEADER (legacy), U-17 INVOICE_LINE (legacy), U-18 USAGE_EVENTS, U-19 BILLING_AUDIT_LOG |
| Code | U-20 pkg_ow_util, U-21 pkg_plans, U-22 pkg_rating, U-23 pkg_invoicing, U-24 pkg_dunning |
| Orchestration | U-25 JOB_NIGHTLY_DUNNING (created paused), U-26 JOB_PURGE_AUDIT_LOG (created paused) |
| Transport | U-27 CDC (Debezium → Kinesis → Lakeflow AUTO CDC) |

Modern `INVOICES`/`INVOICE_LINES` (5 rows, Lakebase) are not legacy
`INVOICE_HEADER`/`INVOICE_LINE` (168,750 rows, Delta). Every mapping spec carries a
`generation` field so a child cannot confuse them (D9-01).

A code unit's mapping names the tables that unit writes, plus its read-only entrypoints as
Tier-4 ops. Those tables are owned as data units by a different child: a mapping is an
evidence contract, not a write grant. Write ownership is the manifest's `write_targets`, and
it is disjoint across all 41 declared targets (checked mechanically, see §6).

## 2. Decisions taken in this plan

These are plan-level engineering decisions. They bind every child. They do not move a
tolerance, a scope line or a dependency posture — those need a human reply recorded by the
parent in `.migration/06_decisions.md`.

| ID | Decision | Why |
|---|---|---|
| P1-D1 | `pkg_ow_util.log_msg` (PRAGMA AUTONOMOUS_TRANSACTION) becomes a best-effort writer on its own connection that cannot fail or be rolled back by its caller, and swallows its own errors. | Reproduces the observable behaviour: audit rows survive a caller rollback, and a failed audit write never fails the business transaction. |
| P1-D2 | `WHEN OTHERS THEN NULL` in `pkg_dunning` and `JOB_PURGE_AUDIT_LOG` is reproduced, not fixed. The recon baseline is the rows the legacy code actually wrote. | Swallowed exceptions are contract until a human decides otherwise. Each occurrence is documented in the unit PR so the customer can choose later. |
| P1-D3 | Oracle `DATE`/`TIMESTAMP` carry no zone; the migration assumes and declares UTC, and keeps the time part (`timestamp(0)` / `TIMESTAMP`). | Recon needs one declared assumption. If parity breaks on it, a child reports it — no child retunes the assumption. |
| P1-D4 | Package globals become explicit state, not session state. The `pkg_rating` → `pkg_invoicing` hand-off (`g_overage_amount`) is the table `billing.rating_state`, keyed by `(tenant_id, period_id)`, written by `sp_finalize_rating` and read by `sp_issue_invoice`. Its shape is pinned in wave 0 so w3-a and w3-b can be built concurrently. | Two Postgres sessions do not share a package global. Pinning the contract in wave 0 is what lets rating and invoicing run in the same wave. |
| P1-D5 | The 37 `DD-MON-YY` string-date columns are migrated raw and byte-exact, plus a derived parsed column. `f_str2dt` keeps returning NULL on unparseable input, and those rows form the declared anomaly set. | Losing the raw string loses the evidence; cleaning the data changes the estate. |
| P1-D6 | Every converted load is idempotent: truncate-and-load or MERGE on the declared key. A recon rerun must not change target row counts. | Children are capped at 3 recon runs; a non-idempotent load makes rerun 2 meaningless. |

## 3. Dependencies — none left UNDECIDED

| ID | State | Owner | Routing point | Closure condition | Lead time |
|---|---|---|---|---|---|
| D10-01 — open 1521 on `sg-0eaf11f4434260e1e` to the Databricks serverless NAT range | **BLOCKED — escalated at this STOP C** | engagement owner | STOP C reply | Federation catalog `ow_billing_fed` reads `OW_BILLING` and `dbx-recon --family databricks` connects to it | Asked 2026-09-15; needs a security-group change plus a Federation connection. Assume one business day after approval. Wave 0 can start without it; the first merge-evidence recon cannot. |
| D10-02 — Lakebase `ow-tp-billing` provisioned, branch `mig-p1-w0` | ACCEPTED (in progress, parent-owned) | parent | wave 0 start | Doctor's branch-create and schema-grant rows pass on `mig-p1-w0` (they did at last run) | none |
| D10-03 — Kinesis stream + Debezium Server on EKS `otterworks-dev` | DEFERRED WITH CONDITION | parent | wave 0 batch w0-b | CDC stream lands rows in `ow_tp.bronze` and converges with a JDBC snapshot | Condition: if not delivered, w0-b falls back to JDBC + watermark (D-002), reports the CDC leg as follow-up, and does not block the pipeline |
| D10-04 — confirm the service principal `dhrov_spa` is the migration identity | ACCEPTED PROVISIONALLY (D-005), still open in the ledger | engagement owner | STOP C reply (one line, alongside D10-01) | Owner confirms; or names the PAT, which reopens STOP A | Reversible. Everything already runs as the SP object id `2e90bc1d-…`. |
| D4-02 — application consumer census for invoice preview, invoice lines and overdue-account reads, and whether an API shim is needed | **OPEN — escalated at this STOP C** | engagement owner + application team | STOP C reply, or STOP D at the latest | A named list of services and connection strings that read those three surfaces, and a decision to repoint vs. shim | Blocks STOP E, not the waves. Asked now because a shim is application work with its own lead time. |
| D6-01 — `pkg_ow_util` shared by all four packages, owned by wave 0 | IMPLEMENTED IN PLAN | parent | wave 0 batch w0-a | Wave 0 merges with the MD5 parity proof | none |
| D8-01 — orphan rows and malformed strings are reproduced, not cleaned | IMPLEMENTED IN PLAN | parent | every unit gate | Anomaly sets compared as sets (tolerances v1) | none |
| D9-01 — modern vs legacy invoice generation | IMPLEMENTED IN PLAN | parent | every mapping spec | `generation` field present in all 27 mappings (it is) | none |
| D2-01 — byte-for-byte `f_md5_uuid` parity | IMPLEMENTED IN PLAN | wave 0 child | wave 0 gate | Parity vector proven on both targets; a failure stops the pipeline | none |
| D2-02 — autonomous-transaction logging semantics | DECIDED (P1-D1) | parent | wave 0 gate | Converted `log_msg` demonstrates caller-rollback survival on the fixture | none |
| D10-05 — STOP E cutover authorization | NOT YET DUE | engagement owner | STOP E | Never default-accepted; Devin never holds the cutover principal | — |

Pipeline-2/3 dependencies (D3-01, D4-01, D5-01, D7-01) are out of scope here and stay with
the parent.

## 4. Scaffolding delta (wave 0, serial)

Wave 0 is two serial batches and everything else waits on it.

**w0-a — shared scaffolding + U-20 `pkg_ow_util`**

1. Lakebase: schema `billing` conventions on the existing branch `mig-p1-w0` (do not recreate
   it); apply the approved Lakebase grants from `p1_grants_approved.sql` (APPROVED rows only).
2. Unity Catalog: `ow_tp.bronze` / `silver` / `gold` conventions, the landing volume
   `/Volumes/ow_tp/bronze/landing`, secret scope `ow_tp` referenced by name only.
3. DAB skeleton for `ow_tp_p1_*` jobs and pipelines. No schedule enabled. No cluster created;
   the existing serverless warehouse `565cd2fd713738c4` is the only compute.
4. Recon wiring: the pinned canonicalization profile
   `databricks/migration/recon/canonicalization.oracle.json` (the 37 string-date columns, the
   Oracle NUMBER/CHAR/DATE rules) is the profile every unit passes to `dbx-recon`.
5. Lakehouse Federation: create the `ow_billing_fed` connection and catalog. It is what the
   recon source side reads and what the code units' Tier-4 ops query. Blocked on D10-01.
6. `billing.rating_state`: the P1-D4 hand-off table, pinned here so wave 3 can run wide.
7. Convert `pkg_ow_util` (`f_md5_uuid`, `f_str2dt`, `f_code_desc`, `log_msg`) to PL/pgSQL plus
   the Delta-side equivalents. The MD5/UUID parity proof is this batch's reason to exist: a
   fixed input vector covering every call shape in the estate plus NULL, empty string and
   non-ASCII, proven byte-for-byte on both targets. If it fails, the pipeline stops — every
   downstream primary key derives from it.

**w0-b — U-27 CDC transport**

Debezium Server on the existing EKS cluster → Kinesis on-demand → Lakeflow pipeline
`ow_tp_p1_cdc_ingest` with AUTO CDC into `ow_tp.bronze`. Capture secret `ow-tp/oracle/dbzuser`
by name. Supplemental logging is already in place (D-001) and Oracle is not touched again.
Recon is stream-vs-batch convergence at threshold depth; the row contract for those three
tables belongs to their own units. On failure or a missing D10-03: JDBC + watermark fallback
(D-002), stated plainly, not blocking.

## 5. Execution schedule

| Wave | Width | Batches | Units | Manifest |
|---|---|---|---|---|
| 0 | 1 (serial) | w0-a, w0-b | 2 | `.migration/waves/wave-0.json` |
| 1 (pilot) | 3 | w1-a (U-01, U-02, U-11), w1-b (U-18), w1-c (U-16, U-17) | 6 | `wave-1.json` |
| 2 | 5 | w2-a (U-03, U-21), w2-b (U-12), w2-c (U-13), w2-d (U-14, U-15), w2-e (U-19, U-26) | 8 | `wave-2.json` |
| 3 | 5 | w3-a (U-04, U-05, U-22), w3-b (U-06, U-07, U-23), w3-c (U-08), w3-d (U-09, U-10, U-24) | 10 | `wave-3.json` |
| 4 | 1 (serial) | w4-a (U-25, created paused) | 1 | `wave-4.json` |

**On the width discrepancy.** The engagement contract says pilot 3 then 5; the approved
analysis describes wave 3 as "width 4". Both are satisfied: wave 3 has four batches, so a
width cap of 5 is not binding. The manifests carry width 5 for waves 2 and 3 to match the
recorded contract, and the batch count does the rest. No scope or ordering changed.

**Wave 3 runs four batches that depend on each other.** That is deliberate and it is why
P1-D4 exists: w3-b (invoicing) reads rating state and credit notes, w3-d (dunning) reads
invoices. Each child codes against the contract pinned in wave 0 and reconciles against the
fixture, never against another child's in-flight branch. At wave close the orchestrator
re-runs the Tier-4 op diffs of w3-b and w3-d after their inputs merge; a contract mismatch is
a wave-level finding, not something a child routes around. If the pilot shows this coupling
costs more than it saves, wave 3 can be split into two serial waves without changing scope —
that is a plan amendment, and it needs the parent.

**Wall-clock projection.** Serial floor is wave 0 (2 batches) + 4 wave gates + wave 4, all
single-threaded. With a 90-minute child budget and a 3-round review cap, and assuming the
reviewer is the constraint at 2 batches per round:

| Wave | Batches | Parallel child time | Gate + review | Notes |
|---|---|---|---|---|
| 0 | 2 serial | ~3 h | ~1 h | Federation setup is D10-01-dependent |
| 1 | 3 | ~1.5 h | ~1.5 h | Pilot: add ~1 h to harvest dialect feedback into the skill before wave 2 |
| 2 | 5 | ~1.5 h | ~2 h | `CUSTOMER_MASTER` (25k × 155 cols) is the long pole |
| 3 | 4 | ~1.5 h | ~2 h | Plus the post-merge op-diff re-runs |
| 4 | 1 | ~1 h | ~0.5 h | Job created paused |

That is roughly 1.5–2 working sessions of Devin time end-to-end, and the schedule is
dominated by two things that are not compute: the D10-01 lead time before any merge-evidence
recon can run, and human review throughput. The source-query cap of 4 concurrent Oracle reads
is not binding at these widths (worst case wave 2 wants 5, and the largest unit,
`INVOICE_LINE` at 150,000 rows, is one chunked read).

**Recon cost** (from `dbx-recon estimate`, summed per wave, in the manifests):

| Wave | Source statements | Target statements | Source rows fetched |
|---|---|---|---|
| 0 | 23 | 19 | 193,750 |
| 1 | 57 | 45 | 169,668 |
| 2 | 85 | 65 | 33,471 |
| 3 | 191 | 148 | 31 |
| 4 | 17 | 11 | 2 |

Wave 3 is statement-heavy and row-light: ten small units, most of them behavioural, each
with Tier-4 op diffs.

## 6. The mechanical recon gate

The official harness is the only merge authority. No hand-written comparison SQL, ever. A
fixture PASS is never a merge verdict.

Every child runs, per unit:

```
dbx-recon run --unit <unit> --family databricks \
  --mapping .migration/units/<unit>/mapping_spec.json \
  [--ops .migration/units/<unit>/ops.json] \
  --tolerances .migration/03_recon_tolerances.json \
  --canonicalization databricks/migration/recon/canonicalization.oracle.json \
  --mode <transactional|live> --source-dsn-secret OW_BILLING_RO_DSN \
  --target-kind <lakebase|databricks> --target-secret <OW_TP_LAKEBASE_DSN|DATABRICKS_MIGRATION_SQL> \
  --target-catalog ow_tp --target-schema <billing|silver> \
  --allowed-targets-file .migration/allowed_targets.json \
  --seed 0 --depth <threshold|sampled|full> --out .migration/recon/<unit>/
```

The exact command for each unit is in that unit's batch brief in the manifest, so no child
composes one by hand. Operational units run `--mode transactional --target-kind lakebase`
against their wave's Lakebase branch; analytical units run `--mode live --target-kind
databricks`. The source side always reads Oracle through Lakehouse Federation as
`--family databricks`; `--family oracle` is an untested adapter and the CLI refuses it.

PASS requires all of:

- row counts equal, exactly;
- money equal, exactly — one cent is a FAIL, not a tolerance;
- other floats within 1e-9 relative;
- dates equal after ISO canonicalization, and the unparseable-date set equal as a set;
- declared anomaly sets (orphan invoice lines, malformed lists) equal as sets;
- primary-key / identity sets equal;
- operational units only: CDC watermark and ordering checks, plus constraint, index and
  sequence parity;
- no write outside the batch's declared `write_targets`, and no source-side write;
- observed source row counts match the manifest's `source_volume_assertions`;
- evidence states whether it is fixture or live, and who owns the environment.

Evidence lands in `.migration/recon/<unit>/summary.md` and `result.json` and is quoted in the
unit PR. Children write nothing else under `.migration/`; the fan-out workflow is the single
writer of wave results. Caps: 3 full recon runs per unit, 3 review rounds, 3 same-class
failures trips the breaker and halts the wave.

**Units with no data to prove.** `CUSTOMER_MASTER_HIST`, `SUBSCRIPTIONS_HIST` and
`BILLING_AUDIT_LOG` are empty today. Their verdict is schema parity plus an empty-set
assertion, recorded as **NOT DATA-PROVEN** in `summary.md` and in the PR. The Oracle scheduler
jobs are DISABLED, so U-25 and U-26 have no live run to compare against; they are verified by
fixture run-history equivalence, and that gap is stated, not papered over.

**Degraded path while D10-01 is open.** Without Federation there is no supported live read of
Oracle from the harness. A child that reaches its gate with D10-01 still open runs the gate on
the fixture, marks the verdict DEGRADED in `summary.md`, and reports `status=BLOCKED` with
`d10_01_federation`. Devin does not invent an unofficial comparison and does not merge on a
degraded verdict. This is why D10-01 is a STOP C blocker rather than a footnote.

## 7. Governance

`databricks/migration/governance/p1_governance_map.json` maps each source privilege to a
target statement with a status of PROPOSED, APPROVED or GAP.

- `PUBLIC INHERIT PRIVILEGES` on `OW_BILLING` → a proposed group grant. PROPOSED only; PUBLIC
  never auto-maps.
- `OW_BILLING` object ownership → GAP: Unity Catalog ownership is an account-level decision.
- `OW_BILLING_RO SELECT` → proposed analytical reader group. PROPOSED.
- `C##DBZUSER` capture privileges → GAP: no Unity Catalog analogue.
- Oracle role membership and masking/redaction policies → GAP: not readable at the access tier
  we have, so they are unverifiable rather than assumed absent.
- Migration working-target grants for the SP → APPROVED.
- Plaintext credentials in `etl/config.ini` → GAP: converted jobs use secret names; rotating
  the exposed values is the customer's action (D7-01).

`p1_grants_approved.sql` contains the APPROVED rows only: catalog/schema/volume grants for the
migration service principal on `ow_tp`, and the commented Lakebase block applied by wave 0.
The orchestrator runs it once. Children never create, modify or execute a grant. Production
catalog grants are a STOP E action and are not in the file.

## 8. Risks

| Risk | Handling |
|---|---|
| D10-01 not approved | Every merge-evidence recon is DEGRADED and no unit merges. Escalated here. |
| MD5 parity fails in wave 0 | Pipeline stops; every downstream key depends on it. |
| Debezium LogMiner against 26ai Free | JDBC + watermark fallback (D-002); the CDC leg is fixed beside the correctness path. |
| Wave 3 intra-wave coupling | Contract pinned in wave 0, fixture-only development, post-merge op-diff re-run at the gate. Splittable into two serial waves if the pilot says so. |
| `CUSTOMER_MASTER` wide diff | Alone in its batch, full depth, raw+parsed date columns compared separately. |
| Oracle redo volume from supplemental logging | Hourly RMAN housekeeping already installed (D-001). Watch it; do not add source writes. |

## 9. STOP C — what the user is being asked

Approve this plan and the wave manifests so wave 0 can start, and answer two dependencies:

1. **D10-01** — open port 1521 on `sg-0eaf11f4434260e1e` to the Databricks serverless NAT
   range (us-east-1) and nothing else, so Lakehouse Federation can read `OW_BILLING`. Without
   it every recon verdict is DEGRADED and no unit is merge-eligible.
2. **D4-02** — who reads invoice preview, invoice lines and overdue accounts today, and do we
   repoint them or build an API shim. Needed by STOP E, asked now for lead time.

D10-04 (the service principal as migration identity) can be confirmed in the same reply; work
already runs under it.
