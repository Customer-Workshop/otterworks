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
2. Read the bucket name out of the error. `upload to bucket <name> failed: ... NoSuchBucket`
   tells you exactly which bucket the service tried to write to.
3. Compare it with the configured bucket and confirm that bucket exists:
   ```
   kubectl get configmap file-service-config -n otterworks -o jsonpath='{.data.S3_BUCKET}'
   aws s3api head-bucket --bucket "$S3_BUCKET"
   ```
4. If the bucket in the error differs from `S3_BUCKET`, something between config and the S3
   call is rewriting it (a chaos/fault-injection hook, a stale image). Check
   `kubectl -n otterworks describe deploy/file-service` for the running image tag and the
   Helm release history (`helm history file-service -n otterworks`) for a recent
   `config.S3_BUCKET` override.

## Resolution Steps

- **Misconfigured `S3_BUCKET`:** re-run `scripts/deploy-dev.sh` (or `deploy-tenant.sh <ID>`
  for a tenant) so the ConfigMap is regenerated from Terraform outputs, then
  `kubectl -n otterworks rollout restart deploy/file-service`.
- **Bucket deleted/renamed by an infra change:** restore the bucket via Terraform
  (`infrastructure/terraform`) or point `S3_BUCKET` at the replacement; existing metadata in
  DynamoDB references keys in the old bucket, so migrate objects before repointing.
- **Chaos flag set:** `redis-cli DEL chaos:file-service:upload_s3_error` on the affected
  Redis. Note that this flag only has an effect on images that still contain the
  fault-injection hook in `upload_file`; current builds always write to `S3_BUCKET`.
- Confirm recovery: `FileUploadHighErrorRate` should resolve within ~1 minute; verify with a
  manual upload through the web app.

## Post-Incident

- Record which of the above causes applied and how long uploads were failing.
- If the cause was a config override, add a pre-deploy check that `head-bucket` succeeds for
  the configured `S3_BUCKET`.
