---
name: visual-ui-defect-remediation
description: >
  Repo-specific mechanics for closing user-facing (browser-visible) defects in the
  OtterWorks client app. Covers the defect registry in qa/registry.yaml, the
  ui-* Makefile targets that drive the repro → fix → verify → gate loop, how to
  bring the app up locally and sign in, where the client's API calls are made,
  how the route sweep suppresses still-open findings, and where evidence lands.
---

# Visual UI Defect Remediation — OtterWorks

Repo-specific mechanics behind the `!visual-ui-defect-remediation` Playbook.
Auto-loaded when Devin works in this repository.

## The registry is the source of truth

`qa/registry.yaml` registers every defect an exploratory browser pass has found
in `frontend/client-app`, the routes it appears on, the expected behavior it is
graded against, and the Playwright spec that reproduces it. The findings on
`main` came from a real browser pass recorded in `docs/exploratory-qa-report.md`
— they are the durable before-state of this exercise.

| Finding | Sev | Surface | Symptom in the browser |
|---|---|---|---|
| `OW-UI-101` | high | every authenticated route | notification calls return `400`; the bell badge and `/notifications` render as if empty |
| `OW-UI-102` | high | `/settings` | the settings form posts to a route that answers `404`; input is silently discarded |
| `OW-UI-103` | medium | `/files` | a text file's detail page never shows its contents |
| `OW-UI-104` | medium | `/files` | Download reports no progress, success, or failure |
| `OW-UI-105` | medium | `/trash` | permanent delete destroys an item with no confirmation |

`status` is a closed set — `open` or `remediated`. Any other value is a hard
error, so a typo cannot skip a gate. `open` findings may carry
`accepted_console_errors`; `remediated` findings may not, and the harness refuses
to run if one does. That pairing is what makes the gate tighten as the backlog
burns down instead of decaying into a permanent allowlist.

None of these are the planted bug described in `AGENTS.md` (the admin-service
Rails logger). They are genuine gaps in the client app and its contracts, and
closing one on a branch is the point of the exercise — just never on `main`.

## Commands

```bash
make ui-list                          # findings, status, and whether each has a spec
make ui-repro FINDING=OW-UI-101       # the finding's spec must FAIL (defect is real)
make ui-verify FINDING=OW-UI-101      # the spec must PASS and the suppression must be gone
make ui-gate                          # route sweep + every remediated finding's spec
```

All four wrap `qa/harness/ui_gate.py` (`uv run --with pyyaml`). Exit codes: `0`
pass, `1` a real failure (the spec did not fail when it had to, or did not pass
when it had to, or the sweep saw an unregistered error), `2` inconclusive — no
spec for the finding, or an unknown finding id. `2` is never a pass.

`BASE_URL` overrides the target (default `http://localhost:3000`, from
`qa/registry.yaml`). Point it at your own tenant to grade a deployed build.

## Bringing the app up

```bash
make up                  # all services + infra via docker compose
make dev-web             # backend in compose, client app with HMR on :3000
```

The client app is Vite on `:3000` and proxies `/api/v1/*` to the API gateway at
`http://localhost:8080` (`API_GATEWAY_URL` overrides), so browser requests are
same-origin and the gateway's auth applies exactly as in a deployed tenant. Sign
in by registering a throwaway user through `/register` — `e2e/fixtures/
test-helpers.ts` has `registerUser`, `loginUser`, `expectDashboard`, and
`clearAuth`; use them rather than hand-rolling the flow. Every reproduction
registers its own user, so runs never collide over state.

Playwright starts the dev server itself when one is not already running
(`playwright.config.ts`, `reuseExistingServer: true`), so `make ui-repro` works
from a clean shell as long as the backend is up. With no backend, every route
fails to load and the sweep is meaningless — bring up `make up` (or at least
`make dev-backend`) first.

## Where the client makes its calls

`frontend/client-app/src/lib/api.ts` is the single axios client and the only
place request headers and auth are attached; every feature module calls through
it (`notificationsApi`, `settingsApi`, `filesApi`, …). The callers behind the
registered findings:

- `src/components/ui/notification-bell.tsx` and `src/pages/notifications.tsx` —
  `GET /notifications/unread-count`, `GET /notifications`.
- `src/pages/settings.tsx` — `GET`/`PATCH /settings`.
- `src/pages/file-detail.tsx` — preview and download.
- `src/pages/trash.tsx` — restore and permanent delete.

Backends behind them, for tracing a contract across the boundary: the gateway's
prefix table is `services/api-gateway/internal/config/config.go`
(`ServiceRoutes`), and it forwards the authenticated identity as a header in
`services/api-gateway/internal/proxy/router.go`. `/api/v1/notifications` is
served by `services/notification-service` (Ktor, `routes/Routes.kt`) and
`/api/v1/settings` by `services/auth-service`
(`controller/SettingsController.java`). Read what the handler requires before
deciding which side of a failing call is wrong.

## How the route sweep works

`e2e/ui-console-gate.spec.ts` registers one user, walks every route in
`app.authenticated_routes`, and fails on any console error or `>=400` response
that is not suppressed. `e2e/fixtures/ui-observer.ts` holds the listeners,
matching, and screenshotting.

Suppressions are not written in the spec. `make ui-gate` derives them from the
registry into `qa/reports/accepted-console.json` (`url_pattern`, `status`,
`message`) and passes the path via `UI_ACCEPTED_CONSOLE`. Run the spec on its own
and nothing is suppressed — it fails closed. Adding a route to
`authenticated_routes` is how a surface gets gated at all; a route nobody visits
is a route nobody checks.

## Evidence

`qa/reports/` is git-ignored generated output — never commit it. Each command
writes a JSON and a Markdown report on both success and failure paths
(`repro-<finding>.md`, `verify-<finding>.md`, `ui-gate.md`), and the sweep writes
a full-page screenshot per route to `qa/reports/screenshots/<route>.png`. Collect
the directory as a CI artifact; paste the summary lines and attach the
before/after screenshots in the PR body.

For a before/after pair, run the sweep once against the unfixed app and copy the
route's screenshot aside (it is overwritten by the next run), then run it again
after the fix.

## Adding a finding

Append to `findings:` in `qa/registry.yaml` with `id` (`OW-UI-1xx`), `title`,
`severity`, `status: open`, `source`, `routes`, `symptom`, `expected`, and
`spec: e2e/ui-defects/<id-lowercased>.spec.ts`. Add
`accepted_console_errors` only for errors the defect itself produces, matched as
narrowly as the failure allows (`url_pattern` plus `status`) — a broad pattern
hides future regressions on the same route. The spec path may not exist yet;
`make ui-list` reports it as `MISSING` and `make ui-repro` tells you to write it.

## Revert

Everything this loop produces is a branch plus (ignored) files under
`qa/reports/`. `git checkout main && rm -rf qa/reports` restores the
before-state; nothing is deployed and no infrastructure is touched.
