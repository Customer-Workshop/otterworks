# 04 Progress

Units and waves, derived from the census (`census.md`) and the PRD delivery order.
Status values: PLANNED, RUNNING, PASS, FAIL, HALTED.

| Unit | Wave | Batch | Status | Parity | Quarantine rate | Unverified paths | PR |
|---|---|---|---|---|---|---|---|
| plans, codes, tenants, subscription_history | 0 | w0-b01 | PLANNED | — | — | — | — |
| customers, customer_history | 1 | w1-b01 | PLANNED | — | — | — | — |
| invoices, invoice_lines_orphaned | 1 | w1-b02 | PLANNED | — | — | — | — |
| usage_events, rating_periods | 1 | w1-b03 | PLANNED | — | — | — | — |
| credit_notes, notifications, audit_log | 1 | w1-b04 | PLANNED | — | — | — | — |

Wave 0 is one batch, so it runs in-session (`!mongo_unit_migration` then
`!mongo_reconciliation`), per the orchestrator playbook's small-wave rule. Wave 1 is four
batches, so it runs through the `migration-fanout` workflow at width 4.

Expected row counts per unit are in each batch brief and in `03_mapping_spec.json`
under `cardinality`.
