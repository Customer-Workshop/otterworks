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

A code unit's mapping names the tables that unit writes. Those tables are owned as data units
by a different child: a mapping is an evidence contract, not a write grant. Write ownership is
the manifest's `write_targets`, and it is disjoint across all 43 declared targets (checked
mechanically, see §6).

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
| P1-D5 | The `DD-MON-YY` string-date columns are migrated raw and byte-exact, plus a derived `<col>_parsed` date column. `f_str2dt` keeps returning NULL on unparseable input, and those rows form the declared anomaly set. The parsed columns are declared per table in `derived_fields` and generated from an explicit column list (18 names, 34 occurrences); a new `VARCHAR2(9)` column fails generation rather than being parsed on a guess. `HIST_DT` and `SERVICE_PERIOD` are `VARCHAR2(20)` in another format and stay raw with no parse. | Losing the raw string loses the evidence; cleaning the data changes the estate. A width is not a type, so the parse list is named, not inferred. |
| P1-D6 | Every converted load is idempotent: truncate-and-load or MERGE on the declared key. A recon rerun must not change target row counts. | Children are capped at 3 recon runs; a non-idempotent load makes rerun 2 meaningless. |
| P1-D7 | Trailing spaces are stripped for recon on fixed-width `CHAR`/`NCHAR` only. `VARCHAR2` keeps its bytes. | Oracle blank-pads `CHAR`, so its trailing spaces carry nothing; a `VARCHAR2` trailing space is data, and stripping it would let real loss pass the gate. |
| P1-D8 | One Lakebase branch per **wave**, created by the orchestrator before fan-out off the previous wave's branch. Children never create, reset or drop a branch; batches in a wave share it and are isolated by disjoint write targets. `allowed_targets.json` allowlists `mig-p1-w0/w1/w2`, so waves 3 and 4 continue on `mig-p1-w2`. | Per-batch creation of the same branch name races concurrent children, and re-cutting from `mig-p1-w0` each wave would drop everything earlier waves merged. Extending the allowlist is a parent decision, so the plan stays inside it. |
| P1-D10 | D10-01 was denied, so there is no Federation read path. Recon reads Oracle over JDBC from the Devin CIDRs instead, driving the official harness as a library (`recon.engine.run_recon`) with a repo-local Oracle source adapter: every tier, canonicalisation rule and tolerance is the harness's own, only the source connector is outside the tested matrix. Consequence, recorded by owner decision: **every pipeline-1 unit's recon grade is DEGRADED and no artifact, PR body or wave brief may call it an official harness verdict.** The STOP E packet states this instead of presenting a green gate. | The owner declined the security-group change and directed the JDBC route with that consequence accepted. Driving the harness as a library keeps the comparison math official — hand-written comparison SQL would make the arithmetic unofficial too, which is a strictly worse trade. `dbx-recon --family oracle` refuses at the CLI by design, and that refusal is respected: nothing pretends the adapter is tested. |
| P1-D9 | Package behavioural parity is proved by the row parity of the tables the package writes, plus a fixture run-diff, not by a live Oracle entrypoint call. Only `pkg_ow_util`'s MD5 parity has a live gate, because Oracle already stored the ids it produced. | The recon source path reads OW_BILLING rows, not PL/SQL. Calling an Oracle package from the source side would need an Oracle view over it — source DDL, which is forbidden. The live entrypoint comparison is a declared unverified path, not a fake gate. |

## 3. Dependencies — none left UNDECIDED

| ID | State | Owner | Routing point | Closure condition | Lead time |
|---|---|---|---|---|---|
| D10-01 — open 1521 on `sg-0eaf11f4434260e1e` to the Databricks serverless NAT range | **DENIED** by the owner at STOP C (2026-09-15) | engagement owner | closed | — | Closed as denied. There is no Lakehouse Federation on this run. The owner directed the JDBC-from-Devin route instead; see P1-D10 and §6. Consequence accepted in writing: every pipeline-1 recon grade is DEGRADED. |
| D10-02 — Lakebase `ow-tp-billing` provisioned, branch `mig-p1-w0` | ACCEPTED (in progress, parent-owned) | parent | wave 0 start | Doctor's branch-create and schema-grant rows pass on `mig-p1-w0` (they did at last run) | none |
| D10-03 — Kinesis stream + Debezium Server on EKS `otterworks-dev` | DEFERRED WITH CONDITION | parent | wave 0 batch w0-b | CDC stream lands rows in `ow_tp.bronze` and converges with a JDBC snapshot | Condition: if not delivered, w0-b falls back to JDBC + watermark (D-002), reports the CDC leg as follow-up, and does not block the pipeline |
| D10-04 — confirm the service principal `dhrov_spa` is the migration identity | **CONFIRMED** by the owner at this STOP C | engagement owner | STOP C reply (one line, alongside D10-01) | Owner confirms; or names the PAT, which reopens STOP A | Reversible. Everything already runs as the SP object id `2e90bc1d-…`. |
| D4-02 — application consumer census for invoice preview, invoice lines and overdue-account reads, and whether an API shim is needed | **RULE DECIDED** at STOP C; **census done** — `docs/migration/Pipeline1_D4-02_consumer_census.md` (3 runtime consumers: 1 shim, 1 flagged, 1 no-action) | engagement owner + application team | STOP E | Two things still need the customer: a named shim-removal owner, and the routing call for the one flagged consumer | Blocks STOP E, not the waves. Rule: package-entrypoint callers (`pkg_invoicing` preview, overdue/dunning entrypoints) go behind a thin temporary shim that preserves the call shape over Lakebase; direct table readers repoint to the Postgres wire protocol; anything fitting neither is flagged, not forced. The shim is temporary and the STOP E packet must name its removal owner. |
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
5. Recon source path: **no Federation** (D10-01 denied). Wave 0 installs the repo-local Oracle
   JDBC source adapter and the degraded-recon driver every later unit calls, reading Oracle
   read-only from the Devin CIDRs under `ow-tp/oracle/ow_billing_ro`.
6. `billing.rating_state`: the P1-D4 hand-off table, pinned here so wave 3 can run wide.
7. Convert `pkg_ow_util` (`f_md5_uuid`, `f_str2dt`, `f_code_desc`, `log_msg`) to PL/pgSQL plus
   the Delta-side equivalents. The MD5/UUID parity proof is this batch's reason to exist. It
   runs against ids Oracle itself produced: `billing.md5_parity_input` is seeded through
   the read-only JDBC path with the exact inputs behind the stored ids (`rating_results.period_id`,
   `invoices.period_id || 'invoice'`, `invoice_lines.invoice_id || line_no`), and the three
   ops put those stored ids next to `billing.f_md5_uuid` recomputed from the same inputs.
   Add the NULL, empty-string and non-ASCII inputs as a fixture vector beside it. If parity
   fails, the pipeline stops — every downstream primary key derives from it.
   `f_code_desc` is graded at the wave-1 CODES gate (it reads `billing.codes`, which does not
   exist yet in wave 0) and `f_str2dt` at each string-date unit's `str_date_parse` op.

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
| 2 | 4 | w2-a (U-03, U-21), w2-b (U-12), w2-c (U-13), w2-d (U-14, U-15), w2-e (U-19, U-26) | 8 | `wave-2.json` |
| 3 | 4 | w3-a (U-04, U-05, U-22), w3-b (U-06, U-07, U-23), w3-c (U-08), w3-d (U-09, U-10, U-24) | 10 | `wave-3.json` |
| 4 | 1 (serial) | w4-a (U-25, created paused) | 1 | `wave-4.json` |

**On the width discrepancy.** The engagement contract says pilot 3 then 5; the approved
analysis describes wave 3 as "width 4". Waves 2 and 3 ship at **width 4**, not 5, because the
source query cap is 4 concurrent Oracle reads for a whole wave and every batch takes a live
read at its gate — a width of 5 on wave 2 (five batches) would put five concurrent queries on
the source. Wave 3 has four batches, so the cap is not binding there either way. All 27 units
and the batch boundaries are unchanged; wave 2 runs five batches with at most four in flight.
`gen_wave_manifests.py` now refuses to emit a wave whose width exceeds the cap.

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
| 0 | 2 serial | ~3 h | ~1 h | JDBC recon wiring replaces the Federation step (D10-01 denied) |
| 1 | 3 | ~1.5 h | ~1.5 h | Pilot: add ~1 h to harvest dialect feedback into the skill before wave 2 |
| 2 | 5 | ~1.5 h | ~2 h | `CUSTOMER_MASTER` (25k × 155 cols) is the long pole |
| 3 | 4 | ~1.5 h | ~2 h | Plus the post-merge op-diff re-runs |
| 4 | 1 | ~1 h | ~0.5 h | Job created paused |

That is roughly 1.5–2 working sessions of Devin time end-to-end, and the schedule is
dominated by human review throughput. The source-query cap of 4 concurrent Oracle reads binds
wave 2, which is why it runs its five batches at width 4; the largest unit, `INVOICE_LINE` at
150,000 rows, is one chunked read.

**Recon cost** (from `dbx-recon estimate`, summed per wave, in the manifests):

| Wave | Source statements | Target statements | Source rows fetched |
|---|---|---|---|
| 0 | 23 | 19 | 193,750 |
| 1 | 57 | 45 | 169,668 |
| 2 | 85 | 65 | 33,471 |
| 3 | 191 | 148 | 31 |
| 4 | 17 | 11 | 2 |

Wave 3 is statement-heavy and row-light: ten small units, most of them behavioural.

## 6. The mechanical recon gate

The official harness is the only merge authority. No hand-written comparison SQL, ever. A
fixture PASS is never a merge verdict.

Every child runs, per unit:

```
python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
python3 databricks/migration/recon/run_degraded_recon.py --unit <unit> \
  --mapping .migration/units/<unit>/mapping_spec.json \
  [--ops .migration/units/<unit>/ops.json] \
  --tolerances .migration/03_recon_tolerances.json \
  --canonicalization databricks/migration/recon/canonicalization.oracle.json \
  --mode <transactional|live> --source-dsn-secret OW_TP_ORACLE_RO \
  --target-kind <lakebase|databricks> --target-secret <OW_TP_LAKEBASE_DSN|DATABRICKS_MIGRATION_SQL> \
  --target-catalog ow_tp --target-schema <billing|silver> \
  --allowed-targets-file .migration/allowed_targets.json \
  --seed 0 --depth <threshold|sampled|full> --out .migration/recon/<unit>/
```

The exact command for each unit is in that unit's batch brief in the manifest, so no child
composes one by hand. Operational units run `--mode transactional --target-kind lakebase`
against their wave's Lakebase branch; analytical units run `--mode live --target-kind
databricks`. The source side reads Oracle directly over JDBC (P1-D10, D10-01 denied);
`dbx-recon run --family oracle` still refuses at the CLI and is not used.

Op SQL runs on two different engines: the source side is **Oracle dialect** against
`OW_BILLING`, the target side is Lakebase PL/pgSQL or DBSQL. Source aliases are quoted
lowercase so the tier-4 diff matches columns by name across Oracle's upper-case folding. The
string-date parse on the source side is `TO_DATE(col DEFAULT NULL ON CONVERSION ERROR,
'DD-MON-YY')` — the same NULL-on-bad-input behaviour as `f_str2dt`, so a malformed date is
compared as an anomaly instead of aborting the run. No op calls an Oracle package: that would
need an Oracle view over it, which is source DDL (see P1-D9).

PASS requires all of:

- row counts equal, exactly;
- money equal, exactly — one cent is a FAIL, not a tolerance;
- other floats within 1e-9 relative;
- dates equal after ISO canonicalization, and the unparseable-date set equal as a set. The
  raw string-date columns are compared byte-exact; the `_parsed` companions are proved by the
  unit's `str_date_parse` op, which parses the same raw bytes on the source side, rather than
  graded against the raw column they derive from;
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

**Package entrypoints are a declared unverified path.** For `pkg_plans`, `pkg_rating`,
`pkg_invoicing` and `pkg_dunning`, no op compares a live Oracle entrypoint result with the
converted one, because that would need an Oracle view over the package and the source is
read-only (P1-D9). Their merge evidence is the live row parity of the tables they write plus
a fixture run-diff: run the legacy package and the converted one over the same fixture state
and diff the written rows with the harness in fixture mode. The PR states the fixture grade
explicitly; a fixture PASS alone is never a merge verdict, the live row parity is.

**The recon path after D10-01 was denied (P1-D10).** There is no Federation, so no unit can
produce an official harness verdict. Each gate instead runs the harness's own engine over a
repo-local Oracle JDBC source adapter: same tiers, same canonicalisation profile, same frozen
tolerances, money exact, counts exact, 1e-9 relative on other floats, ISO-canonicalised dates,
anomaly sets compared as sets, idempotency proven by rerun. The target side is always read back
from the target platform itself, never from the CDC output the unit produced. Every result is
stamped `official_verdict: false`, `grade: DEGRADED`, `reason: d10_01_denied`, and each PR body
and the wave brief repeat that wording. Unverified paths stay listed as unverified. A DEGRADED
result is the agreed evidence standard for this run, and the STOP E packet says exactly that
rather than presenting a green official gate.

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
| D10-01 denied (realised) | Every unit's recon grade is DEGRADED and nothing may be labelled official. The risk that remains is a reader mistaking a degraded verdict for a harness verdict, so the stamp is in the artifact, the PR body and the STOP E packet. |
| MD5 parity fails in wave 0 | Pipeline stops; every downstream key depends on it. |
| Debezium LogMiner against 26ai Free | JDBC + watermark fallback (D-002); the CDC leg is fixed beside the correctness path. |
| Wave 3 intra-wave coupling | Contract pinned in wave 0, fixture-only development, post-merge op-diff re-run at the gate. Splittable into two serial waves if the pilot says so. |
| `CUSTOMER_MASTER` wide diff | Alone in its batch, full depth, raw+parsed date columns compared separately. |
| Oracle redo volume from supplemental logging | Hourly RMAN housekeeping already installed (D-001). Watch it; do not add source writes. |

## 9. STOP C — outcome (approved 2026-09-15)

The owner approved the plan and the wave manifests, and answered the dependencies:

- **D10-01: DENIED.** No security-group change, no Lakehouse Federation. Recon runs over JDBC
  from the Devin CIDRs, every pipeline-1 unit is graded DEGRADED, and nothing may be presented
  as an official harness verdict (P1-D10).
- **D10-04: CONFIRMED.** The service principal is the migration identity.
- **D4-02: rule decided**, census mechanical and in progress; it gates STOP E, not the waves.
- Execution authorised: wave 0 serial, then the width-3 pilot of wave 1, feedback harvest, then
  waves 2–4. Widths are 4, not the 5 named at STOP C, so the fan-out cannot exceed the
  4-concurrent-read source cap; batch composition is unchanged.
