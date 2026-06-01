# ServiceNow → Devin AI Automated Bug Remediation

Receives incident webhooks from ServiceNow and auto-creates [Devin](https://devin.ai) sessions to investigate and fix reported bugs in the OtterWorks platform.

## Architecture

```
┌─────────────┐    Business Rule    ┌──────────────────┐    Devin v3 API    ┌───────────┐
│  ServiceNow │ ──── webhook ─────▶ │  Lambda + APIGW  │ ─── create ──────▶ │  Devin AI │
│  Incident   │                     │  (this stack)    │                    │  Session  │
│             │ ◀── work note ───── │                  │                    │           │
└─────────────┘    callback         └──────────────────┘                    └───────────┘
```

**Flow:**
1. User creates a Software/Critical incident in ServiceNow
2. Business Rule fires → POSTs incident data to this webhook
3. Lambda maps ServiceNow fields to a Devin prompt and creates a session
4. Devin investigates the bug, identifies root cause, opens a PR
5. (Optional) Webhook posts work notes back to ServiceNow with session URL and PR link

## Files

| File | Purpose |
|------|---------|
| `template.yaml` | CloudFormation template — Lambda + API Gateway + IAM |
| `lambda_handler.py` | Lambda function code — webhook receiver + Devin session creation |
| `deploy.sh` | One-command deployment script |
| `webhook_receiver.py` | Standalone Flask version (for local dev / Docker) |
| `Dockerfile` | Container build for the Flask version |
| `requirements.txt` | Python dependencies for the Flask version |

## Quick Start

### 1. Deploy to AWS

```bash
cd integrations/servicenow

# Interactive (prompts for secrets):
./deploy.sh

# Non-interactive:
./deploy.sh \
  --devin-api-key "YOUR_DEVIN_API_KEY" \
  --devin-org-id "YOUR_DEVIN_ORG_ID" \
  --snow-secret "your-shared-secret" \
  --snow-instance "https://yourinstance.service-now.com" \
  --snow-client-id "YOUR_SNOW_CLIENT_ID" \
  --snow-client-secret "YOUR_SNOW_CLIENT_SECRET"
```

The script outputs the API Gateway URL — copy it for the next step.

### 2. Configure ServiceNow

See [SERVICENOW_SETUP.md](./SERVICENOW_SETUP.md) for step-by-step instructions.

### 3. Test

Create an incident in ServiceNow with Category=Software and Priority=1-Critical. The Business Rule fires the webhook, and a Devin session should appear within seconds.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/admin/servicenow/ingest` | Receive ServiceNow incident webhook |
| `POST` | `/api/v1/admin/servicenow/resolve` | Resolve incident + update ServiceNow |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEVIN_API_KEY` | Yes | Devin v3 API bearer token |
| `DEVIN_ORG_ID` | Yes | Devin organization ID |
| `SERVICENOW_WEBHOOK_SECRET` | Recommended | Shared secret for `X-ServiceNow-Secret` header |
| `SERVICENOW_INSTANCE_URL` | Optional | Instance URL for callbacks |
| `SERVICENOW_CLIENT_ID` | Optional | OAuth 2.0 client ID for callbacks |
| `SERVICENOW_CLIENT_SECRET` | Optional | OAuth 2.0 client secret for callbacks |

## Teardown

```bash
aws cloudformation delete-stack --stack-name otterworks-servicenow-webhook --region us-east-1
```
