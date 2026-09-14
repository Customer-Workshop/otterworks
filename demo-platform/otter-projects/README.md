# Otter Projects

A minimal, real issue tracker (a tiny Jira) whose one job is to demonstrate
**automated ticket-to-Devin assignment** in workshops without a Jira license:

```
ticket gets label `devin` / assignee `devin`  ──▶  Otter Projects dispatches
   ├─ webhook   → Devin Automation (webhook trigger) → Devin session
   └─ devin-api → POST /v3/organizations/{org}/sessions → Devin session
Devin progress (status, messages, PR)  ──▶  POST /api/webhooks/devin  (+ 60s poller)
   └─ Devin comments / activity / PR link / column moves on the board
```

Live: <https://projects.otterworks.app> (passcode-protected). Docs:
[docs/api.md](docs/api.md) · [docs/devin-automation.md](docs/devin-automation.md).

## Local development (no AWS)

```bash
cd demo-platform/otter-projects
npm install
cp .env.example .env.local        # LOCAL_MODE=true, pick a passcode/API key
npm run dev                       # http://localhost:3000
npm run seed                      # LOCAL_MODE=true: seeds OTTER + ~10 tickets into the JSON file
npm test && npm run lint && npm run typecheck
```

`LOCAL_MODE=true` uses a JSON file (`LOCAL_STORE_PATH`) or memory instead of
DynamoDB. Restart `npm run dev` after seeding so the server reloads the file.

## Layout

| Path | What |
|------|------|
| `app/` | Next.js App Router pages + `app/api/**` route handlers |
| `components/` | Board (dnd-kit), ticket drawer with Devin panel, project settings |
| `lib/` | `service.ts` (domain logic + triggers), `dispatch.ts` (webhook / devin-api), `devin.ts` (v3 API client), `poller.ts`, `store/` (local + DynamoDB), `auth.ts`, `hmac.ts` |
| `scripts/seed.ts` | Seeds project `OTTER` (repo `Cognition-Partner-Workshops/otterworks`) |
| `scripts/deploy-otter-projects.sh` | ECR build/push → Terraform → `helm upgrade --install` |
| `infra/terraform/` | DynamoDB table `otterworks-projects` + IRSA role scoped to it |
| `helm/otter-projects/` | Deployment, ClusterIP Service, Ingress, NetworkPolicy, SA (IRSA), Secret, poller CronJob |
| `tests/` | Vitest: store, HMAC, dispatchers (mocked fetch), inbound webhook handler |

## Deploy

```bash
export AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=… AWS_REGION=us-east-1
AWS_ACCOUNT_ID=<12 digits> SEED=true ./scripts/deploy-otter-projects.sh
```

The account id is never committed — it is passed via env/`--set-string`.
Secrets (passcode, API key, session + webhook secrets) are generated on first
run into `~/.otter-projects/secrets.<cluster>.yaml` and only exist there and in
the Kubernetes Secret. The Service is `ClusterIP` behind the shared
ingress-nginx; TLS/DNS come from the platform's wildcard cert-manager /
external-dns setup.
