FROM golang:1.25-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/server ./cmd/server

FROM alpine:3.19
RUN apk --no-cache add ca-certificates wget
WORKDIR /app
COPY --from=builder /bin/server /app/server
RUN adduser -D -u 1001 appuser
USER appuser
EXPOSE 8092
HEALTHCHECK --interval=10s --timeout=3s CMD wget --spider -q http://localhost:8092/health || exit 1
ENTRYPOINT ["/app/server"]
