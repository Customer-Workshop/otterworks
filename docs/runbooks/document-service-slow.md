# Runbook: Document Service Slow Queries

**Severity:** High

## Alert

`DocumentServiceHighLatency` -- fires when document-service P95 latency exceeds 3s over a 1-minute window.

## Symptoms

- Document CRUD operations take 3-5 seconds instead of the usual sub-second response times.
- The Incident Overview dashboard shows elevated P95 latency on the document-service panel.
- Upstream timeouts may cascade to the web app, causing loading spinners or error messages.

## Investigation Steps

1. Check Jaeger traces for document-service requests with high duration:
   ```
   Open Jaeger UI → Search → Service: document-service → Min Duration: 3s
   ```
2. Check whether the chaos flag `chaos:document-service:slow_queries` is set in Redis:
   ```
   redis-cli EXISTS chaos:document-service:slow_queries
   ```

<!-- TODO: Complete investigation steps -->

## Resolution Steps

<!-- TODO -->

## Post-Incident

<!-- TODO -->
