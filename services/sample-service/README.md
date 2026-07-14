# Sample Service

Minimal CRUD reference microservice for OtterWorks, built with Python 3.12 / FastAPI.

It manages a simple owned `samples` resource (`items`) and mirrors the structure and
conventions of the `document-service` (routing, header/JWT-based auth, inline
`HTTPException` error handling, SQLAlchemy async persistence, pytest + `httpx.AsyncClient`
tests). It is intended as a starting point for new Python services on the platform.

## API

Routed through the API gateway at `/api/v1/samples` (service port `8092`).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/samples/` | Create an item |
| GET | `/api/v1/samples/` | List items (paginated) |
| GET | `/api/v1/samples/{id}` | Get an item by ID |
| PUT | `/api/v1/samples/{id}` | Full replace |
| PATCH | `/api/v1/samples/{id}` | Partial update |
| DELETE | `/api/v1/samples/{id}` | Soft delete |
| GET | `/health` | Health check (DB connectivity) |
| GET | `/metrics` | Prometheus metrics |

## Auth

Ownership is derived from a JWT `Authorization: Bearer <token>` header. When no
`JWT_SECRET` is configured, the service trusts the `X-User-ID` header injected by the
api-gateway (mirrors `document-service`).

## Development

```bash
poetry install
poetry run ruff check .
poetry run pytest --cov=app
```
