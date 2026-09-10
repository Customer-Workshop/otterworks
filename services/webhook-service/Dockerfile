FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/server ./cmd/server \
 && CGO_ENABLED=0 GOOS=linux go build -o /bin/sink ./cmd/sink

# Headless demo receiver (docker-compose `webhook-sink`).
FROM alpine:3.19 AS sink
RUN apk --no-cache add ca-certificates wget && adduser -D -u 1001 appuser
COPY --from=builder /bin/sink /app/sink
USER appuser
EXPOSE 8093
HEALTHCHECK --interval=10s --timeout=3s CMD wget --spider -q http://localhost:8093/health || exit 1
ENTRYPOINT ["/app/sink"]

# The service itself (default target). No static assets, no templates: the
# image contains exactly one binary.
FROM alpine:3.19
RUN apk --no-cache add ca-certificates wget && adduser -D -u 1001 appuser
WORKDIR /app
COPY --from=builder /bin/server /app/server
USER appuser

EXPOSE 8092
HEALTHCHECK --interval=10s --timeout=3s CMD wget --spider -q http://localhost:8092/health || exit 1
ENTRYPOINT ["/app/server"]
