# Lab 3 — Subagents and the Bug Hunt (20 min)

**Goal:** show what subagents are actually for. Not "more agents = faster" — a
subagent is a *context boundary*. It burns a hundred tool calls in its own window
and hands your main session back three lines.

The hunt is real: `services/document-service` fails 9 tests on a clean checkout.

## Where to Find Things

- Service: `services/document-service` (Python/FastAPI, Poetry).
- Auth helpers under suspicion: `app/api/documents.py` —
  `_extract_user_id`, `_require_user_id`, `_ensure_owner`.
- Custom profiles: `.agents/agents/repo-scout.md` (read-only researcher),
  `.agents/agents/verifier.md` (runs one service's verification command, reports
  counts).
- Built-in profiles ship with the agent; the two above are repo-local additions
  discovered from `.agents/agents/`. Ask the agent "which subagent profiles do you
  have?" to see both sets.

## Setup

```bash
cd services/document-service
poetry install --no-root
poetry run pytest -q
# 9 failed, 51 passed
```

The failures, on a clean tree:

```
test_get_document              assert 401 == 200
test_get_document_not_found    assert 401 == 404
test_update_document           assert 401 == 200
test_patch_document            assert 401 == 200
test_delete_document           assert 401 == 204
test_document_versions         assert 401 == 200
test_restore_version           KeyError: -1
test_export_document_html      assert 401 == 200
test_export_document_markdown  assert 401 == 200
```

Eight say 401. One doesn't. That shape — one cluster plus one outlier — is the
whole lesson: fan out, don't guess.

## Task

Find the root cause of the 401 cluster, decide whether `test_restore_version` is
the same bug, and fix only what the tests demand.

## Suggested prompts

```
9 tests fail in services/document-service. Dispatch repo-scout to find where the 401 originates in the request path, and separately have it check whether test_restore_version shares that cause. Don't fix anything yet.
```

```
Two subagents in parallel: one reads app/api/documents.py auth helpers, one reads tests/conftest.py and how the tests authenticate. I want the mismatch between them.
```

```
Fix the root cause. Then run the verifier subagent on document-service and report the counts.
```

## Capability Spotlight

- **Context protection is the point.** The scout greps a polyglot monorepo and
  returns `file:line` hops. Your main session never sees the transcript, so it
  still has room to reason about the fix. Show `Ctrl+O` (thinking trace) to make
  the difference visible.
- **Parallelism where it's safe.** Two *read-only* scouts at once is free. Two
  agents editing the same file is not — say that out loud; it's the question every
  customer asks next.
- **Profiles have teeth.** `repo-scout` declares `allowed-tools: read, grep, glob`.
  It cannot edit even if the model wants to. Open the file and show the frontmatter.
- **Roles, not clones.** Scout finds, main session decides, verifier proves. The
  verifier re-runs `poetry run pytest -q` and reports exit code and counts —
  independent of whoever wrote the fix.
- **Enablement:** Devin Desktop → Settings → **Subagents (Preview)**. In the CLI,
  `subagents_enabled` in config controls the same thing.

## How to Verify

```bash
poetry run pytest -q            # fewer failures, and no test file modified
git diff --stat tests/          # must be empty — tests are the source of truth
git diff app/                   # small and explainable
```

## What "Done" Looks Like

- A named root cause with a `file:line`, not "something with auth".
- An explicit verdict on `test_restore_version`: same bug or separate.
- A fix in `app/`, zero changes under `tests/`.
- Counts reported by the verifier, not asserted by the fixer.

## Tips

- If a scout returns prose instead of paths, its report contract is too loose —
  tighten the profile. That's a Lab 4 moment.
- Ask "what did you rule out?" Ruled-out branches are the highest-value part of an
  investigation and are usually thrown away.
- Resist fixing all nine at once. Fix the cluster, re-measure, then look at the
  outlier with a smaller problem in front of you.
