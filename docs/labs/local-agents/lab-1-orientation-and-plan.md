# Lab 1 — Orientation and Plan (10 min)

**Goal:** show that a local agent's first job is not to write code. It is to load
the right context and produce a plan you can argue with.

## Where to Find Things

| What | Where | Why it matters |
|---|---|---|
| Always-on rules | `AGENTS.md` (repo root) | Loaded into every session with no prompting. Golden-app policy, tenant model, deploy rules |
| Scoped rules | `AGENTS.md` in any subdirectory | Applies only when the agent touches that directory |
| Skills | `.agents/skills/<name>/SKILL.md` | Model-invoked; the agent pulls one in when its `description` matches the task |
| Subagent profiles | `.agents/agents/*.md` | Named specialists you can dispatch (Lab 3) |
| Route → service map | `docs/api-route-matrix.md` | The fastest orientation artifact in an 11-service estate |

## Task

Start a session at the repo root and get an accurate map of the admin dashboard's
upgrade situation — with zero files changed.

```bash
cd otterworks
devin
```

## Suggested prompts

```
What rules and skills are loaded for this repo, and what do they tell you about how I work here?
```

```
/plan
Explore frontend/admin-dashboard. Map the upgrade path to Angular 20: what is sequential, what can be parallelized. Don't change anything yet.
```

Then, after the plan lands:

```
Which of those steps do you think will break the test baseline, and why?
```

## Capability Spotlight

- **Rules load themselves.** Ask the agent about the golden-app policy before ever
  mentioning it. It already knows — that's the root `AGENTS.md`. Contrast with
  pasting conventions into a chat window every morning.
- **Skills are matched, not listed.** `devin skills list` shows eight; the agent
  pulled in `angular-upgrade` because the *task* matched its description. Show
  `devin skills show angular-upgrade` and point at the verified baseline inside it.
- **Plan mode is a real constraint.** In `/plan` the agent can read, grep, and run
  read-only MCP tools, but cannot write. The output is a plan you edit before a
  single line changes. Say `megaplan` to force a clarifying question first.
- **`@` mentions** pull a specific file into context: `@frontend/admin-dashboard/package.json`.

## How to Verify

```bash
git status         # must be clean — plan mode wrote nothing
devin skills list  # angular-upgrade is discovered
```

The plan should name Angular 17.3 as the starting point, one-major-at-a-time as the
sequence, and the 7 failing specs as the baseline. If it invents a version or a
test count, the skill isn't being picked up — check `devin skills list` first.

## What "Done" Looks Like

- A written plan with a per-major stop point, not a single "upgrade to 20" step.
- The agent citing the 7-failure baseline **as a constraint** rather than as work.
- `git status` clean.

## Tips

- Ask "what would you need from me to be sure?" — it surfaces where the repo's
  documented context is thin, which is exactly what Lab 4 fixes.
- If the audience is skeptical, delete `.agents/skills/angular-upgrade/SKILL.md`
  locally and re-run the same prompt. The difference in the plan's specificity is
  the entire argument for skills.
