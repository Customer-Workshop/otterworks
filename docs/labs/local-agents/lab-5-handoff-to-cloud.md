# Lab 5 — Local vs. Massively Parallel, and the Handoff (10 min)

**Goal:** answer the question every customer has by now — *when do I stop doing
this locally?* Then show the handoff, live.

## The rule

| Do it **local** when… | Do it **cloud** when… |
|---|---|
| You don't yet know what the change is | The change is fully specified |
| Steps depend on the previous step's outcome | Tasks are independent of each other |
| It needs your uncommitted work or local creds | It starts from a clean branch |
| You need to look at it (UI, chart, layout) | Success is a command exiting 0 |
| It unblocks everything else | It's the same mechanical edit, N times |
| One machine is enough | You want 10 PRs while you're in a meeting |

Lab 2 was the left column: nobody knew which schematic would break which spec, so a
human sat there. What Lab 2 *produced* is the right column.

## The fan-out

Once the dashboard is on Angular 20, the modernization inventory in
`.agents/skills/angular-upgrade/SKILL.md` is a list of independent, well-specified,
mechanical tasks — one PR each:

- Constructor DI → `inject()`, one feature page per session
- `@Input()`/`@Output()` → signal inputs/outputs
- `ng2-charts` → current charting approach
- Karma/Jasmine → modern test runner
- Angular ESLint setup

Each touches a different area, each has the same definition of done (build clean,
baseline unchanged), none blocks another. That is the shape that deserves parallel
cloud sessions.

## Task

Hand the fan-out off without leaving the terminal, and show the cloud side picking
it up.

## Suggested prompts

```
/handoff The app is on Angular 20. Fan out the independent modernizations as parallel cloud sessions, one PR each: one per feature page (inject() + control flow), plus signals, ng2-charts, test runner, and eslint.
```

```
Draft the per-session brief you'd send: scope, definition of done, and what must not change.
```

## Capability Spotlight

- **`/handoff` carries context.** It packages the conversation and current branch
  into a cloud session, so the cloud agent inherits everything you learned locally
  rather than restarting cold. `/handoff` with no description just continues.
- **Same assets, both sides.** `AGENTS.md` and `.agents/skills/` are in the repo, so
  a cloud session reads the skill you wrote in Lab 4. That's why authoring it was
  worth ten minutes.
- **Playbooks are the cloud counterpart.** Show `.workshop/playbooks/` — a repeatable
  procedure for the cloud what a skill is for local. Same instinct, different runner.
- **The brief is the work.** Parallel sessions fail on ambiguity, not capability.
  A good brief names the scope, the verification command, and the invariant
  ("the 7 failing specs stay 7 and keep their names").
- **You stay the reviewer.** Ten PRs arrive; you review them locally, where you can
  run the app. Local and cloud are a loop, not a choice.

## How to Verify

- The cloud session appears in the web app and in the CLI's session list.
- Its opening message reflects the local context — the Angular version, the
  baseline — instead of asking what the repo is.
- Each planned session maps to exactly one PR-sized scope.

## What "Done" Looks Like

- A handed-off session, visible on both surfaces.
- A written brief with scope, done-condition, and invariant.
- The audience able to state the rule back to you in one sentence.

## Tips

- If a task in the fan-out list can't be described in three sentences, it isn't
  ready to go parallel — that's still local work.
- Don't fan out two sessions that edit the same file. Merge conflict cost swamps
  the parallelism gain.
- Close the workshop on the compounding point: Lab 2's grind became Lab 4's skill,
  which is what makes Lab 5's ten cloud sessions safe to launch.
