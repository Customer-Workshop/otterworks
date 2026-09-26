---
name: dotnet-wpf-to-angular
description: Port the legacy .NET WPF desktop client (clients/windows-desktop) to the Angular app at frontend/desktop-client with a dynamic workflow of child agents — one scaffold agent, an analyze→port chain per WPF view, and one integration agent that builds, tests, browser-verifies and opens a single PR. Use when a WPF view in clients/windows-desktop has no Angular counterpart, or when asked to migrate/continue migrating the desktop client to Angular.
---

# WPF → Angular desktop client migration

## When to use this

Use it when `clients/windows-desktop/OtterWorks.Desktop/Views/*.xaml` contains a
screen that has no counterpart under `frontend/desktop-client/src/app/pages/`,
or when asked to (re-)run the desktop-client migration. It is a *dynamic
workflow*, not a manual porting procedure: the point is that each screen is
ported by its own child agent, concurrently, on its own branch.

Do not use it for the React `frontend/client-app` or the Angular
`frontend/admin-dashboard` — those are unrelated apps.

## How to run it

Invoke the builtin `dynamic-workflows` skill first, then:

```
run_workflow(
  workflow_name="dotnet-wpf-to-angular-<run-id>",
  script_path="/absolute/path/to/repo/.devin/skills/dotnet-wpf-to-angular/workflow.py",
)
```

Environment knobs (both optional):

- `WPF_MIGRATION_REPO_ROOT` — the checkout the script enumerates views from
  (default `/home/ubuntu/repos/otterworks`).
- `WPF_MIGRATION_RUN_ID` — the token embedded in every branch name; change it
  for a fresh run so branches never collide with an earlier one.

Resume an interrupted run by passing its `run_id` back to `run_workflow`;
completed agents replay instead of re-running.

## What the workflow does

1. **Enumerate** `Views/*.xaml` deterministically inside the script.
   `MainWindow.xaml` is treated as the app shell (owned by the scaffold agent);
   every other view becomes a routed screen with a derived slug, route,
   component folder, selector, class name and branch name.
2. **scaffold** (1 agent) — creates the Angular 17 + Material workspace at
   `frontend/desktop-client` mirroring `frontend/admin-dashboard`, the shell,
   the router with a *lazy route and placeholder component for every screen*,
   the shared `OtterWorksApiService` (port of `OtterWorksApiClient`), the
   session/token service (browser equivalent of `SessionState`), the auth
   interceptor, `proxy.conf.mjs` and the Karma setup; pushes the base branch.
   This stage is what makes the per-screen outputs additive and collision-free.
3. **analyze → port** (2 agents per screen, chains run concurrently) — the
   analyze agent reports the screen's behaviours, API calls, validation rules
   and states from the XAML + view model; the port agent branches off the base
   branch, implements **only inside its own component folder**, adds
   Karma/Jasmine specs for those behaviours, and pushes its own branch.
4. **integrate** (1 agent) — merges every screen branch onto the base branch,
   gets `ng build` and `ng test` green, brings up the stack (`make up`), drives
   the real app in Chrome through register → empty documents → create document →
   files → logout → login → document persists, screenshots each state, pushes
   the integration branch and opens **one** PR with a screen-by-screen
   WPF-vs-Angular comparison.

A failed analyze or port stage is recorded and skipped (`WorkflowAgentError`),
the screen stays as its scaffolded placeholder, and the integration agent lists
it in the PR as not ported.

## Conventions the workflow enforces

- Branches only: `devin/<run-id>-desktop-client-{base,<slug>,angular}`; never
  push to `main`, never fix planted bugs outside scope, never name a requester.
- Agents share nothing but git — every prompt is self-contained and every agent
  reports its branch in structured output.
- Angular app parity targets: Angular/Material `^17.3.0`, standalone components,
  `ng test` on ChromeHeadless, `/api` proxied to the gateway on `:8080`.
