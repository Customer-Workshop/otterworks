# Runbook: High Latency

**Severity:** Warning / Critical

## Alert

`HighLatencyP95` -- fires when P95 latency exceeds 1s (warning) or `HighLatencyP99` when P99 exceeds 2s (critical) on any service.

## Symptoms

- Users report slow page loads or API timeouts.
- P95/P99 latency panels on the Incident Overview dashboard show sustained elevation.
- Upstream services may start returning 504 Gateway Timeout errors.

## Investigation Steps

1. Open the **Incident Overview** dashboard and identify which service has elevated P95/P99 latency.
2. Check Jaeger traces for the affected service to find slow spans:
   ```
   Open Jaeger UI → Search → Service: <service> → Min Duration: 2s
   ```

<!-- TODO: Complete investigation steps -->

## Resolution Steps

<!-- TODO -->

## Post-Incident

<!-- TODO -->
