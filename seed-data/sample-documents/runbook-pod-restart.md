# Runbook: Otter Pod Restart Procedure

| Field | Value |
|-------|-------|
| **Owner** | Dam Sanfilippo (The Burrow) |
| **Last Updated** | 2026-04-10 |
| **Severity** | P2-P3 |
| **Estimated Duration** | 5-15 minutes per service |

## When to Use

- Service is in a degraded state (high latency, memory leak, stuck connections)
- After deploying a hotfix that requires a restart
- Health check is failing but the underlying issue is transient

## Pre-Checks

1. **Verify the issue isn't cluster-wide**
   ```bash
   kubectl get nodes -o wide
   kubectl top nodes
   ```

2. **Check current pod status**
   ```bash
   kubectl get pods -n otterworks -l app=<service-name>
   kubectl describe pod <pod-name> -n otterworks
   ```

3. **Check recent logs for the root cause**
   ```bash
   kubectl logs <pod-name> -n otterworks --tail=100
   ```

4. **Notify the team**
   Post in #tide-watchers: "Restarting <service-name> pods. Reason: <brief description>"

## Restart Procedure

### Stateless Services (Preferred: Rolling Restart)

For: api-gateway, auth-service, search-service, notification-service, admin-service, audit-service, report-service

```bash
kubectl rollout restart deployment/<service-name> -n otterworks
kubectl rollout status deployment/<service-name> -n otterworks --timeout=300s
```

### Stateful Services (Requires Extra Care)

#### collab-service
Active WebSocket connections will be dropped. Users will auto-reconnect.

```bash
# Check active collaboration sessions
kubectl exec -it <collab-pod> -n otterworks -- curl localhost:8084/health/sessions

# Graceful shutdown (allows 30s drain)
kubectl rollout restart deployment/collab-service -n otterworks
```

#### document-service
In-flight document saves may be interrupted. The CRDT persistence loop ensures no data loss (last flush < 500ms ago).

```bash
# Verify no active write transactions
kubectl exec -it <doc-pod> -n otterworks -- curl localhost:8083/health/active-writes

# Restart
kubectl rollout restart deployment/document-service -n otterworks
```

## Post-Restart Validation

1. **Health check**
   ```bash
   kubectl get pods -n otterworks -l app=<service-name>
   # All pods should be Running and Ready
   ```

2. **Service health endpoint**
   ```bash
   curl http://localhost:8080/api/v1/<service>/health
   ```

3. **Check Grafana dashboard**
   Open http://localhost:3001 → OtterWorks Overview dashboard
   Verify: request rate recovered, error rate dropped, latency normalized

## Rollback

If the restart makes things worse:

```bash
kubectl rollout undo deployment/<service-name> -n otterworks
```

## Escalation

If the restart doesn't resolve the issue after 2 attempts, escalate to the service owner (see org-structure.yaml) and page the on-call engineer via PagerDuty.
