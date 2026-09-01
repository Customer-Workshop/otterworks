# 05 — Decision log

| Date (UTC) | Decision | Owner | Status |
|---|---|---|---|
| 2026-09-01 | Engagement opened: migrate entire Oracle billing estate (`OW_BILLING`) to MongoDB Atlas; orchestrator phase 1 (setup) entered | user (session request) | RECORDED |
| 2026-09-01 | Run branch `tp-run/mongodb-20260901T032752Z` cut from `tech-partnerships` per repo reproducibility policy | Devin | RECORDED |
| 2026-09-01 | Source fixture provisioned per repo runbook (`oracle-billing-up` + seed `NS=demo`), then treated strictly read-only; surfaced for confirmation at STOP A | Devin | PROPOSED |
| 2026-09-01 | Tolerance record v0.1-proposed pinned (02); all rows PROPOSED pending STOP A | Devin | PENDING STOP A |
| 2026-09-01 | STOP A approved as proposed (scope: full OW_BILLING estate; LIVE recon; tolerances v0.1→v1.0; target ow_tp_mongodb_032752; caps 1/3/3; chat-only notifications; fixture provisioning confirmed) | dhrov.subramanian ("approve", this session) | APPROVED |
| 2026-09-01 | Phase transition: phase 1 (setup) → phase 2 (inventory & data model) | orchestrator | RECORDED |
