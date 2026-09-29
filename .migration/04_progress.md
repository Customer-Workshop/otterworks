# 04 Progress

| Unit | Status | Parity | Quarantine rate | Unverified paths | Cost | PR |
|---|---|---|---|---|---|---|
| baseline (Oracle counts) | done | 20/20 tables match user figures | - | - | - | - |
| before captures (Oracle, read-only) | done | post-capture recount match | - | - | - | - |
| setup (STOP A) | approved (D-010) | connectivity probe_ok both sides | - | - | - | #1741 |
| inventory + model (STOP B) | approved (D-011, superseded by D-015) | census 20/20 tables, 24 objects covered | 37 orphans -> quarantine | - | - | #1741 |
| STOP B change (waves 0/1/2) | approved (D-015) | - | - | - | - | #1741 |
| wave 0: U0-reference (codes, tenants, plans, sequences) | in progress (in-session) | - | - | - | - | - |
| wave 1: U1-customers (calibration) | live load + live recon PASS carried from D-011 run; PR + fresh-session recon pending | - | - | - | - | - |
| wave 2: U2-invoices, U3-billing-core, U4-app-backend (fan-out, width 3) | planned | - | - | - | - | - |
