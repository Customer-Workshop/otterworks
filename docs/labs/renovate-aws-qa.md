# Renovate-style dependency PR and backend QA demo

This branch is a **synthetic Renovate-style PR** for CVE-2022-42889. It updates
`commons-text` from 1.9 to 1.10.0 in report-service and notification-service,
and pins the safe version in legacy-portal, where it otherwise arrives through
`commons-configuration2`. The vulnerable `main` branch and the recorded
behavior cases remain available for the next workshop.

## Run the dependency review

On `main`, run `make deps-inventory`, `make deps-tests`, and
`make deps-transcript-baseline` to capture the before-state. On this branch,
run `make deps-inventory`, `make deps-gate`, `make deps-tests`, and
`make deps-transcript`. Each command writes a gitignored JSON report under
`security/deps/reports/`. A nonzero exit or an unmeasured module is **not a
pass**. Compare the dependency tree and behavior transcripts, then review CI.
Do not merge this workshop branch into the golden `main`.

## Inspect an actual deployment (read-only)

These commands query existing resources; they do not deploy or change them.
Only run tenant commands against an explicitly assigned tenant namespace, never
against `t-main` or another attendee's workload. Record the output and UTC
time (`date -u +%FT%TZ`) with each check. Set `EXPECTED_SHA` to the PR head
commit, `CONTEXT` to the approved EKS context, `NAMESPACE` to the approved
tenant namespace, and `DEPLOYMENT` to the service being checked. Confirm the
context and namespace before querying pods:

```sh
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}'
aws eks describe-cluster --name otterworks-dev --region us-east-1 \
  --query 'cluster.{name:name,status:status,version:version}'
kubectl config current-context
kubectl --context "$CONTEXT" get namespace "$NAMESPACE"
kubectl --context "$CONTEXT" -n "$NAMESPACE" get deployment "$DEPLOYMENT" -o json
kubectl --context "$CONTEXT" -n "$NAMESPACE" get pods -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" describe deployment "$DEPLOYMENT"
kubectl --context "$CONTEXT" -n "$NAMESPACE" logs "deployment/$DEPLOYMENT" \
  --all-pods=true --all-containers=true --since=15m --tail=100 --prefix=true
```

Check desired versus ready replicas, pod conditions, restart counts, deployment
events, image digest/tag, and logs. Identify which image or deployment annotation
maps to `EXPECTED_SHA`; a healthy cluster or green CI does not prove that SHA is
running. If the mapping is absent, report the rollout as **unverified**. A
pre-existing fault in another tenant (including the golden app's planted
admin-service bug) is not evidence about this PR. Redact secrets and personal
data before sharing logs.

If the assigned staging tenant has a safe health endpoint, run
`curl --fail --silent --show-error --max-time 10 "$STAGING_HEALTH_URL"` and
record the response code, UTC time, and the deployed revision. Do not call
write endpoints. Without a deployed `EXPECTED_SHA` and an endpoint associated
with that deployment, the API check is **unverified**.

CloudFormation, Lambda, and Argo CD are **not** the live deployment path for
OtterWorks: its infrastructure uses Terraform, its services run on EKS with
Helm, and the current deployment has no Argo CD controller. If another
**explicitly assigned** service does use those systems, collect read-only
evidence with `aws cloudformation describe-stacks`,
`aws cloudformation describe-stack-events`,
`aws lambda get-function-configuration`,
`aws logs filter-log-events`, and an Argo application status query. Match the
stack/function/application and its revision to that service's PR before
reporting a pass. Do not select an unrelated resource merely because it is
visible in the demo AWS account.

## Synthetic walkthrough (invented evidence, never a live result)

Use this sample when the meeting has no isolated staging deployment. Every
value below is invented; the example revision `demo-1234567` does not refer to
an OtterWorks commit. Pretend the following observations were collected at
`2026-09-23T12:00:00Z` for a fictional service:

| Check | Invented observation | Verdict |
| --- | --- | --- |
| CloudFormation | `qa-demo-stack` is `UPDATE_COMPLETE`; stack output has no revision | **unverified** for this PR |
| Lambda | `qa-demo-function` reports `LastUpdateStatus=Successful`, version `12`, and revision `demo-1234567` | **pass** in this simulation |
| CloudWatch | No log window supplied | **unverified** |
| Argo CD | `qa-demo-app` reports `OutOfSync`, revision `demo-0000000` | **fail** |
| Kubernetes | `qa-demo-app` has 1 ready replica out of 2 desired; pod restarts: 3 | **fail** |
| API | Health endpoint not called | **unverified** |

For the actual OtterWorks PR, report CloudFormation and Lambda as **not
applicable** and Argo CD as **unavailable**. Report EKS rollout, pod logs, and
API as **unverified** until the PR's image is deployed to an assigned tenant.
Give each actual check a source, UTC timestamp, observed revision, expected
revision, pass/fail/unverified verdict, and the next action. A simulated pass
never changes the live verdict.
