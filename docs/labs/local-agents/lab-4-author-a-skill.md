# Lab 4 — Author a Skill from What Just Happened (10 min)

**Goal:** close the loop. The three labs before this one produced knowledge that
currently lives in your terminal scrollback. Turn it into a file, and the next
session — yours or a teammate's — starts where this one ended.

This is the argument that makes local agents compound instead of plateau.

## Where to Find Things

- Existing repo skills: `.agents/skills/*/SKILL.md` — read
  `.agents/skills/angular-upgrade/SKILL.md` as the shape to copy.
- Same format works in Devin CLI and Devin Local; a skill committed here is a
  skill your teammates get on their next `git pull`.
- Cloud counterpart: `.workshop/playbooks/*.devin.md`.

```bash
devin skills list
devin skills show angular-upgrade
devin skills paths        # every directory searched for skills
```

## Task

Have the session write the skill for the work it just did in Lab 3 —
`document-service-debugging` — then prove it fires.

## Suggested prompts

```
Write .agents/skills/document-service-debugging/SKILL.md from what we just did: setup commands, the 9-failure baseline with names, the auth path we chased, what we ruled out, and how to verify. Only what you actually confirmed.
```

```
Read it back as if you had never seen this repo. What would you still have to discover yourself?
```

Then, in a **new** session:

```
The document-service tests are failing. Where do I start?
```

## Capability Spotlight

- **A skill is a description plus mechanics.** The frontmatter `description` is the
  only thing the model sees when deciding to load it, so it must name the situation
  ("when tests fail in services/document-service"), not the topic. The body holds
  commands, exact expected output, and gotchas.
- **Write what was verified, not what was assumed.** Test counts, file paths, error
  strings you saw. A skill that hallucinates costs more than no skill.
- **Ruled-out branches belong in the file.** "The 401 is not X" saves the next
  session the same twenty minutes.
- **Skills are code review.** They land in a PR, get reviewed, and version with the
  repo. That is the difference between a shared skill and a private prompt library.
- **`subagent: true` in frontmatter** makes a skill run as a foreground subagent —
  useful when the procedure is long and you want its transcript out of your context.
- **New session, cold start.** Open a fresh session and ask the naive question. If
  the skill loads and the answer is instantly specific, the loop is closed. This is
  the moment the demo lands — do not skip it.

## How to Verify

```bash
devin skills list                            # your new skill is discovered
devin skills show document-service-debugging
git status                                    # the skill is a committable file
```

## What "Done" Looks Like

- A `SKILL.md` under 100 lines whose every claim is one you watched happen.
- A fresh session that loads it unprompted and answers the naive question with
  real commands and the real baseline.
- It is in the diff, headed for review — not in someone's notes app.

## Tips

- Reviewing a skill is reviewing a runbook: ask "would a new hire succeed with only
  this?" Both the human and the agent need the same answer.
- Prune. A skill that documents everything gets loaded for everything and dilutes
  context. One situation per skill.
- Bad description: "Angular tips". Good description: "Upgrading
  frontend/admin-dashboard across Angular majors — baseline, commands, revert."
