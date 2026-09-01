# 04_dependency_register.md — dependency register

Taxonomy: D1 data model · D2 code dependency · D3 upstream feed · D4 downstream consumer ·
D5 scheduler edge · D6 platform feature gap · D7 external hand-off · D8 governance/security ·
D9 tolerance/decision pending · D10 environment/access.
Status: OPEN · IN_PROGRESS · CLOSED · DEFERRED(condition). Rows are appended, never deleted.

| ID | Class | Unit(s) | Contract / description | Owner | Status | Fired request / evidence |
|---|---|---|---|---|---|---|
| D10-1 | env | all | Catalog `ow_tp` absent; preflight 3/10 DENIED (`files-get-directory`, `files-put-get`, `uc-create-list`) | parent | OPEN | Wave-0 parent task: create catalog/schemas/volume via shared Terraform, rerun `make tp-preflight PLATFORM=databricks` to clean manifest. See `07_access_checklist.md` A2. |
| D10-2 | env | all | `infrastructure/terraform-databricks/`, `scripts/tp_databricks/dbx.py`, and the 9 contract files referenced by `contracts/README.md` are absent | parent | OPEN | Wave 0 authors them; `make tp-validate-contracts` fails until then. |
| D10-3 | env | 6,7,8,9 | Legacy runtime prerequisites (`ksh`, docker+`sshpass` for SFTP fixture; LocalStack for Python jobs) | parent | IN_PROGRESS | Probed at setup; result in `07_access_checklist.md` A4/A5. |
| D5-1 | scheduler | 6,7 | `*/15` ingest vs `5-59/15` parse: half-written reads | parent | OPEN | Target: single Workflow, parse depends on ingest task. Decide at plan. |
| D5-2 | scheduler | 1,8 | 02:00 analytics vs 02:10 finance overlap | parent | OPEN | Target: independent Workflows, no shared writes; finance depends on parse only. |
| D5-3 | scheduler | 9 | Sunday 06:00 `run_all` re-runs 6→7→8 over live 15-min jobs | parent | OPEN | Target: same DAG, `max_concurrent_runs=1`; `run_all` retired as separate code. |
| D5-4 | scheduler | 2,3 | Weekly Sunday 03:00/04:00 jobs | parent | OPEN | Target: Workflows, paused until STOP E. |
| D5-5 | scheduler | 4,5 | Daily 02:30/05:00 jobs | parent | OPEN | Same. |
| D7-1 | external | 6 | Mainframe CUSTBILL SFTP drop → S3 Transfer Family / landing volume; owner unnamed | customer | OPEN | **Ask at STOP A**: named mainframe-transfer owner. Contract must fix encoding, malformed-record, empty-input, batch granularity. |
| D4-1 | consumer | 8 | `finance-reports@otterworks.dev` `.xls` distribution; `jake@` stale | customer | OPEN | Ask at STOP A: recipient-list owner. Delivery mechanism decided at plan. |
| D4-2 | consumer | 5 | admin-service reads `reports/user-activity/<ds>/activity_report.json` | parent | OPEN | Default: keep path + shape byte-compatible; decide at plan. |
| D3-1 | upstream | 3 | document-/file-service REST → MeiliSearch reindex | parent | OPEN | Scope decision at STOP B/C: keep as a Job (default). |
| D8-1 | governance | 1-5 | `config.ini` plaintext creds | parent | OPEN | Secret scope `ow_tp`, names only. Closed when wave 0 seeds the scope. |
| D8-2 | governance | all | Shared PAT, no service principal; attribution by `ns`/branch/PR | customer | DEFERRED(demo workspace) | Access model in `07_access_checklist.md`. |
| D9-1 | tolerance | all | Tolerance record v1 PROPOSED | user | OPEN | STOP A. |
| D9-2 | decision | all | PR shape: 1 PR/unit vs README 3-PR stack | user | OPEN | STOP A (D-002 proposed). |
