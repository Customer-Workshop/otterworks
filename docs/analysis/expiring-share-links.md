# Feature Analysis — "share a doc with someone outside my team, but not forever"

Worked example produced by the `feature-analysis` skill
(`.agents/skills/feature-analysis/SKILL.md`). It is an analysis artifact, not a
design authority: every claim below is a citation of code on `main` at the time
of writing, and every open question is left open rather than guessed.

## 1. Input (verbatim story)

> As a user, I want to share a document with someone outside my team so they can
> review it, but access shouldn't hang around forever.

Requester context available: none. No ticket, no mock, no acceptance criteria.

## 2. What "share" already means in this repo

Two unrelated sharing mechanisms exist today, in two services, with two data
models and two threat models. Neither matches the story.

| | file-service share | document-service share link |
|---|---|---|
| Subject | a **file** | a **document** |
| Grant | `FileShare` row in DynamoDB — `services/file-service/src/models.rs:56` | nothing persisted — token is derived |
| Recipient | an existing OtterWorks user **UUID** (`shared_with`) | anyone holding the token |
| Token | n/a | `md5(f"{document_id}:{salt}")[:16]` — `services/document-service/app/services/share_link.py:31` |
| Mint | `POST /api/v1/files/{id}/share` — `services/file-service/src/main.rs:84` | `POST /api/v1/documents/{id}/share` — `services/document-service/app/api/documents.py:463` |
| Redeem | `GET /api/v1/files/shared` (own list) | `GET /api/v1/documents/shared?token=` — `documents.py:186` |
| Revoke | `DELETE /api/v1/files/{id}/share/{user_id}` | **impossible** — the token is a pure function of the document id |
| Expiry | **none** — `FileShare` has no TTL field | **none** |

### Findings that decide the shape of this feature

1. **"Outside my team" has no representation in the data model — only "has an
   account" vs. "doesn't".** There is no tenant, team or org field on the user
   table (`services/auth-service/src/main/resources/db/migration/`) or on
   `FileShare`, and `authApi.lookupUser` (`frontend/client-app/src/lib/api.ts:112`)
   resolves *any* registered user by email. So a reviewer who already has an
   OtterWorks account can be shared with today, exactly like a colleague; only a
   recipient **without** an account cannot be a `shared_with` value
   (`api.ts:254`). Anonymous access is therefore not mandatory — it is the answer
   to register question 2, not a given (see §3).
2. **The one anonymous-capable path is not reachable anonymously.** The gateway
   treats every `/api/v1/documents` path as protected
   (`ProtectedPrefixPath: routePrefixes(routes)`,
   `services/api-gateway/cmd/server/main.go:94`) and only `/auth/login` and
   `/auth/register` skip JWT validation
   (`services/api-gateway/internal/middleware/jwt.go:33`). A share link handed to
   an external reviewer returns 401 at the edge. Any external-access story
   therefore *starts* with a gateway change, which is the highest-blast-radius
   file in the repo (all 11 backends sit behind it).
3. **The existing token is not a secret.** It is an unkeyed digest of the
   document id, so it is identical on every mint, cannot be rotated, and is
   forgeable by anyone who can compute MD5 and read the default salt. It is a
   registered security-lab fixture (OW-SEC-403,
   `security/equivalence/findings.yaml`) — see §7, it must not be silently
   "fixed" here.
4. **File access is not gated on the share at all.** `download_file`
   (`services/file-service/src/handlers.rs:355`) and `get_file_metadata`
   (`:203`) look up the file and return it; neither consults ownership nor
   `list_shares`. So "expiring access" to a file cannot be implemented by
   expiring the share row alone — today the row is not on the read path.
5. **`shared_by` is caller-supplied.** `ShareFileRequest.shared_by`
   (`services/file-service/src/models.rs:168`) comes from the request body, not
   from the gateway-injected `X-User-ID` that the same service already trusts
   elsewhere (`resolve_owner_id`, `handlers.rs:225`). Any audit trail for
   expiry/revocation built on `shared_by` inherits a spoofable actor.
6. **Downstreams are already wired for `file_shared` only.** file-service
   publishes `file_shared` (`src/events.rs:123`), audit-service turns it into an
   `action: "share"` audit event
   (`services/audit-service/src/Services/SnsConsumer.cs:113`), notification-service
   renders the `file_shared` template
   (`.../template/NotificationTemplates.kt:46`). There is no `document_shared`,
   no `share_redeemed`, no `share_revoked` — every one of those is new contract
   surface in `shared/events/schemas/file-events.json`.

## 3. Ambiguity register

Each row is a question the story does not answer, with the default this analysis
recommends and the cost of getting it wrong. Rows 1-3 change the architecture and
must be answered before any estimate is meaningful.

| # | Question | Recommended default | Why it matters |
|---|---|---|---|
| 1 | Is the subject a **document**, a **file**, or both? | document only, phase 1 | Different services, languages, datastores; "both" roughly doubles the work and forces a shared share-model decision |
| 2 | Is the recipient (a) an **already-registered user** the owner names, (b) a **guest account** they must create, or (c) an **unauthenticated stranger with a link**? | (c) link, no account | (a) needs no gateway change at all — only expiry on the existing grant, i.e. slices A/B/D minus C; (b) pulls in auth-service, invites, quotas, admin UX; (c) is the only one requiring a public edge route. This single answer moves the estimate more than any other |
| 3 | Does "not forever" mean an **absolute expiry**, an **idle window**, a **view cap**, or **manual revocation**? | absolute expiry, default 7 days, owner may revoke early | Determines whether state must be persisted at all (a signed self-expiring token needs no table; revocation does) |
| 4 | Can the external reviewer **comment**, or only read? | read-only | Comments require an identity to attribute; `POST /documents/{id}/comments` has no anonymous mode |
| 5 | What happens to a live link when the document is **edited or deleted**? | link follows latest version; deletion 404s the link | Versions already exist (`/documents/{id}/versions`); "reviewer sees a snapshot" is a materially different feature |
| 6 | Can the same document have **several links** with different expiries? | one active link per document per phase 1 | Multiple links force a share table + link ids; a single link keeps the derived-token shape |
| 7 | Must expiry/revocation be **visible in the audit trail**? | yes — new `share_redeemed` / `share_revoked` audit actions, and a rejected redemption recorded too | audit-service only understands `file_shared` today; compliance reviewers will ask |
| 8 | Is there an **org policy ceiling** on link lifetime (admin-configurable max)? | out of scope, but do not design it out | admin-service already owns features/quotas; retrofitting a policy later is cheap only if the expiry is stored, not baked into the token |
| 9 | Should a shared-out document appear in the **recipient's search** or **notifications**? | no for anonymous links | search-service scopes by tenant; anonymous recipients have no inbox |

## 4. Scope decision this analysis recommends

**In:** an owner-minted, time-limited, revocable, read-only link to a *document*,
redeemable by an unauthenticated browser, audited on mint/redeem/revoke.
This presumes answer (c) to register question 2; answers (a) and (b) drop slice C
and most of the risk with it.

**Out (name them so they are not assumed):** files, folders, guest accounts,
comments by external reviewers, password-protected links, per-link download
control, admin-level lifetime policy, email delivery of the link.

## 5. Slices

Ordered so each slice is independently mergeable and independently provable.

| Slice | Change | Files |
|---|---|---|
| A. Token becomes a real credential | replace the derived MD5 token with a keyed, expiring token carrying `document_id` + `exp` + a `jti`; keep `mint_token`/`verify_token` signatures | `services/document-service/app/services/share_link.py`, `tests/test_share_link.py` |
| B. Revocation state | persist minted links (id, document_id, expires_at, revoked_at) and check them on redeem | document-service model + migration, `app/api/documents.py:186` |
| C. Anonymous redemption at the edge | make exactly `GET /api/v1/documents/shared` public, leaving every sibling path protected | `services/api-gateway/internal/middleware/jwt.go:33` (exact-match list — note sub-paths of an exact public path stay protected, `jwt_test.go:52`) |
| D. Mint/revoke API + expiry input | `POST /documents/{id}/share` accepts a lifetime and returns `expires_at`; `DELETE /documents/{id}/share` revokes | `app/api/documents.py:463` |
| E. Events + audit | emit `document_shared`, `share_redeemed`, `share_revoked`; teach audit-service the new actions | `shared/events/schemas/document-events.json`, `services/audit-service/src/Services/SnsConsumer.cs` |
| F. UI | the share dialog's "link" tab currently copies `window.location.origin + /files/{id}` — a normal app URL, not a share link (`frontend/client-app/src/components/files/share-dialog.tsx:93`); wire it to the minted link, show the expiry, offer revoke | `share-dialog.tsx`, `src/pages/document-editor.tsx` |
| G. Event-contract coverage | the contract suite is search-OpenAPI only (`tests/contract/test_search_contract.py`) and validates no event schema; add a validator that checks published events against `shared/events/schemas/` | `tests/contract/` |

Slice C is the security-review gate. Everything else is additive; C changes who
may reach a backend without a JWT.

## 6. Acceptance criteria

```gherkin
Feature: Time-limited external share links

  Scenario: Owner mints a link with an expiry
    Given I own a document
    When I create a share link with a lifetime of 7 days
    Then I receive a URL and an expires_at 7 days in the future
    And an audit event with action "share" and resourceType "document" is recorded

  Scenario: A stranger opens a live link
    Given a share link that has not expired or been revoked
    When an unauthenticated browser opens it
    Then the document content is returned read-only
    And no other document is reachable with that token

  Scenario: The link expires
    Given a share link whose expires_at has passed
    When an unauthenticated browser opens it
    Then the response is 403 and the document content is not returned

  Scenario: Every redemption is auditable
    Given a live share link
    When an unauthenticated browser opens it
    Then an audit event with action "share_redeemed" and resourceType "document" is recorded

  Scenario: The owner revokes early
    Given a live share link
    When the owner revokes it
    Then the next redemption is 403
    And the revocation is visible in the audit trail

  Scenario: The link does not become a general bypass
    Given a valid share token for document A
    When it is presented to any other /api/v1/documents path, or for document B
    Then the request is rejected exactly as it would be without the token
```

## 7. How each criterion gets proved (existing harnesses only)

| Criterion | Proof | Command |
|---|---|---|
| Mint/expire/revoke logic | document-service unit tests, extending `services/document-service/tests/test_share_link.py` | `cd services/document-service && poetry run pytest` |
| End-to-end redemption through the gateway | a black-box flow test alongside `tests/api/test_document_flow.py` | `make test-api-flows` |
| Anonymous path is exactly one route | gateway middleware tests (`jwt_test.go` already asserts sub-paths of an exact public path stay protected) | `cd services/api-gateway && go test ./...` |
| No new edge-reachable route goes unattacked | the DAST route/coverage gate — a newly public route is exactly what it exists to catch | `make dast-routes`, `make dast-scan`, `make dast-coverage` |
| Audit side effects | `tests/api/test_side_effect_flow.py` | `make test-api-flows` |
| Redemption audit | `tests/api/test_side_effect_flow.py` | `make test-api-flows` |
| Event shape | **no existing harness reaches this** — `tests/contract/` holds only `test_search_contract.py`, which validates search responses against `shared/openapi/search-service.yaml` and reads no event schema. Slice G exists to build it | n/a until slice G |

Slice A touches OW-SEC-403's subject class. That finding is a deliberate lab
fixture: per `AGENTS.md` and `.agents/skills/secure-refactor-equivalence/SKILL.md`,
the MD5 token must stay on `main`, and the replacement lands on a branch that runs
the equivalence gate — it is not a drive-by fix inside this feature's PR.

## 8. Risks

- **Gateway blast radius (slice C).** The public-path list is global. An
  over-broad entry (prefix instead of exact match) exposes all 11 backends.
- **Enforcement gap precedent (finding 4).** If the feature is ever extended to
  files, note that file reads ignore shares entirely today — "expiring file
  access" is a much larger change than "expiring document access", because the
  authorization check itself does not exist yet.
- **Spoofable actor (finding 5).** Audit rows for share/revoke are only as
  trustworthy as `shared_by`; prefer `X-User-ID` for the new document events.
- **Contract drift.** `shared/openapi/` covers 3 of 11 services and has no
  file-service spec (`docs/SDLC-COVERAGE.md`), so a share contract added only in
  code will not be caught by contract tests.

## 9. What was not verified

- No runtime observation: nothing here was confirmed against a running stack, only
  against source on `main`.
- DynamoDB TTL feasibility for `FileShare` was not checked against the table
  definitions in `infrastructure/` — irrelevant unless question 1 is answered
  "files too".
- No estimate is given: questions 1-3 change the answer by more than the estimate
  would be worth.
