# DEGRADED recon result — not an official harness verdict

- Unit: `p1-invoice-lines`
- Mode: `fixture`, depth: `full`
- Harness verdict on the compared data: `PASS`
- Grade: **DEGRADED** (reason: `d10_01_denied`)

D10-01 (opening 1521 to the Databricks serverless NAT range) was denied, so there is no
Lakehouse Federation and no official Oracle verdict is obtainable on this run. The owner
directed this JDBC route and accepted that consequence at STOP C.

Oracle read over JDBC from the Devin CIDRs with a repo-local source adapter (databricks/migration/recon/oracle_jdbc_adapter.py). The harness supplies every tier, canonicalisation rule and tolerance; the connector is outside its tested matrix, so `dbx-recon --family oracle` refuses it and this result is NOT an official harness verdict.

Unverified on this path: source-side constraint, index and identity parity (tiers 5-7), which
need catalog metadata this adapter does not read.
