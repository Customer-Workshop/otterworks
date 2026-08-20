# Contract — User Preferences

**Status: frozen.** Derived from `com.otterworks.legacyportal.userpreferences` plus the recorded
transcript (`baseline-transcript.json`). Read [`README.md`](README.md) first — it defines the two
error envelopes, the parity normalisation rules and the identity gap that apply here.

| | |
|---|---|
| Service module | `services/portal/user-preferences-service` |
| Base package | `com.otterworks.portal.userpreferences` |
| Port | `8102` |
| Database | `user-preferences-db` (PostgreSQL 16), database `user_preferences`, role `user_preferences` |
| Route prefix | `/api/preferences` — **unchanged** |

> This is the context the assessment flags as "deceptively implicit". Its defining behaviour —
> `GET` never 404s, fabricates defaults, and does **not** persist them — is easy to break during
> extraction and hard to notice. It is spelled out exhaustively below because it is the whole
> risk of this slice.

## 1. Resource

`UserPreference` is keyed by a caller-supplied natural key. There is no surrogate id and no
`createdAt`.

```json
{
  "userId": "u1",
  "theme": "dark",
  "locale": "fr-FR",
  "emailNotifications": false
}
```

Field set is exactly these four, always present. Field order as declared: `userId, theme,
locale, emailNotifications`.

- `userId` — string, max 100 characters, the primary key. **Caller-supplied and unvalidated**:
  it is an opaque identifier defined outside this service, with no user table, no format check
  and no ownership check anywhere. It is echoed back verbatim.
- `theme` — string, non-blank, max 20 characters. **Not an enum.** The monolith accepts any
  non-blank ≤ 20-character string; `"chartreuse"` is a valid theme. Do not introduce an
  allow-list — that would 400 requests the monolith accepts.
- `locale` — string, non-blank, max 20 characters. **Not validated as a locale.** `"zz-ZZ"` and
  `"not a locale"` are both accepted. Do not parse it.
- `emailNotifications` — JSON boolean, never null.

## 2. Routes

Only two. There is no list route, no create route, no delete route, and no search.

### 2.1 `GET /api/preferences/{userId}` — never 404s

This is the clause most likely to be broken. In full:

- If the user has a stored row → `200` with that row.
- **If the user has no stored row → still `200`**, with a fabricated default:
  ```json
  {"userId": "<the path segment, verbatim>", "theme": "light", "locale": "en-US", "emailNotifications": true}
  ```
- **The fabricated default is NOT persisted.** No row is written. A second `GET` for the same
  unknown user returns the same fabricated response and the table is still empty. A subsequent
  `PUT` must behave as a first write, not as an update. The transcript exercises exactly this
  sequence (`GET` unknown, `GET` unknown again) and a parity suite must too.
- Therefore: **this route never returns 404 for any `userId`, ever**, including empty-ish,
  unicode, or absurdly long segments. (A segment longer than 100 characters still returns
  fabricated defaults on `GET`; it only fails on `PUT`, at the database. See §5.)
- Defaults are exactly `light` / `en-US` / `true`. They are constants
  (`UserPreferenceService.DEFAULT_THEME`, `DEFAULT_LOCALE`, and a literal `true`), not
  configuration. Keep them as constants in the extracted service; do not make them configurable.

### 2.2 `PUT /api/preferences/{userId}` — upsert

Request:

```json
{"theme": "dark", "locale": "fr-FR", "emailNotifications": false}
```

- The body carries **no `userId`**. The key comes solely from the path segment. If a body
  happens to contain a `userId` field it is ignored (unknown field), and must stay ignored.
- `theme` — required, non-blank, ≤ 20 characters.
- `locale` — required, non-blank, ≤ 20 characters.
- `emailNotifications` — optional. It binds to a **primitive `boolean`**, so **absent or `null`
  → `false`**. This is a real trap: omitting the field silently turns notifications off rather
  than leaving them unchanged. Reproduce it; do not "fix" it to a merge/patch semantic.
- **`PUT` is a full replace, not a patch.** All three fields are written on every call. There is
  no `PATCH` route.

Responses:

- `200` (**not** `201`, even when the row is created by this call) with the stored resource.
- Bean-validation failure on `theme` or `locale` → `400` with the **default error envelope**
  (`{"timestamp","status","error","path"}`, no `message`).
- Malformed JSON → `400`, default envelope.

Upsert semantics in detail, matching `UserPreferenceService.save`: load the row by id; if
absent construct a new one seeded with the defaults; then overwrite all three fields from the
request and save. The seeding is unobservable (every field is immediately overwritten) but keep
the shape so future contract diffs stay honest.

### 2.3 Unmapped

`GET /api/preferences` (no id) → `404`, default envelope. `DELETE /api/preferences/{userId}` →
`405`, default envelope. Do not define these routes.

## 3. State transitions

There is no lifecycle. A `userId` is in exactly one of two states:

```
   ┌──────────────────────────┐   PUT /api/preferences/{userId}   ┌───────────────────────┐
   │ absent                   │ ────────────────────────────────► │ stored                │
   │ GET → 200 fabricated     │                                   │ GET → 200 stored row  │
   │ default, nothing written │ ◄──── (no transition back) ────── │ PUT → 200 overwrite   │
   └──────────────────────────┘                                   └───────────────────────┘
```

`absent` is not an error state and is not observable as one — from a client's point of view a
user always has preferences. There is no transition from `stored` back to `absent`: nothing in
the contract deletes a row.

## 4. Data ownership

```sql
CREATE TABLE user_preference (
    user_id             VARCHAR(100) PRIMARY KEY,
    theme               VARCHAR(20)  NOT NULL,
    locale              VARCHAR(20)  NOT NULL,
    email_notifications BOOLEAN      NOT NULL
);
```

- Flyway `V1__create_user_preference.sql`. `ddl-auto: none`, permanently.
- The natural key is the primary key, exactly as today. Do not add a surrogate id.
- **No additional index.** The only query is a primary-key lookup; the primary key already
  covers it. (Contrast with the other two contexts, which each gain one index.)
- Table lives in the service's default schema; the monolith's `user_preferences` schema
  qualifier is dropped because the database is now dedicated. Invisible on the wire.

Data migration copies rows verbatim. There is no sequence to preserve.

## 5. Errors — complete table

| Condition | Status | Envelope | Body |
|---|---|---|---|
| `GET` for an unknown user | **200** | — | fabricated defaults; see §2.1. **Never an error.** |
| Bean-validation failure on `PUT` (blank/missing/oversized `theme` or `locale`) | 400 | default | `{"timestamp","status":400,"error":"Bad Request","path":"/api/preferences/{userId}"}` |
| Malformed JSON body | 400 | default | as above |
| `userId` path segment longer than 100 characters on `PUT` | 500 | default | The monolith lets the database reject it; the insert fails and Spring returns a 500 with the default envelope. Reproduce the status; do not add a length check that would turn it into a 400. |
| Method not allowed on a mapped path | 405 | default | `{"timestamp","status":405,"error":"Method Not Allowed","path"}` |
| Unmapped path | 404 | default | `{"timestamp","status":404,"error":"Not Found","path"}` |

The `{"error","message"}` legacy envelope is **never produced by this context** — it has no
`NoSuchElementException` and no `IllegalArgumentException` path. `portal-common` still provides
it; this service simply never triggers it. A parity suite should assert that no response from
this service carries a `message` field.

## 6. Health

`GET /health` → `200 {"status":"UP","service":"user-preferences-service"}`. The monolith's
`banner` field is dropped — see the announcements contract §6 for the rationale; it applies
identically here.

Actuator: `/actuator/health` with liveness/readiness probes, exposure limited to `health,info`.

## 7. Out of scope for this contract

Authentication and ownership checks (see README §identity — acute here, since any caller can
overwrite any user's preferences), a `PATCH` route, enum/locale validation, a delete route,
persisting the fabricated defaults, and configurable defaults. Each would be a contract
revision applied to all three services together.
