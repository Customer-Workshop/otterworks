# Local Agents on OtterWorks — Demo Flow

A ~75-minute end-to-end flow for showing how to actually *work* with a local coding
agent (**Devin CLI** in the terminal, **Devin Local** inside Devin Desktop) on a
real polyglot monorepo. It is built to be run live in front of a customer, then
handed to them as the labs they run themselves.

The three things this flow is designed to land:

1. **Skills** — the repo teaches the agent its own mechanics, so every engineer's
   session starts where the last one left off.
2. **Subagents** — one operator, several agents, without losing the thread.
3. **The working loop** — how a strong operator drives a local agent: context
   first, plan before edits, verify every step, keep the diff reviewable, and know
   the moment to hand off to the cloud.

Everything below is grounded in this repo as it stands on `main` — the paths,
commands, test counts, and failures are real and were measured, not illustrative.

---

## Before the room

```bash
# 1. Local agents
curl -fsSL https://cli.devin.ai/install.sh | bash   # macOS/Linux/WSL
# macOS alternative: brew install --cask devin-cli
# Devin Desktop bundles the CLI: Command Palette → "Install Devin CLI"
devin --version
# Devin Desktop: Settings → enable "Devin Local" and the "Subagents (Preview)" toggle

# 2. Repo
git clone https://github.com/Cognition-Partner-Workshops/otterworks
cd otterworks
git checkout -b workshop-<your-id>       # never demo on main

# 3. What the agent already knows about this repo
devin skills list                        # 8 repo skills under .agents/skills/
devin rules list                         # root AGENTS.md loads as an always-on rule
```

Two lab targets, both runnable without Docker or AWS:

```bash
cd frontend/admin-dashboard && npm ci                      # ~1 min
cd services/document-service && poetry install --no-root   # ~1 min
```

Nothing else in the estate needs to be up. `make up` brings the whole platform
(11 services, 2 frontends, Postgres/Redis/LocalStack/MeiliSearch) if you want the
running app on screen, but no lab requires it.

### Verified starting state

| Target | Command | Baseline |
|---|---|---|
| `frontend/admin-dashboard` | `CHROME_BIN=$(which google-chrome) npm test` | 64 specs — **57 pass, 7 fail** |
| `services/document-service` | `poetry run pytest -q` | 60 tests — **51 pass, 9 fail** |

Both sets of failures are pre-existing on the golden app (see the planted-bug
policy in the root `AGENTS.md`). They are the demo's raw material: the dashboard's
7 are the *baseline you must not disturb* during an upgrade; the document service's
9 are the *bug you go hunt*.

---

## The flow

| Act | Lab | Minutes | The point |
|---|---|---|---|
| 0 | — | 5 | What a local agent is, and what it is not |
| 1 | [Lab 1](lab-1-orientation-and-plan.md) | 10 | Context beats prompting: `AGENTS.md`, rules, plan mode |
| 2 | [Lab 2](lab-2-skill-driven-modernization.md) | 20 | A skill turns tribal knowledge into a repeatable run |
| 3 | [Lab 3](lab-3-subagents-bug-hunt.md) | 20 | Subagents: parallel work, protected context |
| 4 | [Lab 4](lab-4-author-a-skill.md) | 10 | The compounding loop — the session writes the next skill |
| 5 | [Lab 5](lab-5-handoff-to-cloud.md) | 10 | Local vs. massively parallel, and the handoff |

Run them in order the first time; each act sets up the next. Labs 2–4 stand alone
if you only have 30 minutes.

### Act 0 — frame it (5 min, no typing)

Say this before opening a terminal:

> A local agent runs on *your* machine, in *your* checkout, with *your* toolchain
> and credentials. That buys three things a cloud session can't: it sees your
> uncommitted work, it runs the thing you're staring at, and the feedback loop is
> a second long. It costs you one machine's worth of parallelism. So the operating
> rule is: **judgment, exploration, and anything needing your eyes → local.
> Well-specified, independent, repetitive → cloud.**

Then show the surface area, because this is what the rest of the flow uses:

- `AGENTS.md` at the repo root → always-on rules, no prompting required.
- `.agents/skills/` → 8 skills the agent invokes on its own when relevant.
- `.agents/agents/` → custom subagent profiles (`repo-scout`, `verifier`).
- `.workshop/playbooks/` → the cloud-side counterpart, for Act 5.

Identical in Devin CLI and Devin Local — same harness, same files. The difference
is the surface: terminal vs. IDE with diffs, browser preview, and inline review.

---

## The working loop (the actual content of the demo)

Every lab drills the same five habits. Name them out loud when they happen;
that is what the audience takes home.

1. **Load context before asking for work.** The first prompt of a session is
   almost never "make the change". It's "tell me what you found". `AGENTS.md` and
   skills mean the agent starts oriented instead of guessing.
2. **Plan mode before edits on anything non-trivial.** `/plan` reads and
   researches but cannot write. You review a plan, not a diff of 400 lines you
   didn't ask for. Saying `megaplan` in the prompt makes it plan harder and ask at
   least one clarifying question before writing the plan.
3. **Verify at every step, with the repo's own command.** "Tests pass" is a claim;
   `57 passed, 7 failed` is evidence. The baseline is a number you hold the agent
   to, and — per this repo's TDD rule — the tests are the source of truth. A test
   is never edited to make a change look green.
4. **Keep the diff reviewable.** One concern per commit. A schematic run, a
   refactor, and a fix are three commits, not one. This is what makes an agent's
   output *mergeable* rather than merely correct.
5. **Write down what you learned.** The moment you explain a gotcha twice, it goes
   in a skill (Act 4). This is the difference between a demo and a practice.

### Prompting notes

Terse and specific beats long and hedged. All prompts in these labs are one or two
lines. Three patterns to point out:

- **Bounded exploration** — "Explore X. Map Y. Don't change anything yet."
- **Explicit stop points** — "Pause after the first major so I can review."
- **Named verification** — "Run the test command from the skill and report the
  count before and after."

### Model switching

`/model` mid-session, no restart, context intact. The demo-worthy sequence: a fast
model for the mechanical schematic run, a stronger one the moment a spec fails and
someone has to reason about *why*. Same session, same context, different cost per
token. In Desktop it's the model picker on the session.

### Permissions

`Shift+Tab` cycles Normal → Accept Edits → Smart → Bypass. Smart mode
auto-approves workspace edits and routine build/test commands while still
prompting for installs, `git` mutations, and anything destructive. Show the prompt
at least once — an agent asking before it runs something is a feature, and the
"always allow this command in this project" option is how a real user tunes it.
(Smart mode is rolling out gradually; the cycle skips it if it isn't enabled for
your account.)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `npm test` exits before running specs | `CHROME_BIN=$(which google-chrome \|\| which chromium) npm test` |
| Karma dies in a container | `karma.conf.js` already defines `ChromeHeadlessNoSandbox`, but `npm test` hardcodes `--browsers=ChromeHeadless` over it — run `npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox` instead |
| `poetry: command not found` | `pipx install poetry`, then `poetry install --no-root` |
| Agent doesn't pick up a skill | `devin skills list` — check it's discovered; skills are matched on their `description`, so make it say *when* to use it |
| Subagent tools missing | Subagents on by default; `subagents_enabled: false` in `~/.config/devin/config.json` (or the Desktop toggle) turns them off. Org policy can override |
| A dashboard spec count that isn't 7 | Re-run `npm ci` — a partial install shifts the baseline |

## Reset

```bash
git checkout -- . && git clean -fd     # discard the lab's work
git checkout main
```

Never fix a planted bug on `main`, and never demo from `main` — see the golden-app
policy in the root `AGENTS.md`.
