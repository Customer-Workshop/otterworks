# 04 Progress

| Unit | Status | Parity | Quarantine rate | Unverified paths | Cost | PR |
|---|---|---|---|---|---|---|
| baseline (Oracle counts) | done | 20/20 tables match user figures | - | - | - | - |
| before captures (Oracle, read-only) | done | post-capture recount match | - | - | - | - |
| setup (STOP A) | approved (D-010) | connectivity probe_ok both sides | - | - | - | #1741 |
| inventory + model (STOP B) | approved (D-011, superseded by D-015) | census 20/20 tables, 24 objects covered | 37 orphans -> quarantine | - | - | #1741 |
| STOP B change (waves 0/1/2) | approved (D-015) | - | - | - | - | #1741 |
| wave 0: U0-reference (codes, tenants, plans, sequences) | closed PASS (D-016), awaiting manual merge | live T1 3/3, T2 6/6, T3 104/104; independent recon PASS | - | - | - | #1742 |
| wave 1: U1-customers (calibration) | closed PASS (D-017), awaiting manual merge | live T1 2/2, T2 15/15, T3 33,333/33,333; independent recon PASS | - | - | - | #1743 |
| wave 2: U2-invoices, U3-billing-core, U4-app-backend (fan-out, width 3) | closed PASS (D-019), run wfr-801c19c633a04d6d8886dc591a81877a | independent verify PASS 3/3 | - | - | 32.96 ACU | #1744 #1745 #1746 |
| w2-b01 U2-invoices (+quarantine) | PASS, merge_eligible=false (D-012 scoped-embed warning only) | 18,750 invoices, 149,963 embedded lines, 168,750 keyed rows | 37/37 orphans quarantined | - | 3.49 ACU | #1745 |
| w2-b02 U3-billing-core | PASS, merge-eligible | T1 11 / T2 28 / T3 901 | - | subscriptions_hist, billing_audit_log empty in source | 3.54 ACU | #1744 |
| w2-b03 U4-app-backend | PASS, merge-eligible | fixture + live recon PASS; app queries Oracle = Mongo | - | 3 lint issues in test files (not CI-gated) | 21.34 ACU | #1746 |
