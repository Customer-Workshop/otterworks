# Runbook: High Error Rate

**Severity:** Critical

## Alert

`HighErrorRate` -- fires when any service returns more than 5% server errors (5xx) over a 5-minute window.

## Symptoms

- Spike in 5xx responses visible on the OtterWorks Overview or Chaos Scenarios dashboard.
- Users report failures when performing actions (uploads, searches, document edits).
- On-call receives a PagerDuty / Grafana alert notification.

## Investigation Steps

1. Open the **Incident Overview** dashboard and identify which service(s) show elevated error rates.
2. Check the service's application logs for stack traces or error messages:
   ```
   kubectl logs -l app=<service> --tail=200 -n otterworks
   ```

<!-- TODO: Complete investigation steps -->

## Resolution Steps

<!-- TODO -->

## Post-Incident

<!-- TODO -->
