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

3. Confirm the bucket file-service is configured for exists and matches Terraform:
   ```
   kubectl get deploy file-service -n otterworks -o jsonpath='{.spec.template.spec.containers[0].env}' | grep -o '"S3_BUCKET"[^}]*'
   terraform -chdir=infrastructure/terraform output -raw s3_file_bucket
   aws s3api head-bucket --bucket <S3_BUCKET>
   ```
   file-service also logs `S3 bucket check failed` at startup when the configured bucket is unreachable.

## Resolution Steps

- If the chaos flag is set, clear it: `scripts/inject-bug.sh <TENANT_ID> reset` (or `redis-cli DEL chaos:file-service:upload_s3_error`).
- If `S3_BUCKET` does not match the Terraform output, redeploy with the correct value
  (`scripts/deploy-dev.sh` / `scripts/deploy-tenant.sh` wire it from `s3_file_bucket`) and
  `kubectl rollout restart deploy/file-service -n otterworks`.
- Verify recovery: `FileUploadHighErrorRate` clears and an upload via the web app succeeds.

## Post-Incident

- Note whether the trigger was a chaos flag, a config drift, or a real infra change to the bucket.
- If config drift, add a check to the deploy pipeline that compares `S3_BUCKET` against Terraform output.
