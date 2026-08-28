# 01 — Migration conventions

| Convention | Status and rule |
|---|---|
| Run branch | **FACT** — use a fresh `tp-run/databricks-<timestamp>` branch from the run base (`docs/tech-partnerships/contracts/README.md:38-43`). |
| Child branch | **FACT** — `migrate/ow_billing/<wave>-<unit>` (`docs/tech-partnerships/contracts/README.md:38-43`). |
| PR shape | **FACT** — one PR per migration unit, stacked bottom-up (`docs/tech-partnerships/contracts/README.md:38-43`). |
| PR evidence | **FACT** — each unit PR carries its own `*.recon.json`, with `kind: recon-report`, and validates it against `contracts/schema/recon-report.schema.json` (`docs/tech-partnerships/contracts/README.md:8-11`). |
| Smoke gate | **FACT** — run `make tp-smoke`; every PR must pass it (`docs/tech-partnerships/contracts/README.md:35-37`). |
| Object prefix | **FACT** — every shared-workspace object is `ow_tp`-prefixed; never touch an unprefixed object (`docs/tech-partnerships/contracts/README.md:23-26`). |
| Compute | **FACT** — create no cluster, warehouse, or hourly-floor resource; reuse the existing serverless SQL warehouse and serverless job compute (`docs/tech-partnerships/contracts/README.md:23-26`). |
| Terraform ownership | **FACT** — add only `infrastructure/terraform-databricks/jobs_<unit>.tf`; never edit the shared stack or run apply/destroy (`docs/tech-partnerships/contracts/README.md:19-22`). |
| Namespace | **FACT** — every job has `ns`, paths use `<ns>/<unit>/...`, and rows carry `ns` (`docs/tech-partnerships/contracts/README.md:27-29`). |
| Secrets | **FACT** — secret names may be documented, values never enter branches; jobs read values through `dbutils.secrets` (`origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:47-51`). |
| Branch contents | **FACT** — code only, never data, state, or secrets (`docs/tech-partnerships/contracts/README.md:27-29`). |

## Review rejection checklist

- **PROPOSED:** reject any unprefixed object, cluster/resource creation, shared Terraform edit,
  missing `ns`, missing recon report, hardcoded secret, or failed `make tp-smoke`.
- **PROPOSED:** reject a unit PR whose recon report does not state provenance, quarantine
  accounting, idempotency rerun, and any unverified path required by the report schema.
