---
name: angular-upgrade
description: >
  Repo-specific mechanics for upgrading the OtterWorks admin dashboard
  (frontend/admin-dashboard) across Angular majors. Covers the verified test
  baseline, the headless-Chrome gotcha, the one-major-at-a-time sequence, the
  peer packages that must move with each major, and how to revert.
---

# Angular Upgrade — OtterWorks Admin Dashboard

Everything in this skill was measured against `main` on Node 22.23.2 / npm 10.9.8.
Re-measure before trusting a number that disagrees with what you see.

## The app under upgrade

- Path: `frontend/admin-dashboard`, Angular **17.3** (`@angular/core`, `cli`,
  `material`, `cdk` all `^17.3.0`), TypeScript `~5.4.2`, zone.js `~0.14.4`.
- Already **standalone components** + the `@angular-devkit/build-angular:application`
  builder (`angular.json`). There is no NgModule migration to do — the work is the
  major-version chain plus per-file API modernization.
- 11 route folders under `src/app/pages/`, plus `layout/sidebar`, `layout/toolbar`,
  `shared/components`, `core/services`, `core/interceptors`, `core/guards`.
- Charts: `ng2-charts` `^5.0.3` on `chart.js` `^4.4.2`. `ng2-charts` majors track
  Angular majors — it moves with the chain, not separately.
- Tests: Karma + Jasmine. Angular 20 deprecates Karma but still ships the builder;
  swapping test runners is a separate change, not part of the spine.

## Commands

```bash
cd frontend/admin-dashboard
npm ci                       # ~1 min
npm start                    # dev server on http://localhost:4200
npm run build                # production build
npm test                     # ng test --watch=false --browsers=ChromeHeadless
```

Login on `localhost:4200` is **mocked client-side**
(`src/app/core/services/auth.service.ts`) — any email plus any non-empty password
signs in. There is no admin backend call to stand up.

## Gotcha: headless Chrome

On a machine with no Chrome on the default path, `npm test` exits before running a
single spec. Set `CHROME_BIN` for the command:

```bash
CHROME_BIN=$(which google-chrome || which chromium) npm test
```

If the sandbox is unavailable (containers, CI), add a `ChromeHeadlessNoSandbox`
custom launcher in `karma.conf.js` rather than disabling the browser tests.

## Verified test baseline (Angular 17.3, `main`)

`TOTAL: 7 FAILED, 57 SUCCESS` out of 64 specs:

```
AuthService should return token from getToken()
DashboardComponent should load dashboard stats
DashboardComponent should display stat cards when loaded
HealthComponent should load system health data
UsersComponent should load users
UsersComponent should display page title
UsersComponent should apply text filter
```

These are pre-existing on the golden app — see the planted-bug policy in the root
`AGENTS.md`. **They are the baseline, not the task.** An upgrade step is clean when
the count is still exactly 7 and the failing spec names are unchanged. A spec that
starts failing during the chain is a regression the upgrade introduced; a spec that
starts passing means something changed behavior and needs explaining. Never edit a
spec to move the number.

## Upgrade sequence

One major at a time, never `ng update` straight to 20. After **each** major:
`npm run build`, then the test command above, then diff-review the schematic's edits.

```bash
npx ng update @angular/core@18 @angular/cli@18
npx ng update @angular/material@18          # pulls @angular/cdk with it
# build + test + review, commit, then repeat for 19, then 20
```

Per-major notes:

- **17 → 18**: control-flow migration (`*ngIf`/`*ngFor` → `@if`/`@for`) is offered
  as a schematic; run it as its own commit so the diff stays reviewable.
- **18 → 19**: standalone becomes the default; the schematic strips now-redundant
  `standalone: true`. Expect a large, mechanical diff.
- **19 → 20**: needs Node 20.19+ / 22.12+ and a TypeScript bump. `ng2-charts` must
  reach its Angular-20-compatible major in the same step or the build fails on peer
  resolution.

Node/TypeScript floors move every major — read the `ng update` output rather than
assuming; it refuses and tells you when the toolchain is too old.

## Modernization inventory (do these after the spine lands on 20)

Each is independent of the others, which is what makes them fan-out candidates:

- **Constructor DI → `inject()`** — 17 non-spec files: 11 under `pages/`, plus
  `app.component.ts`, `layout/toolbar`, `shared/components/confirm-dialog`,
  `core/services/{auth,admin-api}.service.ts`, `core/interceptors/jwt.interceptor.ts`.
  One page per session is the natural fan-out unit.
- **`@Input`/`@Output` → signal inputs/outputs** — 2 declarations, both in
  `layout/sidebar/sidebar.component.ts`.
- **Charts** — `ng2-charts`/`chart.js` bump and the config changes it brings.
- **Test runner** — Karma/Jasmine → a modern runner (deprecated as of 20).
- **Lint** — `@angular-eslint` is not wired up yet; `npm run lint` calls `ng lint`.

## Revert

Every step is `package.json` + `package-lock.json` + schematic edits, so
`git checkout -- . && npm ci` returns you to the last commit. Commit after each
major so a bad schematic costs one major, not the whole chain.
