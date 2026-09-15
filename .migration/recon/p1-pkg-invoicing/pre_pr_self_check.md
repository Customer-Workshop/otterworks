# tp-pre-pr-self-check — p1-pkg-invoicing (U-23)

| item | result | evidence |
|---|---|---|
| NULL / missing attribution cannot fail open | PASS | A missing subscription leaves plan code, plan fee and tax NULL and the preview still returns five rows — the source's `WHEN NO_DATA_FOUND THEN NULL` (P1-D2), compared against Oracle in scenario `no_subscription`. A NULL credit still propagates through the burn-down's `GREATEST` so the NOT NULL write fails as Oracle's does, rather than silently writing 0. |
| References scoped to `ow_tp` / `ow-tp-` | PASS | Lakebase database `ow_tp`, schema `billing`, project `ow-tp-billing`, branch `mig-p1-w2`. No unqualified name; `ow_tp.silver.usage_events` is never read. |
| No DDL drops / replaces / alters a shared table | PASS | `w4b_pkg_invoicing.sql` is three `CREATE OR REPLACE` routines plus their comments. The seven tables it touches are DML only. |
| Retention / cleanup safe on rerun | PASS | The only deletion is the source's own `DELETE FROM invoice_lines WHERE invoice_id = …` before the lines are rebuilt — scoped to the invoice being issued, and what Oracle does. Nothing prunes by age. |
| Cleanup retains run evidence | PASS | Nothing under `.migration/recon/p1-pkg-invoicing/` is removed or rewritten by any script in this unit. |
| No secrets / tokens / real addresses | PASS | Secrets are referenced by name (`ow-tp/oracle/ow_billing_ro`, `OW_TP_LAKEBASE_DSN`) and resolved by the repo helpers; no DSN or credential is printed, stored or committed. `git log -p` on this branch and the evidence files contain no address. |
| Parity-vs-tolerance matches the contract | PASS | `.migration/03_recon_tolerances.json` unchanged (byte-equal to HEAD per the capability preflight). Money exact — no tolerance invented for the one-cent class. |
| Idempotency proven by an actual rerun | PASS | `idempotency/run1.json` and `idempotency/run2.json`: two executed runs, distinct run ids, identical counts and content hashes over all seven declared write targets. Scope and the two excluded non-deterministic columns are stated in `summary.md`. |
| Recon values recomputed from the target | PASS | `p1-pkg-invoicing.recon.json` carries `values_recomputed_from_target: true`; both the digest and the behaviour check read every value back out of Lakebase, none from migration output. |
| Unverified paths listed | PASS | Four, in `summary.md` and in the `unverified_paths` array of the recon report. |
| `"kind": "recon-report"` in a `*.recon.json` | PASS | `.migration/recon/p1-pkg-invoicing/p1-pkg-invoicing.recon.json`; `make tp-validate-recon` validated it. |
| Capability preflight passed | PASS | `.migration/09_capabilities.json` (parent-owned, read not edited): `blocking: []`, guard_mode=block, allowlist clean. Oracle EXECUTE is the one capability absent, and it is recorded as an unverified path rather than treated as green. |
| `make tp-smoke` green | PASS | Run at HEAD of this branch: `tp-smoke: all checks passed`. |

Nothing in the list is skipped. The DEGRADED grade is not a self-check failure: it is the
owner's D10-01 decision, and it is carried on every artifact.
