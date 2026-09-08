# Runbook: Critical API SLO alerts

**Severity:** Critical for `*BurnFast` / `*BurnMedium`, `CriticalApiNoTraffic` and
`CriticalApiProbeFailing`; warning for `*BurnSlow`, `*BurnVerySlow` and
`CriticalApiProbeSlow`.

## Alerts covered

| Alert | Meaning |
| --- | --- |
| `CriticalApiErrorBudgetBurnFast` | The endpoint is returning 5xx 14.4x faster than its 30d availability objective allows, over both the last 1h and the last 5m. Left alone it spends 2% of the 30-day budget every hour. |
| `CriticalApiErrorBudgetBurnMedium` | 6x burn confirmed over 6h and 30m. |
| `CriticalApiErrorBudgetBurnSlow` / `...VerySlow` | Slow leak. Not an outage; fix within the working day/week before the budget is gone. |
| `CriticalApiLatencyBudgetBurn*` | Same windows, but the SLI is the share of requests slower than the endpoint's latency threshold. |
| `CriticalApiNoTraffic` | An endpoint the catalog marks `expect_traffic: true` has served zero requests for 15 minutes. Burn-rate alerts cannot fire on an endpoint with no traffic, so this is the companion check. |
| `CriticalApiProbeFailing` / `CriticalApiProbeSlow` | The blackbox synthetic check against the gateway failed or exceeded its duration budget. Fires with no user traffic at all. |

Every alert carries `endpoint_id`, `backend`, `method`, `route`, `owner` and
`tier` labels, taken from `observability/slo/critical-apis.yaml`. `backend` is
the service the gateway proxied to; `service` on gateway series is the scrape
target (`api-gateway`).

## First five minutes

1. Open the **Critical API SLOs** dashboard (`critical-api-slo`) and read
   *Error budget remaining (30d)* for the endpoint in the alert. A budget near
   zero means the error is sustained, not a blip.
2. Decide the blast radius: is the fast burn on one endpoint, one service, or
   every endpoint at once?
   - One endpoint → suspect a recent deploy of that handler or a dependency it
     alone uses.
   - Every endpoint of one service → treat it as a service outage and continue
     in [service-down.md](service-down.md).
   - Every endpoint of every service → suspect the gateway, ingress or a shared
     dependency (RDS, Redis) rather than any single service.
3. Check the synthetic health probes. They call each service's own `/health`
   credential-free, so a failing probe means that service is down or
   unreachable; probes green while the burn rate is high points at a specific
   handler, payload or dependency rather than at the process being dead.

## Investigation

```bash
# Which status codes and which route, for the failing backend
sum by (status, route) (rate(api_gateway_http_requests_total{backend="<backend>"}[5m]))

# Latency distribution for the endpoint under alert
histogram_quantile(0.99, sum by (le) (
  rate(api_gateway_http_request_duration_seconds_bucket{route="<route>"}[5m])))

# Recent rollouts
kubectl rollout history deployment/<service> -n otterworks

# Service logs, filtered to the failing route
kubectl logs -l app=<service> --tail=500 -n otterworks | grep '<route>'
```

Correlate with traces in Jaeger (`service.name = <service>`) to find whether the
time is spent in the handler or in a downstream call.

## Resolution

- **Bad deploy** → `kubectl rollout undo deployment/<service> -n otterworks`.
  Confirm the fast-burn alert clears within two evaluation cycles.
- **Downstream dependency** → follow that dependency's runbook; the gateway
  circuit breaker will shed load meanwhile (`circuit breaker rejected request`
  in the gateway logs).
- **Genuine load** → scale the deployment, then review whether the objective in
  the catalog still reflects what the endpoint can sustain.
- **Alert is wrong** → do not silence it in Prometheus. Change the objective or
  the endpoint's tier in `observability/slo/critical-apis.yaml` and run
  `make slo-generate`, so the intent stays reviewable in git.

## Post-incident

- Record how much of the 30-day budget the incident consumed
  (`slo:api_error_budget:remaining_ratio` before and after).
- If the endpoint was not in the catalog when the incident started, add it.
- If detection came from a user report rather than an alert, work out which
  signal was missing and add it: a probe, an objective, or a new endpoint entry.
