# Incident: ow-tp-portal-demo-api-5xx (2026-08-18)

## Summary
CloudWatch alarm `ow-tp-portal-demo-api-5xx` (5xx on API Gateway `g2rqbb7uw6`, stage `$default`) fired at 05:03:45 UTC. The feedback Lambda's `live` alias had been repointed to a broken published version (v12) whose environment carried `CHAOS_FAULT=invoke-error`, causing every invocation to throw `java.lang.IllegalStateException` and surface as HTTP 500 at the gateway. Remediated by repointing the alias to the last known-good version (v11).

## Timeline (UTC, 2026-08-18)
- 04:42 — version 10 published with description "chaos invoke-error (blast radius rehearsal)" (`CHAOS_FAULT=invoke-error`)
- 04:44–04:58 — alarm flapped ALARM/OK twice (earlier chaos exercise against v10)
- 04:50 / 04:54 — "canary" versions 11 (clean env) and 12 (`CHAOS_FAULT=invoke-error`) published
- ~05:02 — `live` alias serving v12; 5xx count reached 10/min (18–24 Lambda errors/min on `ow-tp-portal-demo-feedback`)
- 05:03:45 — alarm transitioned OK → ALARM (threshold ≥1, datapoint 10.0)
- 05:07 — remediation: `live` alias repointed v12 → v11
- 05:08 — API Gateway feedback endpoints returning 200; alarm returned to OK shortly after

## Root cause
The `live` alias of `ow-tp-portal-demo-feedback` pointed at published version 12, which was built with the chaos-injection environment variable `CHAOS_FAULT=invoke-error`. The shared handler (`com.otterworks.portal.common.ApiHandler.failIfChaosConfigured`) throws `IllegalStateException: CHAOS_FAULT=invoke-error: injected invocation fault` on every request, producing 5xx at the API Gateway. Version 11 (published 04:50, identical code path but a clean environment: only `TABLE_NAME` and `EVENT_BUS_NAME`) was the last known-good version. The other two Lambdas (announcements, preferences) showed zero errors in the window; no infrastructure change was involved.

## Remediation
Configuration-level fix only (no `terraform apply`, no shared infrastructure touched):

```
aws lambda update-alias \
  --function-name ow-tp-portal-demo-feedback \
  --name live --function-version 11 --routing-config '{}'
```

(Previous alias state: FunctionVersion 12, no weighted routing.)

## Verification
- `GET /api/feedback?userId=<id>` via `https://g2rqbb7uw6.execute-api.us-east-1.amazonaws.com` with the portal bearer token: 5/5 responses `200`.
- `GET /api/feedback/average-rating`: `200`, body `{"averageRating":4.0}`.
- CloudWatch Logs show requests served by Version 11 with no exceptions.
- Alarm `ow-tp-portal-demo-api-5xx` returned to `OK` after the evaluation window cleared.

## Follow-up
- Chaos-rehearsal versions (v10, v12) remain published but unaliased; consider deleting them or gating `CHAOS_FAULT` builds away from the `live` alias promotion path.
