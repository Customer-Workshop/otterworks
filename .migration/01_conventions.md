# 01 — Conventions

## Designated write target

**The only place this engagement ever writes.**

| | |
|---|---|
| Cluster | Atlas `otterworks-demo` (`otterworks-demo.cgbijgv.mongodb.net`), MongoDB 8.0.29, project `otterworks-demos` |
| Database | `ow_tp_demo` |
| Quarantine database | `ow_tp_demo_quarantine` |
| Namespace | `demo` (the repo's persistent demo namespace; `ow_tp_<ns>` is the repo default database name) |

Nothing outside `ow_tp_demo` and `ow_tp_demo_quarantine` is written, created, dropped, or
reconfigured — no grants, no users, no index or validator changes elsewhere. The cluster
already holds `ow_tp_billing_demo`, `ow_tp_demo1`, `ow_tp_mongodb_demo` and
`ow_tp_mongodb_demo_quarantine` from other runs; those are **other owners' slices** and are
out of bounds. `ow_tp_demo` did not exist before this engagement, so the designated target
is uncontended.

## Secret NAMES (values never appear in any artifact, log, PR body, or code)

| Purpose | Env var NAME |
|---|---|
| Target cluster URI | `MONGODB_ATLAS_URI` |
| Atlas control plane | `MONGODB_ATLAS_PUBLIC_KEY`, `MONGODB_ATLAS_PRIVATE_KEY`, `MONGODB_ATLAS_PROJECT_ID` |
| Source DSN | `OW_BILLING_SOURCE_DSN` — value is `user/password/dsn` (the format `recon.adapters.OracleSourceAdapter` expects). No secret is provisioned for it in the vault, because the Oracle estate is a local fixture reached at `localhost:52521/FREEPDB1` whose credentials live in `docker-compose.oracle-billing.yml`; the operator exports the NAME into the environment before the load and the recon run, and the value is never inlined into code, artifacts, logs, or a PR body. If the estate is ever repointed at a real instance, provision a vault secret under this same NAME |

## Collection and field naming

- Collections: lower snake plural — `customers`, `invoices`.
- Quarantine collections mirror the unit name in the quarantine database:
  `ow_tp_demo_quarantine.customers`, `ow_tp_demo_quarantine.invoices`.
- Fields: lower snake, source column names lowercased (`cust_no`, `signup_dt`); no
  Oracle-isms (`_CD`, `_FLAG`) are renamed at this stage — renames are a mapping-spec
  decision at playbook 2, and each one is an explicit row there.
- EAV rows fold into an `attributes` subdocument on `customers`; CSV columns become real
  arrays. Both are mapping-spec decisions, recorded here only as naming shape.
- `_id`: the natural business key, not an ObjectId, so recon has a stable comparison key
  on both sides (`customers._id = CUST_NO`, `invoices._id = INVOICE_ID`). The mapping spec
  declares the key explicitly; the harness refuses a collection without one.
- Tenant scoping: every document carries `ns` (namespace) so a load can be re-run for one
  namespace without touching another.

## Branch / PR convention

- Run branch: **`tp-run/mongodb-20260831T232410Z`** (cut with
  `make tp-run-branch TRACK=mongodb` off `tech-partnerships`).
- Every unit PR targets that run branch. `tech-partnerships` is never a PR target, and
  nothing here is ever merged to `main`.
- **One PR per unit** — never a stacked series.
- Working branches: `devin/<unix-timestamp>-<slug>`.
- Every PR must pass the `tp-golden-smoke` gate (`make tp-smoke` locally first).
- A unit is done only when its PR is **merged** into the run branch.

## Artifact layout

```
.migration/
  00_context.md          scope, census facts, capability manifest, gaps
  01_conventions.md      this file
  02_tolerances.json     versioned tolerance record
  03_mapping_spec.json   harness mapping spec (v1.0.0, authored at playbook 2)
  04_progress.md         write-target registry, unit ledger, circuit breaker
  05_stops.md            STOP A/B/C decision log
  06_census.md           object census, stored logic, access patterns, anomaly scan
  profile.canon.json     oracle recon_canonicalization, placeholders resolved
  recon/<unit_id>/       harness evidence: result.json, report.md, recon.summary.md
```

Evidence layout is per unit: `.migration/recon/customers/`, `.migration/recon/invoices/`.
The unit PR renders `recon.summary.md` inline and links `result.json` and `report.md`; it
never pastes the full report.
