# Shared OpenAPI Specifications

This directory contains shared OpenAPI 3.0 specifications that define
the contracts between services.

Each service also maintains its own OpenAPI spec in its source directory.
Shared specs here define cross-service models and common response formats.

## Common Models

- `ErrorResponse` - Standard error response format (RFC 7807)
- `PaginatedResponse` - Standard pagination wrapper
- `HealthResponse` - Health check response format
- `AuditEvent` - Cross-service audit event structure
