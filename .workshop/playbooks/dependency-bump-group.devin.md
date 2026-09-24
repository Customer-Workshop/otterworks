# Playbook: Group verified dependency PRs into one combined, re-verified PR

> **Facilitator / author:** this file is the source for a **Devin Playbook** and
> the prompt of the **deps-group** Devin automation (webhook trigger, called by
> `.github/workflows/group-verified-deps.yml`). Copy it into your Devin
> organization (Settings → Playbooks → *Create a new Playbook*) so sessions can
> invoke it as `!dependency-bump-group`, and paste the same text as the
> automation's prompt.

## Overview

Dependency bots open one PR per bump (or per bot-side group). After
`dependency-bump-verify.devin.md` has proven each one with the `make deps-*`
harness and posted `✅ Build verified`, a human still has to merge N PRs, and
N green PRs merged one after another can still be red together (two bumps that
each pass alone but pull conflicting transitive versions once combined). This
playbook collapses the verified set into **one** combined branch, proves the
*combination* with the same harness, and opens **one** PR for a human to merge.

Two rules decide what may be combined:

- **Shared version property → one PR.** Bumps that flow through the same
  declaration (a Spring Boot parent/BOM, a `<properties>` block, a
  `gradle/libs.versions.toml` alias, a Gradle version catalog) belong together;
  splitting them leaves the estate in a half-upgraded state no test covers.
  Bumps that touch *different* modules with *no* shared declaration may be
  combined for convenience, but must not be forced together if the combined
  harness run goes red — drop the offender back out and say so.
- **Module boundaries come from the code, not from file paths.** Use DeepWiki
  (`ask_question` on the repository: "which services share the Spring Boot
  version?", "which modules consume commons-text transitively?") and
  `security/deps/modules.yaml` to see which modules share build files, parents
  and transitive paths. `make deps-inventory` is the ground truth for the
  transitive picture.

Devin **never merges its own PRs**. The combined PR is left open, re-verified,
for a human.

## Input (webhook payload)

```json
{
  "source": "deps-verified-comment",
  "repository": "Cognition-Partner-Workshops/otterworks",
  "pr_number": "123",
  "branch": "dependabot/gradle/services/auth-service/spring-minor-patch",
  "comment_url": "https://github.com/…/pull/123#issuecomment-…",
  "verification_comment": "✅ Build verified\n\nBranch: … ",
  "verified_marker": "✅ Build verified",
  "verified_prs": [ {"number": 123, "branch": "…"}, {"number": 124, "branch": "…"} ]
}
```

`verified_prs` is a hint captured at trigger time. Re-derive it yourself in
step 1; more PRs may have been verified (or closed) since.

## Procedure

1. **Enumerate the verified set.** In the repository:

   ```bash
   gh pr list --state open --json number,headRefName,author,title,files \
     --jq '.[] | select(.author.login != "devin-ai-integration[bot]")'
   ```

   For each candidate, read its comments (`gh api repos/<repo>/issues/<n>/comments`)
   and keep it only if the **latest** comment by `devin-ai-integration[bot]`
   starts with `✅ Build verified`. Skip PRs that already carry a
   `combined-deps` label (they were grouped before) and skip Devin-authored PRs
   (the previous combined PR). If the set has fewer than two PRs, post a short
   comment on the triggering PR saying grouping is waiting for more verified
   bumps, and stop. Nothing else needs doing.

2. **Map bumps to declarations.** For each verified PR, list the manifests it
   touches and the artifacts it bumps (from the diff and its verification
   comment). Look up the module id per manifest in `security/deps/modules.yaml`.
   Then ask DeepWiki and read the build files to answer, for every pair of PRs:
   *do they change the same version property, parent, BOM or catalog alias?* and
   *do their modules share a transitive path to the same artifact?* Write the
   answer down as a grouping table before you touch git:

   ```
   group A (shared: spring-boot parent 3.2.x)  → PR #123 auth-service, PR #125 legacy-portal
   group B (independent)                        → PR #124 notification-service ktor
   excluded                                     → PR #126 (major bump, verify comment lists a caveat)
   ```

   A verified major that carries a code migration may be grouped only if its
   migration does not touch files another PR in the group touches. If unsure,
   leave it as its own PR and say why.

3. **Create the combined branch.** From the default branch:

   ```bash
   git fetch origin
   git checkout -b devin/combined-deps-$(date +%Y%m%d) origin/main
   ```

   Bring in each PR in the order that minimises conflicts (shared-property
   groups first, then independent modules): prefer `git cherry-pick <sha>…` of
   the PR's commits so authorship is preserved; fall back to
   `git merge --no-ff origin/<branch>` when a PR has many commits. Resolve
   conflicts only in manifests and lock files; if a conflict lands in source
   code, drop that PR from the group (`git cherry-pick --abort` / `git reset
   --merge`), note it in the excluded list, and continue.

4. **Prove the combination.** On the combined branch:

   ```bash
   make deps-inventory
   make deps-tests
   make deps-gate
   make deps-transcript
   ```

   All four **without** `MODULE=`, so every module is measured together.
   Record exit codes and the `TESTS PASSED` / `GATE PASSED` /
   `TRANSCRIPT PASSED` lines. The gate on the golden `main` is red today
   (`commons-text` 1.9 in `report-service`, `notification-service` and, via
   `commons-configuration2`, `legacy-portal`) and it is estate-wide, so apply
   the same per-module rule as the verify playbook: compare the
   `<module> -> commons-text:<version>` lines under `GATE FAILED` with the
   merge-base's. Every module a grouped PR bumps must be absent from the
   combined head's list; every remaining line must be identical to the
   merge-base's, and the PR body says `remaining paths pre-existing on main,
   unchanged; <modules> now clean`. `GATE PASSED` is required only when the
   group covers the last vulnerable module (e.g. all three `commons-text`
   consumers bumped together). If anything else is red, bisect by removing the most
   recently added PR from the branch and re-running until green; every PR you
   drop goes into the excluded list with the failing line that excluded it.
   Never edit source to make a combination pass — the individual PR is the place
   for a fix, via the verify playbook.

5. **Open ONE combined PR** against the default branch, labelled
   `dependencies` and `combined-deps`, titled like
   `deps: combine 3 verified bumps (spring-boot 3.2.5, springdoc 2.5.0, ktor 2.3.12)`.
   The body must have:
   - the grouping table from step 2 with the *why* per group;
   - one line per included PR: `#123 (auth-service) — ✅ Build verified <comment link>`;
   - the excluded PRs and the exact reason each was excluded;
   - the combined harness evidence (exit codes and verdict lines) from step 4;
   - `Closes #123, closes #125, …` for every included PR so merging the combined
     PR closes the originals;
   - a closing line: *This PR was assembled and re-verified automatically. It is
     left open for a human to review and merge; Devin does not merge its own PRs.*

   Do not use `Co-authored-by`, requester names or e-mail addresses in the body.

6. **Comment back on each included PR** with one line:
   `Grouped into <combined PR url>; merge that one instead.` Do not close the
   originals yourself — the `Closes` keywords do it on merge, and a human may
   still decide to merge one alone.

7. **Do not merge. Do not approve.** Stop when the combined PR is open and its
   checks are running.

## Specifications

The work is done when all of these hold:

- Every open, non-Devin PR whose latest Devin comment starts with
  `✅ Build verified` is either in the combined PR or in its excluded list with a
  reason.
- No group splits a shared version property across two PRs.
- `make deps-tests` and `make deps-transcript` exit 0 on the combined branch
  head; `make deps-gate` exits 0, or its `GATE FAILED` list contains none of
  the modules the group bumps and is otherwise verbatim-identical to the
  merge-base's (pre-existing advisory in modules the group does not touch);
  the verdict lines are in the PR body.
- Exactly one combined PR exists per grouping run, against the default branch,
  and it is **not** merged or approved by Devin.
- Each included original PR has the one-line pointer comment.

## Advice and pointers

- **Idempotency.** `group-verified-deps.yml` fires on every `✅ Build verified`
  comment. If a combined PR is already open and unmerged, update *that* branch
  (cherry-pick the newly verified PR onto it, re-run step 4, push, edit the
  body) rather than opening a second combined PR.
- **Conflict in a lock file** (`package-lock.json`, `Cargo.lock`, `uv.lock`):
  regenerate it with the ecosystem's tool rather than hand-merging.
- **A red combination is information, not a failure of this playbook.** Two
  green bumps that are red together is exactly the situation the human needed
  to know about; the excluded list with the failing line is the deliverable in
  that case.

## Scale: coordinator–worker fan-out across repositories

The two playbooks above are single-repository. The estate story — "65 repos,
each with a queue of stale or unverified dependency PRs" — uses the same two
playbooks under a coordinator session:

1. **Discover.** A parent session (started by hand, on a schedule, or by an
   automation) lists the repositories in scope
   (`gh repo list <org> --json name,pushedAt`, or a checked-in list) and, per
   repository, the open dependency-bot PRs and their state: no Devin comment
   yet, `✅ Build verified`, `❌ Build not verified`, or stale (head behind base
   by more than N days).

2. **Fan out — one child per repository.** For every repository with work, the
   parent spawns a child session with the `dependency-bump-verify` playbook and
   a prompt of the form:

   ```
   Repository: <org>/<repo>. Run !dependency-bump-verify on each of these PRs in
   order: #12, #15, #18. Post the ✅ / ❌ comment on each. When all are commented,
   run !dependency-bump-group once. Report the combined PR URL, or the reason no
   group was formed, as your final message.
   ```

   One child per repository, not per PR, because the grouping step needs the
   whole repository's verified set. Children run in parallel on their own
   machines. Cap concurrency (e.g. 10 at a time) to stay inside the CI runners'
   and the organisation's session limits.

3. **Collect.** The parent waits for children and assembles one report:
   repository → PRs verified / failed / excluded, combined PR URL, and any
   escalation issues opened by `renovate-verify.yml`. Post it where the team
   reads (a tracking issue, Slack, the run-sheet's summary section).

4. **Retry budget.** A child that ends without a final report is retried once;
   a repository whose children fail twice is listed under "needs a human" with
   the last error. The same `MAX_FIX_ATTEMPTS` idea that bounds a single PR
   bounds the estate run.

Mechanics for creating and monitoring child sessions are in Devin's
`managing-child-sessions` skill and the API docs
(<https://docs.devin.ai/api-reference>). In the demo, run the fan-out
against two or three repositories (otterworks plus
Cognition-Partner-Workshops/uc-api-ehrbase, which already has a
`.github/dependabot.yml`) to show the shape; the 65-repository run is the same
loop with a longer list.
