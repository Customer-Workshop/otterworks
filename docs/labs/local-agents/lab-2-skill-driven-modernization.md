# Lab 2 — Skill-Driven Modernization (20 min)

**Goal:** run a real legacy upgrade — Angular 17 → 18 — the way a good operator
runs one: the skill supplies the mechanics, you supply the judgment, and every step
is verified before the next one starts.

This is the lab that shows why local wins for this class of work. You are watching
schematics rewrite your files, running the app at `localhost:4200`, and deciding
after each step. That loop is seconds long locally.

## Where to Find Things

- App: `frontend/admin-dashboard` — Angular 17.3, standalone components, the
  `application` builder.
- Skill: `.agents/skills/angular-upgrade/SKILL.md` — verified baseline, commands,
  per-major notes, revert path.
- Login is mocked in `src/app/core/services/auth.service.ts`: any email plus any
  non-empty password. No backend needed.

## Task

Take the dashboard from Angular 17 to Angular 18 with the baseline intact, then
stop and review. (18 → 19 → 20 is the same move repeated; run it if you have time.)

## Setup

```bash
cd frontend/admin-dashboard
npm ci
CHROME_BIN=$(which google-chrome || which chromium) npm test
# TOTAL: 7 FAILED, 57 SUCCESS  ← write this number on the whiteboard
npm start   # http://localhost:4200 — sign in, show the dashboard before the upgrade
```

## Suggested prompts

```
Record the current test baseline for admin-dashboard, then upgrade it 17→18 following the angular-upgrade skill. Stop after the schematics run and before the control-flow migration.
```

```
Run the control-flow migration as its own commit. Report the spec count before and after.
```

```
The baseline moved. Which spec changed and what in the schematic diff caused it?
```

## Capability Spotlight

- **The skill carries the gotchas.** Nobody had to remember `CHROME_BIN`, or that
  `@angular/material` is a second `ng update`, or that `ng2-charts` majors track
  Angular majors. That knowledge was paid for once.
- **The baseline is the contract.** 7 failing specs before, 7 failing specs after,
  same names. This repo does TDD: a spec is never edited to make an upgrade look
  clean. When the number moves, that is the finding — chase it.
- **Model switching mid-task.** Run the schematics on a fast model; the moment a
  spec flips, `/model` to a stronger one to reason about the diff. Same session,
  same context.
- **Commit discipline.** Schematic run, control-flow migration, and any manual fix
  are three commits. A reviewer can follow that; a 900-line "upgrade" commit gets
  rubber-stamped, which is how upgrades break in production.
- **Live UI check.** Reload `localhost:4200` after the upgrade with the dev server
  still running. Same screens, newer framework — the visual proof of the change.
  In Devin Desktop the agent can open a browser preview beside the diff.

## How to Verify

```bash
git log --oneline           # one commit per concern
npm run build               # production build clean
CHROME_BIN=$(which google-chrome) npm test   # still 7 FAILED, 57 SUCCESS
grep '"@angular/core"' package.json          # ^18
npm start                                     # dashboard renders and navigates
```

## What "Done" Looks Like

- `@angular/core`, `cli`, `material`, `cdk` all on 18; lockfile updated.
- Production build passes.
- Exactly the 7 original failures, by name.
- Commits a reviewer can read one at a time.

## Tips

- If the schematic diff is huge (18 → 19 strips `standalone: true` everywhere),
  ask "summarize this diff by category before I review it" instead of scrolling.
- Never batch two majors. The whole value of the sequence is that a break is
  attributable to one step.
- Reverting is cheap: `git checkout -- . && npm ci` returns to the last commit.

## Hand off to the cloud

The spine is judgment work — stay local. The moment the app is on 20, the
inventory in the skill (17 files still on constructor DI, signal inputs, charts,
test runner, lint) becomes a set of independent, well-specified tasks. That is
Lab 5.
