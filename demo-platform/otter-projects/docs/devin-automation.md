# Wiring Otter Projects to Devin (Demo org)

Two ways to turn "ticket assigned to Devin" into a Devin session, plus the
return path. Everything below uses the **Demo** Devin organization — never the
internal one.

## Option A — Devin Automation with a webhook trigger (recommended)

1. **Devin app → Automations → New → Trigger: Webhook.** Copy the generated
   *webhook URL* and *secret*. (Docs: <https://docs.devin.ai/product-guides/automations#webhook-triggers>.)
2. **Org secret.** In the Demo org, add a secret named `PROJECTS_API_KEY` with
   the Otter Projects API key (from the deployment's Kubernetes Secret). Sessions
   started by the automation use it to call back.
3. **Automation prompt** — the incoming POST body is appended as context, and
   Otter Projects puts the one-line `prompt` as the first field:

   ```
   You are working a ticket from Otter Projects. The webhook payload follows.
   Treat `prompt` as the task and `ticket.description` as the spec; the repo is
   `ticket.repo`. Create a branch, satisfy every acceptance criterion, run the
   relevant tests, and open a PR.

   Report progress to Otter Projects by POSTing JSON to `callback_url` with the
   header `Authorization: Bearer $PROJECTS_API_KEY` (org secret named in
   `callback_api_key`):
     - when you start:      {"session_id": "<your session id>", "session_url": "<your session url>", "status": "working", "message": "<one line>"}
     - when the PR exists:  {"session_id": "...", "session_url": "...", "status": "working", "message": "Opened PR", "pr_url": "<PR URL>"}
     - when you finish:     {"session_id": "...", "session_url": "...", "status": "finished", "message": "<summary>", "pr_url": "<PR URL>"}
   ```
4. **Point Otter Projects at it.** Either globally (Helm `devin.webhookUrl` +
   `secret.devinWebhookSecret`, i.e. env `DEVIN_WEBHOOK_URL` /
   `DEVIN_WEBHOOK_SECRET`) or per project: **Settings → Dispatcher: webhook →
   Webhook URL**. `X-Webhook-Secret` is sent whenever `DEVIN_WEBHOOK_SECRET` is
   set; the HMAC `X-OtterProjects-Signature` is always sent.
5. **Try it:** open a ticket, click **Assign to Devin** (or add the `devin`
   label). The activity tab shows the delivery (`webhook delivery ok (1 attempt,
   HTTP 200)`) and the card moves to *In Progress*. Devin's first callback
   attaches the session; the PR callback moves it to *In Review*; `finished`
   moves it to *Done*.

### Outbound payload (what the automation receives)

```json
{
  "prompt": "Implement OTTER-7: Document export returns 401 for an authenticated user. … Repo: Cognition-Partner-Workshops/otterworks. Acceptance criteria are in the ticket; run the relevant tests and create a PR.",
  "event": "ticket.assigned_to_devin",
  "ticket": { "key": "OTTER-7", "title": "…", "description": "…", "type": "bug", "priority": "High", "status": "Backlog", "labels": ["document-service", "api-gateway", "devin"], "repo": "Cognition-Partner-Workshops/otterworks", "branch": "", "url": "https://projects.otterworks.app/projects/OTTER?ticket=OTTER-7" },
  "project": { "key": "OTTER", "name": "OtterWorks", "repo": "Cognition-Partner-Workshops/otterworks" },
  "callback_url": "https://projects.otterworks.app/api/webhooks/devin?ticket=OTTER-7",
  "callback_api_key": "PROJECTS_API_KEY",
  "callback_instructions": "POST JSON {session_id, session_url, status, message, pr_url} to callback_url with header 'Authorization: Bearer <PROJECTS_API_KEY>' …"
}
```

Headers: `X-OtterProjects-Signature: sha256=<hmac>`, `X-Webhook-Secret: <secret>`,
`X-OtterProjects-Event`, `X-OtterProjects-Ticket`.

## Option B — `devin-api` dispatcher (direct session creation)

1. Create a Demo-org API key (`cog_…`) and note the org id.
2. Set env `DEVIN_API_KEY` and `DEVIN_ORG_ID` (Helm: `secret.devinApiKey`,
   `devin.orgId`). Optionally set the project's *Create sessions as user id*.
3. **Settings → Dispatcher: devin-api.** Assigning to Devin then calls
   `POST /v3/organizations/{DEVIN_ORG_ID}/sessions` with
   `{ prompt, title: "OTTER-7: …", tags: ["otter-projects", "OTTER-7"], create_as_user_id? }`.
   The prompt ends with the same callback instructions as above; the returned
   `session_id`/`url` are attached to the ticket immediately.
4. Because `DEVIN_API_KEY`/`DEVIN_ORG_ID` are set, the **poller** CronJob also
   mirrors session status, new messages and PR links every 60 s — so streaming
   works even if the session never calls back.

## Return path (both options)

```bash
curl -X POST "https://projects.otterworks.app/api/webhooks/devin?ticket=OTTER-7" \
  -H "Authorization: Bearer $PROJECTS_API_KEY" -H "Content-Type: application/json" \
  -d '{"session_id":"devin-abc123","session_url":"https://app.devin.ai/sessions/abc123","status":"working","message":"Reproduced the 401 on the export route; fix in progress."}'
```

HMAC alternative (no API key on the caller):

```bash
BODY='{"session_id":"devin-abc123","status":"finished","message":"Done","pr_url":"https://github.com/Cognition-Partner-Workshops/otterworks/pull/123"}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$PROJECTS_WEBHOOK_SECRET" | awk '{print $NF}')"
curl -X POST "https://projects.otterworks.app/api/webhooks/devin?ticket=OTTER-7" \
  -H "X-OtterProjects-Signature: $SIG" -H "Content-Type: application/json" -d "$BODY"
```

## Env vars the Demo org / deployment needs

| Where | Name | Value |
|-------|------|-------|
| Demo org secrets | `PROJECTS_API_KEY` | Otter Projects API key (so sessions can call back) |
| Otter Projects | `DEVIN_API_KEY` | Demo-org `cog_…` key (Option B + poller) |
| Otter Projects | `DEVIN_ORG_ID` | Demo org id |
| Otter Projects | `PROJECTS_API_KEY` | same value as the org secret |
| Otter Projects | `PROJECTS_WEBHOOK_SECRET` | HMAC secret for outbound/inbound signatures |
| Otter Projects | `DEVIN_WEBHOOK_URL`, `DEVIN_WEBHOOK_SECRET` | Option A automation URL + secret |
