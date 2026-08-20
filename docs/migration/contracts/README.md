# Portal decomposition — contracts

`services/legacy-portal` is being decomposed into three deployable services, one per bounded
context, strangler-fig style. These documents are the **binding wire contracts** for that work.

| Context | Contract | Service module | Port | Database |
|---|---|---|---|---|
| Announcements | [`announcements.md`](announcements.md) | `services/portal/announcements-service` | 8101 | `announcements-db` |
| User Preferences | [`user-preferences.md`](user-preferences.md) | `services/portal/user-preferences-service` | 8102 | `user-preferences-db` |
| Feedback | [`feedback.md`](feedback.md) | `services/portal/feedback-service` | 8103 | `feedback-db` |

Companions: [`../skeleton.md`](../skeleton.md) is the shared service pattern every child
extends; [`../data-seams.md`](../data-seams.md) is the Wave 0 confirmation that each context
can take its own database.

Background: Confluence space **Legacy Modernization (LM)** — _Legacy Portal — Modernization
Assessment_ and its children (Application Inventory, Dependency Graph, Bounded Contexts & Seams,
Migration Slice Recommendation).

## Rules of engagement

1. **The contract is authoritative and frozen.** It was derived from the monolith's source *and*
   from a recorded transcript of the running application (see below), not from the README — the
   README is wrong in at least two places (§"Recorded baseline").
2. **No service may deviate from the contract, and no service may change it.** If you believe a
   clause is wrong, **stop and report it upstream**; do not "fix" it locally. A silent deviation
   is indistinguishable from a parity bug.
3. **No service may invent a second pattern.** The shared parent POM, the shared
   `portal-common` library (error envelopes + health), the migration layout, the Dockerfile
   shape and the Compose profile in `services/portal/` already exist. Extend them; do not fork
   them, and do not modify them.
4. **Parity is byte-level on the JSON body and exact on the status code**, modulo the
   normalisations listed in §"Parity normalisation" below. Anything else is a defect.

## Recorded baseline

[`record-baseline.sh`](record-baseline.sh) replays a fixed request script against a running
portal and emits a JSON transcript. It was run against the monolith
(`java -jar services/legacy-portal/target/legacy-portal.jar`) to produce
[`baseline-transcript.json`](baseline-transcript.json). It is **evidence**, not a test: the
graded comparison is `tests/parity/portal/replay.py`, which replays
`tests/parity/portal/scenarios/<context>.json` against the monolith and the extracted service
in the same run and diffs both sides under the normalisations below. The monolith side is now
the pinned pre-retirement image rather than the deployed shell, which no longer serves these
routes; see `docs/migration/decommission.md`. The harness itself is unchanged.

Two things the transcript settled that the source reading alone did not, and that the
assessment page states **incorrectly**:

- **There are two error envelopes, not one.** The `{"error","message"}` envelope only covers
  exceptions that reach `common.GlobalExceptionHandler`. Bean-validation failures and framework
  errors (405, malformed JSON) fall through to Spring's default `/error` body,
  `{"timestamp","status","error","path"}` — **which has no `message` field**. Reproducing only
  the first envelope breaks every 400 in the estate.
- **`POST /api/announcements` honours `published: true`.** The assessment says announcements are
  "created unpublished". They are not: the request field is passed straight through.

## Parity normalisation

A parity comparison MUST compare status code and the full JSON body, with exactly these
normalisations — nothing else:

| Field | Normalisation | Why |
|---|---|---|
| `createdAt` | Compare as an instant; ignore sub-second precision. | The monolith returns nanosecond precision on the create response (in-memory entity) and microsecond precision on subsequent reads (DB round-trip). Both are the same instant. |
| `timestamp` (default error envelope) | Presence and type only. | Wall-clock at the time of the request. |
| `id` | Compare the *sequence* of ids within a replay, not absolute values. | Identity columns start from 1 in a fresh database; a replay against a populated one will not. |
| `path` (default error envelope) | Exact. | Must match — it is the request path. |

One response is **excluded** from parity rather than normalised: `GET /health`. The monolith
adds a `banner` field read from a host file resolved against the working directory; extracted
services drop it deliberately (see [`../skeleton.md`](../skeleton.md) §3). Nothing else differs.

The harness self-check: replaying a scenario against two independently started monolith
instances is 100% identical under these rules. If a normalisation were too weak, that check
would fail; if it were too strong, it would hide a real difference.

## Identity — an explicit, deliberate gap

The monolith has **no authentication of any kind**: `userId` is a caller-supplied opaque string
and any anonymous caller can read or overwrite any user's data. The assessment recommends
closing this at the cut.

**This decomposition does not close it, deliberately**, because introducing identity would make
the response for every unauthenticated request differ from the monolith and there would be no
parity to assert. Every service therefore reproduces the anonymous behaviour exactly, and the
services are marked `INTERNAL-ONLY` in the Compose profile. Closing the gap is a follow-up that
must land as its own contract revision, applied to all three services at once, after the cut is
complete. No service may unilaterally add authentication.
