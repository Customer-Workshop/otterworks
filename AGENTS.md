# AGENTS.md — OtterWorks

Guidance for AI agents (and humans) working in this repo.

## Golden app policy

- **`main` is the golden app: the canonical, fully-working initial state for every demo.**
  Unless a demo explicitly needs a variant, all demos start from the golden app as-is.
- The golden app is intentionally **fully functional except for deliberately planted bugs**
  used by bug-hunt / remediation labs. Planted bugs are a feature of the golden app, not
  defects to fix.
  - Do **not** "fix" a planted bug to make the app pass — that erases the lab. If you're
    unsure whether something is planted or a genuine infra gap, ask before changing it.
  - Known planted bug: `services/admin-service/config/environments/production.rb`
    (`ActiveSupport::TaggedLogging.logger($stdout)` is invalid on Rails 7.1 → admin-service
    crash-loops on boot). Leave it in place on the golden app.
- Genuine infrastructure/wiring gaps (missing tables, unwired config/secrets, unreachable
  backing services) **should** be fixed so the golden app is otherwise green.

## Variants & multi-tenant demos

- A **variant** = the golden app plus demo-specific changes (extra planted bugs, feature
  flags, scaled resources). Variants are derived from `main`, never the other way around.
- For concurrent demos on shared infra, isolate per attendee/demo rather than mutating the
  golden baseline. See `docs/MULTI-TENANT-DEMO-PLAN.md` for the namespace-per-tenant model,
  cost controls, and how to inject bugs / do immediate redeploys without stepping on others.

## Deploy

- `scripts/deploy-dev.sh` wires all services' config/secrets from Terraform outputs and
  deploys via Helm. `scripts/spinup-dev.sh` / `scripts/teardown-dev.sh` manage cluster
  lifecycle for cost control. See `docs/SDLC-COVERAGE.md` §3 for the full CD picture.
