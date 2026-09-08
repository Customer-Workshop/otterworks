---
name: feature-analysis
description: >
  How to do the business-analyst job in OtterWorks: turn an ambiguous feature
  request or user story into a requirements and implementation-plan artifact
  without writing production code. Covers which repo surfaces are authoritative
  for "how does this already work", how to find the mechanisms a story collides
  with, the ambiguity register, slicing, acceptance criteria, and which existing
  harness proves each one.
---

# Feature Analysis — OtterWorks

Use when the ask is *planning*, not building: "what would it take to…", "write
the requirements for…", "this story is vague, work out what it means", story
refinement, or sizing. The deliverable is a markdown artifact in
`docs/analysis/`, not a code change.

Worked example: `docs/analysis/expiring-share-links.md` (from the story *"share a
document with someone outside my team, but access shouldn't hang around
forever"*).

## Rules

1. **No production code.** The output is an analysis document. If the analysis
   makes an implementation obvious, say so and stop; opening the code PR is a
   separate task with a separate approval.
2. **Every claim is a citation.** `path:line`, read this session. "The gateway
   probably requires auth" is worthless; `jwt.go:33` listing exactly two public
   paths is the finding.
3. **Read the enforcement point, not the handler name.** A route called
   `share_file` says nothing about whether reads check the share. In this repo
   they don't — that gap only shows up by reading `download_file`.
4. **Leave ambiguity open.** Record each unanswered question with a recommended
   default and the cost of being wrong. Do not silently pick one and design
   around it.
5. **Never "fix" what you find.** Planted bugs and registered security-lab
   fixtures are the point of the golden app (`AGENTS.md`,
   `security/equivalence/findings.yaml`). Note them as constraints on the plan.
6. **Refuse to estimate past an unanswered architectural question.** Say which
   question changes the answer.

## Where the truth lives

Read in this order; each is cheap and kills a whole class of wrong assumption.

| Question | Authoritative surface |
|---|---|
| What is edge-reachable, and what is already known to be broken about it | `docs/api-route-matrix.md` (also lists gateway prefix gaps) |
| How a request actually traverses the services | `docs/flows.md` (sequence diagrams per flow) |
| Whether the story's route is public or protected | `services/api-gateway/internal/config/config.go` (prefix → service) + `internal/middleware/jwt.go` (`DefaultPublicPaths`) |
| Which service owns the behavior, in which language | `services/<name>/` — the ownership table in `.agents/skills/dast-remediation/SKILL.md` is the fastest index |
| What the wire contract says | `shared/openapi/` (3 of 11 services only) and `shared/events/schemas/` |
| What already fires downstream | publisher (`events.rs`, SNS/SQS) → `services/audit-service/src/Services/SnsConsumer.cs` → `services/notification-service/.../NotificationTemplates.kt` |
| What behavior is already pinned | `tests/api/` (black-box flows), `tests/contract/`, per-service tests, `docs/bdd/` |
| What the UI already promises the user | `frontend/client-app/src/lib/api.ts` (every call the web app makes) and the relevant component |
| Known systemic gaps — do not rediscover them | `docs/SDLC-COVERAGE.md` |
| Repo-specific mechanics for an adjacent area | the other `.agents/skills/*/SKILL.md` |

Grep the story's noun across `services/`, `frontend/`, `shared/` and `docs/`
before assuming the feature is new. In OtterWorks the usual outcome is that
**two** partial implementations already exist in different services with
different data models — finding that is most of the analysis.

## Procedure

1. **Restate the input verbatim** and record what context was *not* supplied
   (ticket, mock, acceptance criteria, requester).
2. **Inventory what exists.** One table per competing mechanism: subject, data
   model, mint/redeem routes, revocation, expiry, storage. Cite every cell.
3. **Trace one request end to end** for the closest existing behavior: client →
   gateway (auth decision) → owning service (authorization decision) → datastore
   → event → audit/notification → UI. The gaps in that chain are the findings.
4. **Write the findings** as numbered, cited statements of fact — especially
   anything that makes the story impossible as written (in the worked example:
   the recipient must already have an account, and the anonymous route 401s at
   the edge).
5. **Build the ambiguity register**: question, recommended default, why it
   matters. Mark which questions are architectural (they gate the estimate).
6. **State scope in and out.** Name the out-of-scope items explicitly; unnamed
   scope gets assumed in.
7. **Slice** into independently mergeable, independently provable changes, each
   with the files it touches. Call out the one slice that carries the security or
   blast-radius review (in this repo it is nearly always the gateway).
8. **Write acceptance criteria in Gherkin**, including at least one negative
   scenario that pins the blast radius ("this token does not become a general
   bypass").
9. **Map each criterion to an existing harness** (next section). A criterion no
   existing harness can reach is itself a finding.
10. **Risks + what you did not verify.** Static-only analysis must say so.

## Proving the plan with harnesses that already exist

| Layer | Command |
|---|---|
| Service unit tests | per-service, see the blueprint's `test` section (`poetry run pytest`, `go test ./...`, `cargo test`, `./gradlew test`, …) |
| Black-box API flows through the gateway | `make test-api-flows` (suites in `tests/api/`) |
| Side effects (audit/notification/analytics) | `tests/api/test_side_effect_flow.py` |
| API contracts | `tests/contract/` — today only `test_search_contract.py`, validating search-service against `shared/openapi/search-service.yaml`. **No harness validates `shared/events/schemas/`**; an event-shape criterion needs a slice of its own |
| Any newly edge-reachable route | `make dast-routes`, `make dast-scan`, `make dast-coverage` |
| Behavior parity when refactoring an existing class | `.agents/skills/secure-refactor-equivalence/SKILL.md` |

Prefer extending an existing suite over proposing a new harness; if the plan
needs a new one, that is a slice with its own cost.

## Deliverable template

```
docs/analysis/<slug>.md

1. Input (verbatim story + missing context)
2. What <noun> already means in this repo   (comparison table + numbered findings, all cited)
3. Ambiguity register                        (question | recommended default | why it matters)
4. Scope in / out
5. Slices                                    (slice | change | files)
6. Acceptance criteria                       (Gherkin, incl. a negative scenario)
7. How each criterion gets proved            (criterion | proof | command)
8. Risks
9. What was not verified
```

## Anti-patterns

- Summarizing the story back with tidier headings and no citations.
- Proposing a greenfield design for something two services already do half of.
- Answering the ambiguities yourself and presenting one option as the plan.
- Estimating in human-team weeks. Size in sessions, and only after questions
  1-3 of the register are answered.
- Quietly folding a security-lab fixture's remediation into the feature plan.
