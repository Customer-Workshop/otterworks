# cnvingest — sftp_ingest_poll.ksh → Databricks job ow_tp_ingest_cnvingest

Transport-only, byte-transparent conversion of the 1998 ksh ingest job.
Contract: `docs/tech-partnerships/contracts/sftp_ingest_poll-cnvingest.contract.json`.
Golden baseline: `docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.golden.json`.

| File | Purpose |
|---|---|
| `ingest_core.py` | Pure-Python transport core (discover, atomic stage, archive, delete-after-success) shared by the notebook and the fixture recon |
| `sftp_ingest_poll_notebook.py` | Databricks notebook source: Volumes paths + Delta MERGE registration, all derived from the `ns` parameter |
| `job_ow_tp_ingest_cnvingest.json` | Jobs API job spec: serverless notebook task, manual per-batch trigger, `max_concurrent_runs=1` |
| `deploy_job.py` | Imports the notebook/core under `/Shared/ow_tp/cnvingest` and creates/resets the job (needs `DATABRICKS_DEMO_HOST`/`DATABRICKS_DEMO_TOKEN`) |
| `recon_fixture.py` | Fixture-mode recon: reruns the core against a local landing layout and writes `docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.recon.json` |

Fixture recon (deterministic; seeded shas must equal the golden baseline):

```bash
export OTTERWORKS_LEGACY_ROOT=/tmp/ow-legacy-cnvingest
make legacy-etl-gen-data NS=cnvingest
python3 etl/databricks/cnvingest/recon_fixture.py \
  --out docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.recon.json
make tp-validate-recon FILE=docs/tech-partnerships/recon/sftp_ingest_poll-cnvingest.recon.json
```

Live execution (parent-owned validation window): `python3 etl/databricks/cnvingest/deploy_job.py`,
land drop files under `/Volumes/ow_tp/bronze/landing/cnvingest/sftp_ingest_poll/drop/`, run the job
with `ns=cnvingest`. Writes stay inside the cnvingest slice (`*_cnvingest` tables, `cnvingest/` volume paths).
