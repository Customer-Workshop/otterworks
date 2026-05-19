# ServiceNow Integration Setup Guide

This document describes how to configure the OtterWorks Admin Service to receive incident webhooks from ServiceNow and auto-launch Devin AI investigation sessions.

## Architecture

```
ServiceNow Business Rule
  → POST /api/v1/admin/snow/ingest  (nested JSON payload)
  → OtterWorks creates Incident + Devin session
  → SnowSyncJob polls Devin status every 30s
  → ServiceNow ticket updated with work notes / state changes
  → POST /api/v1/admin/snow/resolve  (callback when resolved)
```

## Required Environment Variables

| Variable | Description | Example |
|---|---|---|
| `SNOW_WEBHOOK_SECRET` | Shared secret for authenticating inbound webhooks. **Must be set** — requests are rejected if blank. | `my-super-secret-token` |
| `SNOW_INSTANCE_URL` | Default ServiceNow instance base URL (fallback when per-incident URL is not provided). | `https://dev12345.service-now.com` |
| `SNOW_API_USER` | ServiceNow API user for outbound REST calls (work notes, state updates). | `otter_integration` |
| `SNOW_API_PASSWORD` | Password for the ServiceNow API user. | *(secret)* |
| `DEVIN_API_KEY` | Devin AI API key for creating investigation sessions. | *(secret)* |
| `DEVIN_ORG_ID` | Devin organization ID. | `org-abc123` |

## Endpoints

### `POST /api/v1/admin/snow/ingest`

Creates an incident from a ServiceNow ticket. Protected by `X-Snow-Secret` header (must match `SNOW_WEBHOOK_SECRET`).

**Request:**
```json
{
  "incident": {
    "number": "INC0010042",
    "sys_id": "abc123def456",
    "short_description": "File upload returns 500",
    "description": "Users report file uploads failing with HTTP 500",
    "priority": "1",
    "affected_service": "file-service",
    "caller_id": "john.smith",
    "state": "1",
    "instance_url": "https://dev12345.service-now.com"
  }
}
```

**Response (201):**
```json
{
  "status": "created",
  "incident_id": 42,
  "devin_session": {
    "id": "session-uuid",
    "url": "https://app.devin.ai/sessions/session-uuid"
  }
}
```

### `POST /api/v1/admin/snow/resolve`

Resolves an existing incident by ServiceNow ticket number or sys_id. Use this when a ServiceNow ticket is resolved (state 6) or closed (state 7).

**Request:**
```json
{
  "incident": {
    "number": "INC0010042",
    "state": "6"
  }
}
```

**Response (200):**
```json
{
  "status": "resolved",
  "incident_id": 42
}
```

## ServiceNow Business Rule Configuration

Create a **Business Rule** in your ServiceNow instance that fires on incident insert/update:

1. **Name**: `OtterWorks Webhook`
2. **Table**: `incident`
3. **When to run**: After Insert, After Update
4. **Filter Conditions**: Assignment group is "Platform Engineering" (or your target group)
5. **Advanced**: Check "Advanced" and use the script below

### Sample Business Rule Script

```javascript
(function executeRule(current, previous) {
  try {
    var r = new sn_ws.RESTMessageV2();
    r.setEndpoint('https://<your-otterworks-host>/api/v1/admin/snow/ingest');
    r.setHttpMethod('POST');
    r.setRequestHeader('Content-Type', 'application/json');
    r.setRequestHeader('X-Snow-Secret', '<your-shared-secret>');
    r.setRequestBody(JSON.stringify({
      incident: {
        sys_id: current.sys_id.toString(),
        number: current.number.toString(),
        short_description: current.short_description.toString(),
        description: current.description.toString(),
        priority: current.priority.toString(),
        state: current.state.toString(),
        caller_id: current.caller_id.getDisplayValue(),
        affected_service: current.cmdb_ci.getDisplayValue(),
        instance_url: gs.getProperty('glide.servlet.uri')
      }
    }));
    var response = r.execute();
    gs.info('OtterWorks webhook response: ' + response.getStatusCode());
  } catch (ex) {
    gs.error('OtterWorks webhook failed: ' + ex.getMessage());
  }
})(current, previous);
```

### Resolve Callback Script

For auto-resolving when the ServiceNow ticket reaches state 6 (Resolved) or 7 (Closed):

```javascript
(function executeRule(current, previous) {
  if (current.state == 6 || current.state == 7) {
    try {
      var r = new sn_ws.RESTMessageV2();
      r.setEndpoint('https://<your-otterworks-host>/api/v1/admin/snow/resolve');
      r.setHttpMethod('POST');
      r.setRequestHeader('Content-Type', 'application/json');
      r.setRequestHeader('X-Snow-Secret', '<your-shared-secret>');
      r.setRequestBody(JSON.stringify({
        incident: {
          number: current.number.toString(),
          sys_id: current.sys_id.toString(),
          state: current.state.toString()
        }
      }));
      r.execute();
    } catch (ex) {
      gs.error('OtterWorks resolve webhook failed: ' + ex.getMessage());
    }
  }
})(current, previous);
```

## Multi-Instance Support

The integration supports multiple ServiceNow instances. When `instance_url` is provided in the webhook payload, it is stored on the incident and used for all outbound API calls (work notes, state transitions) for that incident. If not provided, the system falls back to the `SNOW_INSTANCE_URL` environment variable.

## How Resolve Callbacks Work

1. When a Devin session completes (`stopped`/`finished`), `SnowSyncJob` automatically updates the ServiceNow ticket state to 6 (Resolved) and resolves the OtterWorks incident.
2. When a ServiceNow ticket is resolved externally, the resolve Business Rule fires and calls `POST /api/v1/admin/snow/resolve`, which resolves the corresponding OtterWorks incident.
3. `SnowSyncJob` polls every 30 seconds and stops after 24 hours to prevent infinite polling.
4. When a Devin session is `blocked` (waiting for human input), a work note is posted but polling continues.
