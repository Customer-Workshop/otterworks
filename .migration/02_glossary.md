# 02_glossary.md — customer terms → plain meaning

| Term | Meaning |
|---|---|
| ETL box | `otterworks-etl-prod-01`, the host running all nine cron jobs |
| CUSTBILL | mainframe customer-billing fixed-width extract (copybook CBCUST01), 2 files × 50 records for NS=demo |
| Copybook CBCUST01 | record layout: id, name, date (YYYYMMDD), amount (implied 2 decimals), currency, record type (`01` invoice / `02` credit), trailer with record count |
| `.psv` | pipe-separated parsed output of the fixed-width parser (6 fields) |
| Finance report | `finance_billing_YYYYMMDD.csv` (+ byte-identical `.xls`): currency × record-type count and total |
| `run_all` | Sunday chain of ingest → parse → finance with `sleep 600` between stages |
| Settle | ingest's completion heuristic: file size unchanged after 1 s |
| Trailer | last record of a CUSTBILL file carrying the expected record count (never reconciled by legacy) |
| Quarantine | silver-side table receiving records the converted pipeline rejects |
| Planted anomaly | a known-bad record class the contract requires the conversion to detect (`must-detect`) or declares out of scope (`coverage_gap`) |
| Golden baseline | legacy output regenerated from the deterministic seed for a given NS; the only recon reference |
| `ns` | namespace: isolates a run's data in every table/volume/job parameter; `demo` is persistent |
| Fixture mode | child self-verification against the local transport fixture / LocalStack (`run_mode: fixture`) |
| Live window | parent-owned, uncontended recon pass on NS=demo (`run_mode: live`), one per wave |
| Wave | dependency-ordered batch of units (0 shared, 1 pilot, 2+ fan-out) |
| D1–D10 | dependency classes (see `04_dependency_register.md`) |
| STOP A–E | human decision points: A target/tolerances/access, B pipeline, C plan, D wave review, E cutover |
| Deficiency table | acceptance checklist in `etl/ETL_UPGRADE_GUIDE.md` and `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md` |
| Jake | former operator whose 2019/2020 leftovers (`run_all.sh`, `jake@` recipient) still run |
