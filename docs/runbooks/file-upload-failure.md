# Runbook: File Upload Failures

**Severity:** High

## Alert

`FileUploadHighErrorRate` -- fires when file-service 5xx rate exceeds 10% over a 1-minute window.

## Symptoms

- Users cannot upload files; the UI shows generic upload error messages.
- The Chaos Scenarios dashboard shows elevated error rates on the file-service panel.
- Application logs contain `NoSuchBucket` errors from the AWS S3 SDK.

## Investigation Steps

1. Confirm the error in file-service logs:
   ```
   kubectl logs -l app=file-service --tail=100 -n otterworks | grep -i "NoSuchBucket\|S3\|500"
   ```
   The log line includes the bucket the upload targeted. If it is
   `otterworks-files-chaos-nonexistent`, the fault-injection path is active (step 2).
   Any other name means the configured bucket itself is wrong or missing (step 3).
2. Check whether the chaos flag `chaos:file-service:upload_s3_error` is set in Redis:
   ```
   redis-cli EXISTS chaos:file-service:upload_s3_error
   ```
   The flag only has an effect when the pod runs with `CHAOS_ENABLED=true`:
   ```
   kubectl -n otterworks get deploy file-service -o jsonpath='{.spec.template.spec.containers[0].env}'
   kubectl -n otterworks get configmap file-service-config -o yaml
   ```
3. Check the configured bucket and confirm it exists:
   ```
   kubectl -n otterworks get configmap file-service-config -o jsonpath='{.data.S3_BUCKET}'
   aws s3api head-bucket --bucket "$(terraform -chdir=infrastructure/terraform output -raw s3_file_bucket)"
   ```
   file-service also runs this check at startup and logs
   `S3 bucket check failed` with the bucket name if it is unreachable.
4. Review recent changes to `infrastructure/helm/file-service`, `scripts/deploy-dev.sh`
   (`S3_FILE_BUCKET`) and any `helm upgrade ... --set config.S3_BUCKET=...` in the
   release history (`helm history file-service -n otterworks`).

## Resolution Steps

- **Chaos flag active:** clear it and confirm uploads recover.
  ```
  redis-cli DEL chaos:file-service:upload_s3_error
  # or, per tenant:
  ./scripts/inject-bug.sh <ATTENDEE_ID> reset
  ```
  If the environment should never honour chaos flags, ensure `CHAOS_ENABLED` is unset or
  `false` in the file-service ConfigMap.
- **Bucket misconfigured:** redeploy with the correct bucket, which resets any manual override.
  ```
  ./scripts/deploy-dev.sh            # golden environment
  ./scripts/deploy-tenant.sh <ATTENDEE_ID>
  ```
  or, for an immediate fix, `helm upgrade file-service infrastructure/helm/file-service
  -n otterworks --reuse-values --set-string config.S3_BUCKET=<correct-bucket>` followed by
  `kubectl -n otterworks rollout restart deploy/file-service`.
- **Bucket missing:** re-apply Terraform (`infrastructure/terraform`) so the bucket exists,
  then restart file-service.
- Verify: upload a file through the web app or
  `curl -F file=@README.md -F owner_id=<uuid> http://<api>/api/v1/files/upload` returns 201,
  and the `FileUploadHighErrorRate` alert resolves within one evaluation window.

## Post-Incident

- Record the trigger (chaos flag vs. config change) and how long uploads were failing.
- If a config override caused it, link the `helm history` revision and the change that
  introduced it.
- Reset any tenant used for a demo with `./scripts/inject-bug.sh <ATTENDEE_ID> reset` so the
  flag does not resurface after the incident is closed.
