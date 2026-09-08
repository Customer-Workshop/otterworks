# Otter Projects — REST API

Base URL: `https://projects.otterworks.app` (or `http://localhost:3000`).

## Authentication

| Caller | How |
|--------|-----|
| Browser | Passcode login → HttpOnly cookie `ow_projects_session` (`POST /api/auth/login`) |
| Scripts / automations | `Authorization: Bearer <PROJECTS_API_KEY>` on any `/api/*` route |
| Inbound Devin webhook | Either the API key **or** `X-OtterProjects-Signature: sha256=<hex HMAC-SHA256(rawBody, PROJECTS_WEBHOOK_SECRET)>` |

All bodies are JSON. Errors are `{ "error": "<message>" }` with 400/401/404/409/502.

## Health

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health`, `/api/health` | `{ ok: true }` — no auth, used by probes |

## Auth

| Method | Path | Body / notes |
|--------|------|--------------|
| POST | `/api/auth/login` | `{ passcode }` → sets cookie. Rate limited per IP. |
| POST | `/api/auth/logout` | clears cookie |

## Projects

| Method | Path | Body / notes |
|--------|------|--------------|
| GET | `/api/projects` | `{ projects: Project[] }` |
| POST | `/api/projects` | `{ key, name, description?, repo?, promptTemplate?, dispatcher?, webhookUrl?, createAsUserId? }` — `key` is `[A-Z][A-Z0-9]{1,9}` |
| GET | `/api/projects/:key` | `{ project }` |
| PATCH | `/api/projects/:key` | any subset of the POST fields except `key` |
| DELETE | `/api/projects/:key` | deletes the project and all its tickets |
| GET | `/api/projects/:key/tickets` | `{ tickets: Ticket[] }` |
| POST | `/api/projects/:key/tickets` | `{ title, description?, type?, priority?, status?, labels?, assignee?, branch?, prUrl? }` → `{ ticket }` (key auto-numbered `KEY-n`) |

`dispatcher` ∈ `webhook` (default) · `devin-api` · `none`. `promptTemplate`
placeholders: `{key} {title} {description} {repo} {type} {priority} {labels} {branch}`;
the result is always collapsed to **one line**.

## Tickets

| Method | Path | Body / notes |
|--------|------|--------------|
| GET | `/api/tickets/:key` | `{ ticket, comments, events, deliveries }` |
| PATCH | `/api/tickets/:key` | `{ title?, description?, type?, priority?, status?, labels?, assignee?, branch?, prUrl? }` |
| DELETE | `/api/tickets/:key` | |
| POST | `/api/tickets/:key/transition` | `{ status }` — `Backlog` · `Ready` · `In Progress` · `In Review` · `Done` |
| POST | `/api/tickets/:key/labels` | `{ add?: string[], remove?: string[] }` |
| POST | `/api/tickets/:key/assign` | `{ assignee }` — any handle; `devin` is the built-in bot |
| POST | `/api/tickets/:key/comments` | `{ body, author? }` → `{ comment }` |
| POST | `/api/tickets/:key/devin` | Explicit "Assign to Devin": sets assignee `devin`, dispatches, → `{ ok, ticket, error? }` (502 if the dispatch failed) |

### Trigger rules

Adding the `devin` label **or** setting assignee `devin` (via PATCH, `/labels`,
`/assign`, or `/devin`) dispatches once per ticket via the project's dispatcher
(re-dispatch happens only through `POST /devin`). Success records
`ticket.devin.dispatchedAt`, adds an activity event + comment, and moves the
ticket to **In Progress**. Every attempt is stored as a delivery record shown
in the ticket's activity tab.

## Devin integration

### Outbound: `webhook` dispatcher

`POST <project.webhookUrl || DEVIN_WEBHOOK_URL>` with headers

```
Content-Type: application/json
X-OtterProjects-Event: ticket.assigned_to_devin
X-OtterProjects-Ticket: OTTER-7
X-OtterProjects-Signature: sha256=<hex hmac of body with PROJECTS_WEBHOOK_SECRET>
X-Webhook-Secret: <DEVIN_WEBHOOK_SECRET>          # only when DEVIN_WEBHOOK_SECRET is set
```

and a compact (< 20 KB) body whose **first** key is `prompt`, because Devin
Automation webhook triggers paste the whole body into the session prompt:

```json
{
  "prompt": "Implement OTTER-7: Document export returns 401 for an authenticated user. **Observed on t-main.otterworks.app** … Repo: Cognition-Partner-Workshops/otterworks. Acceptance criteria are in the ticket; run the relevant tests and create a PR.",
  "event": "ticket.assigned_to_devin",
  "ticket": {
    "key": "OTTER-7",
    "title": "Document export returns 401 for an authenticated user",
    "description": "**Observed on t-main.otterworks.app**: …",
    "type": "bug",
    "priority": "High",
    "status": "Backlog",
    "labels": ["document-service", "api-gateway", "devin"],
    "repo": "Cognition-Partner-Workshops/otterworks",
    "branch": "",
    "url": "https://projects.otterworks.app/projects/OTTER?ticket=OTTER-7"
  },
  "project": { "key": "OTTER", "name": "OtterWorks", "repo": "Cognition-Partner-Workshops/otterworks" },
  "callback_url": "https://projects.otterworks.app/api/webhooks/devin?ticket=OTTER-7",
  "callback_api_key": "PROJECTS_API_KEY",
  "callback_instructions": "POST JSON {session_id, session_url, status, message, pr_url} to callback_url with header 'Authorization: Bearer <PROJECTS_API_KEY>' (the org secret named in callback_api_key) whenever you make progress, open a PR, or finish (status \"finished\")."
}
```

Retries: 3 attempts with exponential backoff on network errors, 429 and 5xx;
other 4xx fail fast. The API key **value** is never in the body — only the
secret's *name* (`callback_api_key`).

#### Creating the Devin Automation that receives it

1. In the Devin app (Demo org): **Automations → New automation → Trigger: Webhook**.
2. Copy the automation's **webhook URL** and **secret**.
3. Set on Otter Projects: `DEVIN_WEBHOOK_URL=<webhook URL>` and
   `DEVIN_WEBHOOK_SECRET=<secret>` (Helm: `devin.webhookUrl`, `secret.devinWebhookSecret`),
   or paste the URL into the project's **Settings → Webhook URL** (per-project override).
4. Give the Demo org a secret named **`PROJECTS_API_KEY`** whose value is this
   deployment's API key, so the session can call `callback_url`.
5. Automation prompt (the body arrives as context; keep it short):

   > Work the ticket described in the webhook payload. Use `prompt` as the task,
   > clone `ticket.repo`, satisfy the acceptance criteria, run the relevant tests,
   > open a PR. Report progress by POSTing JSON
   > `{ "session_id", "session_url", "status", "message", "pr_url" }` to
   > `callback_url` with `Authorization: Bearer $PROJECTS_API_KEY`: once when
   > starting (`status: "working"`), when the PR is open (include `pr_url`), and
   > at the end with `status: "finished"`.

See [devin-automation.md](devin-automation.md) for the full walkthrough.

### Outbound: `devin-api` dispatcher

```
POST {DEVIN_API_BASE:-https://api.devin.ai/v3}/organizations/{DEVIN_ORG_ID}/sessions
Authorization: Bearer {DEVIN_API_KEY}
{ "prompt": "<one line prompt> … When done, POST … to <callback_url> …",
  "title": "OTTER-7: Document export returns 401 for an authenticated user",
  "tags": ["otter-projects", "OTTER-7"],
  "create_as_user_id": "<optional project.createAsUserId>" }
```

The returned `session_id` / `url` are stored on the ticket (`ticket.devin`).

### Inbound: `POST /api/webhooks/devin[?ticket=KEY]`

Auth: API key **or** HMAC header (see above). Body:

```json
{
  "ticket": "OTTER-7",                 // optional if ?ticket= is given
  "session_id": "devin-abc123",
  "session_url": "https://app.devin.ai/sessions/abc123",
  "status": "working",                 // free text; "finished"/"done"/"completed" = finished
  "message": "Reproduced the 401; fixing the gateway header handling.",
  "pr_url": "https://github.com/org/repo/pull/42",
  "message_id": "evt_1"                // optional; else dedup uses sha1(message_at|message)
}
```

Effects: Devin-authored comment + activity event; `session_id`/`session_url`/
`status`/latest message stored on the ticket; `pr_url` → **In Review**;
`status: finished` **and** a PR URL → **Done**; a session with no prior
dispatch moves Backlog/Ready → **In Progress**. Duplicate messages (same
`message_id`, or same message+timestamp) are ignored.

```bash
curl -X POST "https://projects.otterworks.app/api/webhooks/devin?ticket=OTTER-7" \
  -H "Authorization: Bearer $PROJECTS_API_KEY" -H "Content-Type: application/json" \
  -d '{"session_id":"devin-abc123","session_url":"https://app.devin.ai/sessions/abc123","status":"working","message":"Opened a PR with the fix.","pr_url":"https://github.com/Cognition-Partner-Workshops/otterworks/pull/123"}'
```

### Poller: `POST /api/devin/poll`

API-key only. For every ticket with `devin.sessionId`, calls the Devin v3
`GET …/sessions/{id}` and `GET …/sessions/{id}/messages` endpoints and mirrors
new Devin messages, status and PR URLs onto the ticket (same dedup + transition
rules as the webhook). The Helm chart runs it from a CronJob every minute.
Returns `{ polled, updated, errors }`; no-op when `DEVIN_API_KEY`/`DEVIN_ORG_ID`
are unset.

## Environment variables

| Var | Purpose |
|-----|---------|
| `PROJECTS_PASSCODE` | UI login passcode |
| `SESSION_SECRET` | signs the session cookie |
| `PROJECTS_API_KEY` | bearer token for the REST API + inbound webhook |
| `PROJECTS_WEBHOOK_SECRET` | HMAC for outbound signatures and inbound HMAC auth |
| `PUBLIC_URL` | base for `callback_url` / ticket links |
| `LOCAL_MODE`, `LOCAL_STORE_PATH` | JSON/in-memory store instead of DynamoDB |
| `PROJECTS_TABLE`, `AWS_REGION` | DynamoDB table (IRSA credentials) |
| `DEVIN_API_KEY`, `DEVIN_ORG_ID`, `DEVIN_API_BASE` | `devin-api` dispatcher + poller |
| `DEVIN_WEBHOOK_URL`, `DEVIN_WEBHOOK_SECRET` | default target + `X-Webhook-Secret` for the `webhook` dispatcher |
