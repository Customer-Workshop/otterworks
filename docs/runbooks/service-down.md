# Runbook: Service Down

**Severity:** Critical

## Alert

`ServiceDown` -- fires when a service's health check endpoint (`up` metric) reports 0 for more than 1 minute.

## Symptoms

- The affected service tile turns red on the OtterWorks Overview dashboard.
- Dependent services return 502/503 errors when routing requests to the downed service.
- Health check endpoint returns non-200 or times out.

## Investigation Steps

1. Check pod status for the affected service:
   ```
   kubectl get pods -l app=<service> -n otterworks
   ```
2. Review pod events and recent restarts:
   ```
   kubectl describe pod <pod-name> -n otterworks
   ```

<!-- TODO: Complete investigation steps -->

## Resolution Steps

<!-- TODO -->

## Post-Incident

<!-- TODO -->
