# Billing Service

This FastAPI service is the extraction target for the plans module. It owns a
separate Postgres `billing_svc` schema, keeps the HTTP layer thin, and places
plans behavior in a plain-Python domain layer.

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8097
uv run pytest
uv run ruff check app scripts tests
```

The deterministic target seed is generated from
`services/legacy-billing/db/seed.sql`:

```bash
python scripts/generate_seed.py
```

The generated-seed test prevents the target fixture from drifting from the
legacy before-state. `POST /internal/reset` applies the migration, truncates
the `billing_svc` schema, and reseeds it so the parity harness can isolate
every scenario.

The reset endpoint is disabled by default. Disposable local/CI Compose stacks
enable it with `BILLING_SVC_ALLOW_INTERNAL_RESET=true`; published deployments
should leave the setting disabled.

The tenant endpoints (`/api/tenants/{tenant_id}/...`) and `/internal/reset`
require an `Authorization: Bearer <token>` credential that the service verifies
itself. Forwarded identity headers such as `X-User-ID` are never trusted.

- Internal callers (the parity harness, operator jobs) send the shared
  `BILLING_SVC_SERVICE_TOKEN` and may act on any tenant. The token is unset by
  default, which disables this path entirely.
- Users send the platform access JWT issued by auth-service. The service checks
  the signature with `BILLING_SVC_JWT_SECRET` (the platform `JWT_SECRET`) and
  then requires a `billing_svc.tenant_members` row linking the token's `sub` to
  the path `tenant_id`; anything else is refused with 403. Unset
  `BILLING_SVC_JWT_SECRET` disables the user path. The local fixture seeds no
  memberships, so user tokens only work once a deployment provisions them.

Requests without a valid credential get 401. The disposable Compose stack and
the harness share a local development token; override it with
`BILLING_SVC_TOKEN` when running `make procs-up` / `make procs-parity`.

For the extracted target, a plan change with an already-scheduled later
subscription preserves that later row. The response's `latest_*` fields always
identify the subscription created by the request, rather than relying on row
ordering.

The legacy procedure attempts a second insert for an identical plan change and
therefore relies on the database uniqueness error. The extracted target returns
HTTP 409 with an explicit conflict detail instead of leaking a 500; this is
target-side error handling, not an additional parity rule.

When using the workshop client with the default disposable stack, the Vite
development proxy forwards `/billing-api/*` to the service on port `12109` and
attaches `BILLING_SERVICE_TOKEN` as the bearer credential when that variable is
set (use the stack's `BILLING_SVC_SERVICE_TOKEN` value).
The billing screens are part of this local parity fixture only. Vite dev
enables their routes by default; a preview requires building with
`VITE_ENABLE_BILLING_FIXTURE=true` and then running `npm run start`. The
`/billing-api` proxy is used by the dev server and by that explicitly flagged
preview. Builds without the flag leave the routes unregistered. No deployed
app or shared-infrastructure deployment is provided for this fixture.
