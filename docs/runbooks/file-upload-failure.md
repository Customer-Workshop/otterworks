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
2. Check whether the chaos flag `chaos:file-service:upload_s3_error` is set in Redis:
   ```
   redis-cli EXISTS chaos:file-service:upload_s3_error
   ```

3. Confirm the bucket the service is configured for and that it exists:
   ```
   kubectl get configmap file-service-config -n otterworks -o jsonpath='{.data.S3_BUCKET}'
   aws s3api head-bucket --bucket <value>
   ```
   file-service also runs this check on startup and logs
   `Configured S3 bucket is not reachable; check S3_BUCKET` if it fails.
4. Check for recent Helm releases or config overrides on file-service:
   ```
   helm history file-service -n otterworks
   ```

## Resolution Steps

- Wrong `S3_BUCKET` value: redeploy with the correct value (`scripts/deploy-tenant.sh <ID>`
  re-applies the bucket from Terraform outputs) and `kubectl rollout restart deploy/file-service`.
- Chaos flag set: `redis-cli DEL chaos:file-service:upload_s3_error` (or
  `scripts/inject-bug.sh <ID> reset`).
- Verify: upload a file through the web app and confirm the `FileUploadHighErrorRate`
  alert clears within a few minutes.

## Post-Incident

<!-- TODO -->
