watermark: 2026-09-29T20:14:55Z
audited_ledger_sha: 61291c773635976017dac7f7c06e2ab959a96d4a

# Cutover audit + watermark recon: OW_BILLING (Oracle) -> ow_tp_mmp_live (MongoDB Atlas)

Verdict: **PASS. Countersigned**, with the non-blocking findings in section 6.

Independent session: migrated nothing, ran no loader, wrote nothing to Atlas or Oracle, merged
and approved no PR. Did not read child chats. Aggregate evidence only; no row values below.

## 1. Inputs
| Item | Value |
|---|---|
| Ledger | `migrate/billing/0-setup` @ `61291c77` (read at audit start and re-checked at report time; unchanged) |
| Mapping spec | `map-1`, sha256 `e6fda96035536d1eb44f7ffc48f49a492a64fc65687f56ba8b2c38119220d08a` (equals the evidence pack) |
| Tolerances | v1, sha256 `03b3c6cc0bc6ebf1e757a05c64cd071656258577b7df2e4d6d46784948ee2e1e` (equals the evidence pack) |
| Harness | mongo-migration plugin 0.3.2 harness, installed editable into `~/.venvs/recon`; `recon selftest` PASS (9 canonicalization rules) |
| Access | source `OW_TP_ORACLE_RO_DSN` (read-only), target `OW_TP_MMP_TARGET_URI` (read only used); secret names only |
| Flags (every gate) | `--family oracle --mapping .migration/03_mapping_spec.json --tolerances .migration/02_tolerances.json --canonicalization <plugin>/profiles/oracle.md --mode live --target-class migration_cluster --target-db ow_tp_mmp_live --allowed-targets-file .migration/allowed_targets.json --source-concurrency 1` (same as recon/wave-2) |

## 2. Watermark (step 1) and source stability
`python .migration/baseline/oracle_recount.py`, read-only, literal SQL, run three times, serialized with every other source read:

| Recount | Completed (UTC) | Result |
|---|---|---|
| W (before gates) | 2026-09-29T20:14:55Z | exit 0, `match=true`, `diffs=[]`: 20 tables, customer_master 25,000, invoice_header 18,750, invoice_line 150,000, orphans 37, customer_master columns 155 |
| after the five gates | 2026-09-29T20:22:04Z | exit 0, `match=true`, `diffs=[]`, identical to W |
| after the U4 re-gate (F1) | 2026-09-29T20:23:50Z | exit 0, `match=true`, `diffs=[]`, identical to W |

Source did not move during the audit. No mismatch occurred, so no double-run drift analysis was needed; no unit is DRIFT-EXPLAINED.

## 3. Full recon gate at W (step 2)
One live run per unit, serialized, from each unit PR's head (heads re-checked with `git ls-remote` at report time).

| Unit | PR / head | Collections | T1 | T2 | T3 | T4 | Verdict | merge_eligible |
|---|---|---|---|---|---|---|---|---|
| U0-reference | #1742 `f70db00e` | codes, tenants, plans | 3 | 6 | 104 | - | PASS | true |
| U1-customers | #1743 `55028dbb` | customers | 2 | 15 | 33,333 | - | PASS | true |
| U2-invoices | #1745 `759a91c0` | invoices, quarantine_invoice_line | 3 | 5 | 168,750 | - | PASS | false (scoped embed, see F2) |
| U3-billing-core | #1744 `b46bacb7` | subscriptions, subscriptions_hist, usage_events, rating_periods, rating_results, billing_invoices, credit_notes, dunning_attempts, notifications, billing_audit_log | 11 | 28 | 901 | - | PASS | true |
| U4-app-backend | #1746 `ddafb31a` | codes, tenants, plans + `ops.live.json` | 3 | 6 | 104 | 6 | PASS | true |
| U4-app-backend (re-gate, F1) | #1746 `34d40006` | same | 3 | 6 | 104 | 6 | PASS | true |

`sequences` is not a mapped collection in `map-1`, so the harness does not gate it; it is covered by probe P6.
U4 `ops.post-wave.json` replayed through the harness tier-4 comparator (live source vs Atlas, read-only) at both
U4 heads: 7/7 passed, 0 findings each time (invoice_headers_by_status, invoice_lines_by_type, invoice_multi_line_count,
billing_invoices_by_status, billing_invoice_lines, subscriptions_rows, admin_report_balances).

Every harness run warned `RECON_REDACT_SALT` unset (F4). No gate recorded a finding.

## 4. Evidence-pack sampled re-checks (step 3)
Independent read-only probe (literal SQL, `OW_BILLING.<TABLE>` qualified, aggregates only), run inside the W window:

| # | Evidence-pack claim | Source | Target | Result |
|---|---|---|---|---|
| P1 | `invoices.lines` length per header = INVOICE_LINE per header | 18,750 headers, 149,963 attached lines | 18,750 docs, 149,963 embedded | 0 missing, 0 extra, 0 per-invoice length mismatches; length distributions equal |
| P2 | 37 quarantine keys as a set | 37 orphan LINE_IDs | 37 `quarantine_invoice_line` docs | set-equal (symmetric difference 0); 0 quarantined keys also embedded; 149,963 distinct embedded + 37 = 150,000 = INVOICE_LINE |
| P3 | `customers.attributes` length per customer = ENTITY_ATTR_VALUE per customer | 25,000 customers, 8,333 EAV rows, 0 non-customer EAV rows | 25,000 docs, 8,333 elements | 0 missing, 0 extra, 0 per-customer length mismatches |
| P4 | runbook V3 demo customer keeps the duplicate TAX_REGION_OVERRIDE | 2 EAV rows, 2 TAX_REGION_OVERRIDE | 1 doc, 2 elements, 2 TAX_REGION_OVERRIDE | attribute-name counts equal; eav_id order equal |
| P5a | money to the cent: invoices.total_amt | sum over 18,750 | sum over 18,750 | equal to the cent and exactly equal (Decimal) |
| P5b | money to the cent: customers.cur_bal_amt | sum over 25,000 | sum over 25,000 | equal to the cent and exactly equal (Decimal) |
| P6 | sequences seeded from last_number | 5 OW_BILLING sequences | 5 `sequences` docs | names equal; last_number and increment equal for 5/5 |
| P7 | runbook V2 target counts | - | customers 25,000; invoices 18,750 (149,963 embedded lines); quarantine_invoice_line 37; billing_invoices 3; subscriptions 69; usage_events 814; tenants 69; plans 3; codes 32 | 10/10 equal to V2 |

Cross-unit: embedded + quarantined lines partition INVOICE_LINE exactly (P2); `tenants` 69 in target equals source;
tenant references outside TENANTS are the source property in OI-1 (not introduced by the migration).

## 5. Evidence-pack completeness (Cutover & Sign-off playbook step 2)
| Required item | Present | Audit note |
|---|---|---|
| Coverage table | yes | `inventory/model.md`: 20 tables, 5 packages, 7 triggers, 2 jobs, 5 sequences, each in one bucket |
| Approved mapping version | yes | map-1; sha256 re-computed and equal |
| Every wave report | yes | recon/wave-0, recon/wave-1, recon/wave-2 reports present; `waves/wave-{0,1,2}.result.json` closed, auto_merge=false |
| Parallel-run log or explicit decision to skip | yes | skip, D-020 (no writers besides legacy-billing, source static); this audit's three identical recounts support the premise. Customer confirms at STOP C |
| Watermark recon | yes | this report (D-021) |
| Open issues with dispositions | yes | OI-1..OI-8 each carry a disposition (table below) |
| Dependency register D1-D3 DONE or deferred with owner | yes, see F3 | pack section 7 states DEP-1 DONE, DEP-2 DEFERRED (owner: customer billing/ETL team), DEP-3 DONE |
| Business-logic track | yes | every legacy-billing path repoints; the one non-repointing consumer (CUSTBILL extract, DEP-2) is stated first in the runbook |

| Open issue | Pack disposition | Audit check |
|---|---|---|
| OI-1 tenant ids absent from TENANTS | source property, preserved | consistent with P3/P7 counts; not re-counted per tenant |
| OI-2 U2 scoped embed, merge_eligible=false | closed by full-population probe | re-confirmed: harness still false (F2); P1+P2 close it |
| OI-3 empty source collections | vacuous PASS | subscriptions_hist, billing_audit_log gated in U3 at 0 = 0 |
| OI-4 RECON_REDACT_SALT unset | accepted, aggregate-only artifacts | still unset (F4) |
| OI-5 empty `_connectivity_probe` in target | housekeeping | still present, empty (F5) |
| OI-6 tolerance doc typo | fixed | tolerance sha equals the pack |
| OI-7 compose hardcoded backend; U4 test lint | fixed on #1746 | true only from head `34d40006`, pushed after the ledger commit (F1) |
| OI-8 no PR merged | manual merge order, runbook section M | still true; not merged by this session (F6) |

## 6. Findings
- **F1 (info, closed): #1746 head moved during the audit.** Gated at `ddafb31a`; head advanced to `34d40006` at 2026-09-29T20:16:47Z (compose passes `BILLING_BACKEND`, `BILLING_MONGO_URI`, `BILLING_MONGO_DB`, `BILLING_READONLY` through, defaults unchanged; lint-only test edits). `.migration/`, `services/legacy-billing/app/` and `services/legacy-billing/migration/` are byte-identical between the two heads. U4 was re-gated live at `34d40006`: PASS, merge_eligible=true, post-wave 7/7; recount after it equals W. The evidence pack (ledger commit 20:13:23Z) recorded OI-7 as fixed before that commit existed, and lists three of the four passthrough variables. Merge #1746 at `34d40006` or a head re-gated after it.
- **F2 (info, closed by probe): U2 merge_eligible=false.** Harness PASS, but the scoped `invoices.lines` embed skips the extra-target-element check. P1+P2 show 0 extra, 0 missing, exact per-header lengths across the full population, and an exact partition with the quarantine. merge_eligible=false has to be accepted by the customer at merge; this audit does not override it.
- **F3 (low, documentation): dependency register wording.** `07_dependency_register.md` State column reads CONFIRMED/FOUND; DONE/DEFERRED and the DEP-2 owner are stated only in the evidence pack section 7. Substance complete; align the register at STOP C.
- **F4 (low, process): `RECON_REDACT_SALT` unset** for every harness run in this audit (OI-4). Artifacts redacted but unsalted; no artifact leaves this session's box.
- **F5 (info): `_connectivity_probe`** empty collection remains in ow_tp_mmp_live (OI-5). Not a mapped target; remove or keep as the customer decides.
- **F6 (cutover prerequisite): nothing merged.** All five PRs are unmerged against `tp-run/mongodb-20260929T160602Z`; gates here ran from PR heads. After the customer merges per runbook section M, run the post-merge verification (runbook V1-V4) before the point of no return.
- Residual Python lint in U4 tests (DTZ011, I001 in two test files under the repo ruff config) is outside any gate; noted, not a finding against cutover.

## 7. Countersignature
Countersigned for STOP C: the watermark recount equals the baseline and did not move across the audit; all five unit gates PASS live
at W from their PR heads (U4 at both heads); app-level parity 6/6 live and 7/7 post-wave; the evidence pack's sampled claims
re-check exactly; the pack is complete per Cutover & Sign-off step 2 with every open issue dispositioned. Findings F1-F6 are
non-blocking. Cutover itself, the merges, and the repoint remain customer-executed with the customer-held cutover principal.

Independent audit session: https://partner-workshops.devinenterprise.com/sessions/7815bcac3c02411aa367ddce831df6b1
