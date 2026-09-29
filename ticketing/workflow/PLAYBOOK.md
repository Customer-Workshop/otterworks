# Playbook: Ticketing modernization — run the whole program as one dynamic workflow

## Overview

A ticketing company's Jakarta EE monolith (synthetic, `ticketing/monolith/` in
`Cognition-Partner-Workshops/otterworks`) becomes event-driven services that scale from zero on
the shared Kubernetes cluster. This session is the **orchestrator**: it checks the before state,
runs `ticketing/workflow/modernize.py` with `run_workflow`, and reports the trail. The workflow
itself spawns every stage as a child session — assess (1), build (4 at once), integrate (1),
verify (1, with the payments consumer killed mid-spike), fix (routed to the owning service, at
most two rounds), ship (1: PR + Devin Review).

If your prompt begins with `WORKFLOW STAGE`, you are a child of that workflow: ignore this
playbook and do only your stage.

## What's needed

- The run token (`tkt…`, default from `ticketing/workflow/run-config.json`).
- Branch `review-base-ticketing` of the repository (the before state; never `main`).
- AWS access to EKS `otterworks-dev` (org secrets `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, or the
  `AWS_DEMO_*` pair) and the `run_workflow` tool.

## Procedure

1. `git fetch origin && git checkout review-base-ticketing` in `~/repos/otterworks`; read
   `ticketing/CONVENTIONS.md` and `ticketing/workflow/modernize.py`.
2. Preflight, and stop with a clear blocker if any step fails:
   `aws eks update-kubeconfig --name otterworks-dev --region us-east-1`;
   `kubectl get crd services.serving.knative.dev scaledobjects.keda.sh kafkas.kafka.strimzi.io`
   (if missing: `ticketing/platform/install.sh`);
   `make ticketing-status NS=<token>` — if `<token>-before` is absent, `make ticketing-before NS=<token>`;
   `curl -s https://<token>-before.demo.otterworks.app/api/health` returns `{"status":"UP"}`.
3. Set `token` in `ticketing/workflow/run-config.json` if the prompt names one (do not commit it to
   the base branch).
4. Invoke the `dynamic-workflows` skill, then call `run_workflow` with
   `workflow_name="ticketing-modernization-<token>"` and
   `script_path=/home/ubuntu/repos/otterworks/ticketing/workflow/modernize.py`. Do not edit the script's
   prompts. If the run is interrupted, resume it with the reported `run_id`; if an agent overruns its
   soft limit, check it with `get_workflow_output` / `message_workflow_agent` instead of killing it.
5. When the run ends, read the `RESULT` line. Add the workflow run link and the per-phase ACUs to the PR
   as one comment. Do not merge the PR.
6. Report a table: phase → session link → output (branch, image, hosts, pass/fail, PR), plus the verification
   measurements and the Devin Review summary. If the run ended in `EXHAUSTED`, say so plainly.

## Specifications

- Every stage ran as its own child session; the four builds ran concurrently.
- The PR targets `review-base-ticketing`, links every session, and has a Devin Review comment.
- Both namespaces are still running at the end; nothing was merged into `main` or `review-base-ticketing`.

## Forbidden actions

- Do not do a stage's work yourself instead of letting the workflow's child do it.
- Do not create `LoadBalancer` services or any AWS resource from Kubernetes.
- Do not run `make demo-destroy` for the live token.
- No real company, person, venue or customer names anywhere.
