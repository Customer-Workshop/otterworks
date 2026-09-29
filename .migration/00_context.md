# 00 Context: OtterWorks billing, Oracle -> MongoDB Atlas

Markers: FACT (user said it), DISCOVERED (probed), PROPOSED (default, confirm at STOP A).

| Field | Value | Marker |
|---|---|---|
| Source family | `oracle` (Oracle Free 23ai, service FREEPDB1) | FACT |
| Source host | ow-tp-oracle EC2, 52.201.36.9:1521/FREEPDB1, schema OW_BILLING | FACT |
| Source posture | read-only in every phase; no schema, data, package, job or EC2 change | FACT |
| Source read secret | `OW_TP_ORACLE_RO_DSN` (JSON user/password/dsn) | FACT |
| App read secret (before/after capture only) | `OW_TP_ORACLE_APP_PASSWORD` with `BILLING_READONLY=1` | FACT |
| Source size | 20 tables; CUSTOMER_MASTER 25,000 x 155 cols; INVOICE_HEADER 18,750; INVOICE_LINE 150,000 (37 orphans); ENTITY_ATTR_VALUE 8,333 | DISCOVERED (`baseline/oracle_counts.json`) |
| Target | Atlas cluster `otterworks-demo`, database `ow_tp_mmp_live` only | FACT |
| Target secret | `OW_TP_MMP_TARGET_URI`; no other Atlas credential may be used | FACT |
| Target after the run | `ow_tp_mmp_live` is left in place | FACT |
| App repo | Cognition-Partner-Workshops/otterworks | FACT |
| App code talking to billing | `services/legacy-billing` (Python 3 / Flask, `app/backends/{oracle,postgres}.py`, `app/reports.py`); `frontend/admin-dashboard` (Angular, `/billing-report`); `frontend/client-app` (Next.js billing pages) | DISCOVERED |
| Target driver | Python `pymongo` (pinned version in `services/legacy-billing` requirements; 4.10.1 already pinned by `scripts/tp_preflight`) | PROPOSED |
| App target | `BILLING_BACKEND=mongo` in legacy-billing serving the same routes from `ow_tp_mmp_live`; CI uses a `mongo:7` fixture container | FACT |
| Run branch | `tp-run/mongodb-20260929T160602Z` (off `tech-partnerships`); every PR targets it | FACT |
| Connectivity policy | `online` (merge evidence needs live source + migration cluster; no silent fallback) | PROPOSED |
| source_access / target_access | live / migration_cluster, BLOCKED on target privilege_excess (see `08_connectivity.json`) | DISCOVERED |
| Children reach the source | unverified; children develop on fixtures and do not read Oracle; the one live read runs from the parent/verifier | PROPOSED |
| Stop routing | this Devin web session only | FACT |
| Pings | only STOP A/B/C, wave close, halt (AGENTS rule 9) | FACT |
| stop_mode | `hard` for STOP A and STOP B (user), STOP C always hard. Effective mode: hard, so every manifest and orchestrator PR sets `auto_merge: false` | FACT |
| Cutover principal / production repoint | customer team; Devin stops at STOP C | FACT |
| Post-STOP C verification | restart legacy-billing on the run branch with `BILLING_BACKEND=mongo`, reopen Casey Novak (DEMO-00000004) Account, Tenant Two invoice 60000000-0000-0000-0000-000000000001, admin billing report; recount Oracle vs baseline | FACT |
| Before captures | `/home/ubuntu/captures/before/` (Oracle, `BILLING_READONLY=1`); post-capture recount matched baseline | DISCOVERED |
