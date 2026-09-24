# Playbook: Verify a dependency-update PR and mark it "✅ Build verified"

> **Facilitator / author:** this file is the source for a **Devin Playbook** and
> the prompt of the **deps-verify** Devin automation (webhook trigger, called by
> `.github/workflows/renovate-verify.yml`). Copy it into your Devin organization
> (Settings → Playbooks → *Create a new Playbook*) so sessions can invoke it as
> `!dependency-bump-verify`, and paste the same text as the automation's prompt.
> See [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks)
> and [Automations](https://docs.devin.ai/product-guides/automations).

## Overview

A dependency bot (Dependabot, Renovate) has opened a PR that bumps one or more
library versions. A green CI badge on that PR proves the code compiles; it does
not prove the bump is *real* (the old version is no longer reachable from any
module's dependency tree) or *safe* (the library still behaves the way the
application depends on). This playbook turns the bump into evidence with the
repository's `make deps-*` harness, fixes what the bump broke, and — only when
every check is green — posts a PR comment whose first line is exactly
`✅ Build verified` followed by the evidence lines. That comment is the contract:
`.github/workflows/group-verified-deps.yml` watches for it and starts the
grouping automation (`dependency-bump-group.devin.md`).

The guiding principle is the same as `dependency-cve-remediation.devin.md`: **a
bumped version in a manifest is a claim; the harness output is the proof.**

## Input (webhook payload)

The automation is started with a JSON body from `renovate-verify.yml`:

```json
{
  "source": "dependency-bump",
  "repository": "Cognition-Partner-Workshops/otterworks",
  "branch": "dependabot/gradle/services/auth-service/spring-minor-patch",
  "head_sha": "…",
  "pr_number": "123",
  "pr_url": "https://github.com/…/pull/123",
  "pr_author": "dependabot[bot]",
  "bot_authored": true,
  "changed_manifests": ["services/auth-service/build.gradle"],
  "dependency_summary": "PR title: …\n### services/auth-service/build.gradle\n-  …:3.2.0\n+  …:3.2.5",
  "attempt": 0,
  "max_attempts": 2
}
```

If you were started by hand instead, ask for the repository and PR number and
derive the rest with `gh pr view`.

## Procedure

1. **Check out the PR branch.** `gh pr checkout <pr_number>` in the repository
   (or `git fetch origin <branch> && git checkout <branch>`). Confirm
   `git rev-parse HEAD` matches `head_sha`; if the branch has moved on, work on
   the new head and say so in the comment.

2. **Read the bump before running anything.** From `changed_manifests` and
   `dependency_summary`, list every artifact that changed: old version, new
   version, and whether the jump is patch, minor or **major**. For a major, read
   the release notes now — that is where `javax.*` → `jakarta.*`, Spring Boot 2 →
   3, Ktor 2 → 3 and similar migrations announce themselves. Map each manifest to
   its harness module id via `security/deps/modules.yaml` (`report-service`,
   `legacy-portal`, `auth-service`, `notification-service`). A manifest with no
   module id (a frontend `package.json`, `go.mod`, `Cargo.toml`) is verified with
   the module's own suite in step 5 and reported as **not covered by the deps
   harness** — never as passing the gate.

3. **Inventory the blast radius.** Run `make deps-inventory`. It resolves every
   JVM module's real dependency tree and records, per module, the resolved
   version of the artifact under advisory, direct vs transitive, and the parent
   that pulls it. Save the exit code and the table. A module reported
   **unmeasured** (missing JDK, tool failed to start) is not a clean module;
   install what it needs (see the `java_home` candidates in `modules.yaml`) and
   run again before you continue.

4. **Run the harness on the affected modules.** For each module id from step 2:

   ```bash
   make deps-tests MODULE=<id>         # build + full suite
   make deps-gate                      # vulnerable version unreachable at any depth
   make deps-transcript MODULE=<id>    # library behavior unchanged vs the recorded before-state
   ```

   If the bump touches a shared BOM or version property (Spring Boot parent,
   `gradle/libs.versions.toml`, a `<properties>` block used by several modules),
   run `make deps-tests` and `make deps-transcript` **without** `MODULE=` so
   every consumer is measured. Record for each command: exit code, the suite
   line (`tests=N failures=0 errors=0 skipped=K`), and for the gate the verdict
   line as printed (`GATE PASSED: …` / `GATE FAILED: …` / `GATE INCONCLUSIVE: …`).

   **The gate on the golden `main` is red today**: `report-service` and
   `notification-service` pin `commons-text` 1.9, inside the advisory range of
   `security/deps/advisory.yaml` (CVE-2022-42889, fixed in 1.10.0). So:
   - If the PR bumps `commons-text` (or anything that pulls it), the gate
     **must** turn green — that is the bump being real.
   - If the PR does not touch the advisory artifact, run `make deps-gate` on
     the merge-base too (`git stash`-free: `git worktree add /tmp/base
     $(git merge-base HEAD origin/main)` and run there). The verdict must be
     identical — same artifact, same modules, same versions. Report it as
     `GATE FAILED (pre-existing on main @<sha>, unchanged by this bump)`. A gate
     that got *worse* (a new module or a new vulnerable path) is the bump's
     fault and blocks `✅`.
   `deps-transcript` exit codes: 0 = every contract case identical and every
   attack case neutralized, 1 = a case changed, 2 = inconclusive (unmeasured).
   Treat 2 as a failure to explain, not a pass.

5. **Run the module's own build for anything the harness does not cover.**
   `./gradlew check`, `mvn -B verify`, `npm test`, `cargo test`, `go test ./...`
   as appropriate. Capture the same three facts: exit code, suite counts,
   the failing test names if any.

6. **Fix what the bump broke — minimally.** When a step is red:
   - **Compile errors from renamed packages** (`javax.servlet` → `jakarta.servlet`,
     `javax.persistence` → `jakarta.persistence`, `javax.validation` →
     `jakarta.validation`): update the imports and the matching starter/BOM
     coordinates together. Spring Boot 3 requires JDK 17 — if the module pins an
     older JDK in `modules.yaml` or its Dockerfile, the bump is not a drop-in
     and you must say so.
   - **Removed or changed APIs**: change the call sites and nothing else. No
     opportunistic refactors; the PR must stay reviewable line by line.
   - **Behavior transcript changes a contract case**: the library changed
     something the application depends on. Do not "fix" the recorded transcript
     to match. Either pin to the nearest release that keeps the contract, or
     stop and report — a changed contract case is a regression, not a task for
     `make deps-record`.
   - **Gate still red after the bump**: a transitive path still pulls the old
     version. Add an explicit pin or move the intermediate library, and say so.
   Commit fixes to the PR branch with a plain message (`fix: migrate
   javax → jakarta imports for Spring Boot 3.x bump`). Each push re-fires
   `renovate-verify.yml`; the workflow counts your commits and escalates after
   `max_attempts`. Do **not** open a second PR for the fix. Do not touch unrelated
   files, and do not fix the planted Rails logging bug in `admin-service` (see
   `AGENTS.md`).

7. **Re-run everything after the last fix.** Steps 3–5 again, from clean. The
   evidence you post must come from the final commit, not from a run that
   predates it.

8. **Post the verdict.** Exactly one comment on the PR, via
   `gh pr comment <pr_number> --body-file …`.

   **All green** — the first line is exactly `✅ Build verified`, then the
   evidence:

   ```
   ✅ Build verified

   Branch: <branch> @ <short-sha>
   Modules: report-service (maven, JDK 11)
   Bumps: org.apache.commons:commons-text 1.9 → 1.10.0 (minor)

   make deps-inventory              exit 0   4 modules measured, 0 unmeasured
   make deps-tests MODULE=report-service   exit 0   "TESTS PASSED: 1 modules." (tests=<N> failures=0 errors=0 skipped=<K>)
   make deps-gate                   exit 1   "GATE FAILED: CVE-2022-42889 still reachable:" notification-service (direct 1.9), legacy-portal (via commons-configuration2:2.8.0) — pre-existing on main @<sha>, both untouched by this PR; report-service now clean
   make deps-transcript MODULE=report-service   exit 0   "TRANSCRIPT PASSED: <N> cases across 1 modules"
   mvn -B verify (JDK 11)           exit 0

   Fixes on this branch: none
   Not covered by the deps harness: none
   ```

   The quoted strings are the harness's own verdict lines (`TESTS PASSED`,
   `GATE PASSED`, `TRANSCRIPT PASSED`, or their `FAILED` / `INCONCLUSIVE`
   counterparts); paste them as printed, with the counts the harness reports.
   Every line is a fact you observed in this run. If a module was unmeasured,
   a step was skipped, or a manifest is outside the harness, it goes under
   `Not covered` — and the comment must **not** start with `✅ Build verified`.

   **Not green after your fixes** — first line `❌ Build not verified`, same
   evidence layout, then the failing target, the first error, and what you
   tried. The workflow's attempt counter decides whether to try again or open
   the escalation issue; you do not.

## Specifications

The work is done when all of these hold:

- The PR branch head you tested is the head you commented on.
- Every module touched by the bump is **measured** by the harness or explicitly
  listed under `Not covered` with the substitute check you ran.
- `make deps-gate` exits 0 — or, when the PR does not touch the advisory
  artifact, its verdict line is identical to the one on the merge-base and the
  comment says so on the gate line.
- Every affected module's full suite passes and the counts are in the comment.
- Every transcript contract case is identical and every attack case neutralized
  (`make deps-transcript` exit 0), or the comment is `❌`.
- Any code change you made is minimal, explained in the comment, and pushed to
  the PR branch — never to `main`, never to a new PR.
- The comment begins with `✅ Build verified` **only** when all of the above
  hold. No emoji-line-then-caveats.

## Advice and pointers

- **The harness first, the module build second.** `make deps-tests` already runs
  each module's own suite on the JDK it needs; running `./gradlew test` by hand on
  the wrong JDK produces failures that are yours, not the bump's.
- **Read `security/deps/modules.yaml` before you run anything.** It tells you the
  JDK per module (report-service and legacy-portal need JDK 11 for the Nashorn
  transcript case; auth-service and notification-service need 17) and which tool
  wrapper each uses.
- **Majors are where the work is.** A patch bump that goes red usually means a
  transitive conflict; a major that goes red usually means an API migration.
  Say which one you found.
- **Do not self-merge, do not approve.** Your output is the comment. Humans and
  the grouping automation take it from there.
- **Attempt budget.** The payload tells you `attempt` and `max_attempts`. On the
  last attempt, prefer a clear `❌` with a diagnosis over a speculative fix.
