# COMMISSION_DW parallel-run contract
The paused job compares the production legacy baseline with the two migrated outputs.
Each cycle runs fact_commission first, then the dependent agent commission summary.
A green cycle requires both recon reports to be PASS with all checks and reruns passing.
A failed fact task skips the summary task; the cycle is red.
The `staged_red` switch turns a passing verification run into an intentional red trigger.
Staged-red failure text identifies the verification drill and preserves the PASS report.
Reports land under `/Volumes/ow_tp/bronze/landing/<ns>/recon/<run_id>/<unit>/`.
The report path is printed by the trigger command for each completed notebook task.
The `r3_notify` task runs with `run_if=ALL_DONE` and sends source, job, run,
namespace, verdict, staged-red, task, and report fields to the remediation webhook.
It reads `devin_webhook_url` and `devin_webhook_secret` by name from secret scope `ow_tp_cdw`.
`deploy --with-webhook` seeds those secrets; without it, secrets remain unchanged and `r3_notify` stays configured.
The window is opened with `run.py schedule --unpause`; `deploy` preserves the live pause state.
The schedule is UTC `0 0 6 * * ?`, remains PAUSED until approval, and runs serially.
Each cycle costs approximately two full reloads plus two recon reads.
Expected serverless cost is approximately 2–3 warehouse-minutes per cycle.
The parent opens the window only after approval and the staged-red drill.
STOP E entry requires three consecutive green scheduled cycles.
No cutover or consumer change is performed by this job.
