# 01 Conventions

## Branches and PRs

- Working branch: `tp-run/mongodb-20260915T045208Z` (cut from `tech-partnerships`).
  Never PR migration work into `tech-partnerships` or `main`.
- Child branch: `migrate/billing/<wave>-<unit>` off the working branch.
- **One PR per unit.** Never a stack. A unit is done only when its PR is merged into the
  working branch.
- Every PR must pass `make tp-smoke` locally and the `tp-golden-smoke` CI gate.
- Children never merge their own PR and never edit `.migration/`.

## PR body shape

Under 2,000 characters, in this order:

1. **Unverified paths** — anything not proven, first.
2. **Decisions** — what was decided and which `05_decisions.md` row authorises it.
3. **Code** — what changed.
4. **Evidence** — `recon.summary.md` rendered inline, raw `recon.json` linked.
5. **PROFILE FEEDBACK** (optional) — reusable Oracle facts for the source profile.

No user-identifying information in PR bodies.

## Namespaces

- Atlas: database `ow_billing_migration` only. Nothing else, ever.
- Collections are named exactly as the PRD names them.
- Repo artifacts: `.migration/` (parent-written only), unit code under the paths the unit
  brief names.

## Evidence

- Machine-readable first: `*.recon.json` with `"kind": "recon-report"`.
- Recon values are recomputed from Atlas, never copied from a prior report.
- Idempotency is proven by an actual rerun.
