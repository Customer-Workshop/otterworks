# OtterWorks Standardized Log Format

All OtterWorks services MUST emit structured JSON logs that conform to the
schema below. This ensures consistent parsing by Fluent Bit and enables
cross-service log correlation in CloudWatch / Loki.

## Required Fields

| Field         | Type   | Description                                      | Example                                |
|---------------|--------|--------------------------------------------------|----------------------------------------|
| `timestamp`   | string | ISO-8601 UTC timestamp with milliseconds         | `2026-01-15T14:30:00.123Z`            |
| `level`       | string | Log severity: `DEBUG`, `INFO`, `WARN`, `ERROR`   | `INFO`                                 |
| `service`     | string | Service name (must match Prometheus job name)     | `document-service`                     |
| `message`     | string | Human-readable log message                        | `Document created successfully`        |

## Recommended Fields

| Field         | Type   | Description                                      | Example                                |
|---------------|--------|--------------------------------------------------|----------------------------------------|
| `trace_id`    | string | OpenTelemetry trace ID for correlation            | `abc123def456...`                      |
| `span_id`     | string | OpenTelemetry span ID                             | `0123456789abcdef`                     |
| `request_id`  | string | Unique request identifier                         | `req-a1b2c3d4`                         |
| `user_id`     | string | Authenticated user identifier (omit if anonymous) | `usr-12345`                            |
| `method`      | string | HTTP method                                       | `POST`                                 |
| `path`        | string | Request path                                      | `/api/v1/documents`                    |
| `status`      | int    | HTTP response status code                         | `201`                                  |
| `duration_ms` | float  | Request duration in milliseconds                  | `42.5`                                 |
| `error`       | object | Error details (only when `level` is `ERROR`)      | `{"type": "NotFound", "stack": "..."}` |

## Example Log Entry

```json
{
  "timestamp": "2026-01-15T14:30:00.123Z",
  "level": "INFO",
  "service": "document-service",
  "message": "Document created successfully",
  "trace_id": "abc123def4567890abc123def4567890",
  "span_id": "0123456789abcdef",
  "request_id": "req-a1b2c3d4",
  "user_id": "usr-12345",
  "method": "POST",
  "path": "/api/v1/documents",
  "status": 201,
  "duration_ms": 42.5
}
```

## Error Log Entry

```json
{
  "timestamp": "2026-01-15T14:30:01.456Z",
  "level": "ERROR",
  "service": "file-service",
  "message": "Failed to upload file to S3",
  "trace_id": "def456abc1234567890def456abc1234",
  "span_id": "abcdef0123456789",
  "request_id": "req-e5f6g7h8",
  "user_id": "usr-67890",
  "method": "PUT",
  "path": "/api/v1/files/upload",
  "status": 500,
  "duration_ms": 1523.7,
  "error": {
    "type": "S3UploadException",
    "message": "Connection timed out to S3 bucket",
    "stack": "S3UploadException: Connection timed out..."
  }
}
```

## Language-Specific Implementation Notes

### Go (api-gateway, file-service)
Use `zerolog` or `zap` with JSON output. Set `zerolog.TimeFieldFormat` to
`time.RFC3339Nano`.

### Java / Kotlin / Scala (auth-service, analytics-service, admin-service)
Use Logback with `LogstashEncoder`. Add `<encoder class="net.logstash.logback.encoder.LogstashEncoder"/>` to `logback-spring.xml`.

### Rust (document-service)
Use `tracing` + `tracing-subscriber` with the `json` formatter.

### Python (notification-service)
Use `python-json-logger`. Configure via `logging.config.dictConfig`.

### Node.js (collab-service)
Use `pino` with default JSON output. Install `pino-opentelemetry-transport`
for automatic trace context injection.

### Ruby (search-service)
Use `semantic_logger` with JSON formatter, or `ougai` for structured logging.

### C# (audit-service)
Use `Serilog` with `Serilog.Formatting.Compact` for JSON output.

## Log Levels

| Level   | When to Use                                                        |
|---------|--------------------------------------------------------------------|
| `DEBUG` | Detailed diagnostic info; disabled in production                   |
| `INFO`  | Normal operations: requests served, tasks completed                |
| `WARN`  | Recoverable issues: retries, deprecated usage, approaching limits  |
| `ERROR` | Failures requiring attention: unhandled exceptions, downstream 5xx |

## Correlation

Every incoming HTTP request MUST propagate the `trace_id` from the
OpenTelemetry context into the log entry. This allows jumping from a log
line in CloudWatch/Loki directly to the corresponding trace in Jaeger.
