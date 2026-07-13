# Report Service Lambda (`lam1`)

This standalone Terraform module provisions an isolated report-service Lambda
deployment in the default VPC in `us-east-2`. It has no backend configuration
and uses local Terraform state. It does not read or modify the shared
`infrastructure/terraform` root module.

## Prerequisites

Build the flat Lambda JAR first:

```bash
cd services/report-service
mvn -q -DskipTests -Plambda package
```

The AWS credentials must have permission to create the Lambda, API Gateway,
IAM, CloudWatch Logs, security groups, subnet groups, S3 (deployment artifact),
Secrets Manager, RDS, and RDS Proxy resources.

Connections go Lambda -> RDS Proxy -> RDS so that many short-lived Lambda
environments share a bounded pool of PostgreSQL connections. Reserved and
provisioned concurrency default to 8 and 3 (see `variables.tf`).

## Plan and apply

From this directory:

```bash
terraform init
terraform plan \
  -var 'db_password=replace-with-a-strong-password' \
  -var 'lambda_jar_path=../../../services/report-service/target/report-service-lambda.jar'
terraform apply \
  -var 'db_password=replace-with-a-strong-password' \
  -var 'lambda_jar_path=../../../services/report-service/target/report-service-lambda.jar'
```

The API Gateway HTTP API uses the `$default` stage, so `api_endpoint` has no
stage path segment.

## Revert

To remove every resource managed by this isolated module:

```bash
terraform destroy \
  -var 'db_password=replace-with-a-strong-password' \
  -var 'lambda_jar_path=../../../services/report-service/target/report-service-lambda.jar'
```
