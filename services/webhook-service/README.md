# Webhook Service

The headless Go/Chi outbound partner webhook service owns subscriptions, consumes
domain events from SQS, and retries signed JSON deliveries. It listens on port
8092; the copy-paste demo sink listens on 8093.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8092` | HTTP port |
| `DATABASE_URL` | built from `POSTGRES_*` | Shared Postgres connection |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ENDPOINT_URL` | empty | LocalStack/custom endpoint |
| `SQS_QUEUE_URL` | LocalStack webhook queue | Event queue |
| `SQS_ENABLED` | `true` | Enable event consumer |
| `SQS_WAIT_TIME_SECONDS` | `10` | Long poll duration |
| `DELIVERY_MAX_ATTEMPTS` | `5` | Retry limit |
| `DELIVERY_BASE_BACKOFF` | `2s` | Exponential retry base |
| `DELIVERY_TIMEOUT` | `5s` | Partner request timeout |
| `WORKER_POLL_INTERVAL` | `1s` | Delivery worker cadence |

Events map `file_shared` → `file.shared`, `document_updated` → `document.updated`,
and `comment_added` → `comment.added`. Unknown events are acknowledged and ignored.

## Verifying signatures

```bash
signature=$(printf '%s.%s' "$TIMESTAMP" "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')
test "sha256=$signature" = "$X_OTTERWORKS_SIGNATURE"
```

```go
mac := hmac.New(sha256.New, []byte(secret))
fmt.Fprintf(mac, "%d.%s", timestamp, body)
valid := hmac.Equal([]byte("sha256="+hex.EncodeToString(mac.Sum(nil))), []byte(header))
```

Retries wait 2, 4, 8, and 16 seconds after failed attempts; the fifth failure
dead-letters the delivery with status `failed`.

## Local demo

Start the stack with `make up`, then run `scripts/demo-webhooks.sh`. The demo
first tries `EMAIL`/`PASSWORD` (defaulting to `admin@otterworks.dev` /
`Admin123!`). If that account cannot log in, it registers and uses
`webhook-demo@otterworks.dev` with display name `Webhook Demo`, then prints the
account used. It registers a unique partner by default, creates a subscription,
verifies a ping and file-sharing event, and exercises fail-mode retries using
`webhook-sink`.

## Headless guarantees

All routes return JSON, reject an explicit HTML-only `Accept` header with 406,
strip `Set-Cookie`, and provide JSON 404/405 handlers. No templates, static
assets, or browser UI are part of this service.
