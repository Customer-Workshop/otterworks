# 05 — Decision log

| Date (UTC) | Decision | Owner | Status |
|---|---|---|---|
| 2026-09-01 | Engagement opened: migrate entire Oracle billing estate (`OW_BILLING`) to MongoDB Atlas; orchestrator phase 1 (setup) entered | user (session request) | RECORDED |
| 2026-09-01 | Run branch `tp-run/mongodb-20260901T032752Z` cut from `tech-partnerships` per repo reproducibility policy | Devin | RECORDED |
| 2026-09-01 | Source fixture provisioned per repo runbook (`oracle-billing-up` + seed `NS=demo`), then treated strictly read-only; surfaced for confirmation at STOP A | Devin | PROPOSED |
| 2026-09-01 | Tolerance record v0.1-proposed pinned (02); all rows PROPOSED pending STOP A | Devin | PENDING STOP A |
| 2026-09-01 | STOP A approved as proposed (scope: full OW_BILLING estate; LIVE recon; tolerances v0.1→v1.0; target ow_tp_mongodb_032752; caps 1/3/3; chat-only notifications; fixture provisioning confirmed) | dhrov.subramanian ("approve", this session) | APPROVED |
| 2026-09-01 | Phase transition: phase 1 (setup) → phase 2 (inventory & data model) | orchestrator | RECORDED |
| 2026-09-01 | Phase 2 census complete: 20 tables, 5 packages, 7 triggers, 5 sequences, 2 disabled jobs, 0 ROWID usage; raw evidence in `census/raw/` | Devin | RECORDED |
| 2026-09-01 | Mapping spec v1.0-proposed authored (16 collections, 377 root + 30 embedded field mappings); coverage table complete (every object bucketed); units U0–U7 and waves 0–3 planned; write targets registered as PLANNED in 04 | Devin | PENDING STOP B |
| 2026-09-01 | Fan-out width: wave 1 = 2, wave 2 = 3, wave 3 = one sequential U5→U6 batch; live source extract/recon serialized through single live window (source-load cap 1); NOT width-1-inline | Devin | PENDING STOP B |
| 2026-09-01 | Orphan disposition: 37 INVOICE_LINE orphans → owq.invoice_feed_orphan_lines; ENTITY_ATTR_VALUE (populated, no runtime reader) migrated as customers.attributes[] embed rather than dropped; string-date VARCHAR2 columns migrate verbatim as strings | Devin | PENDING STOP B |
| 2026-09-01 | STOP B approved as proposed (model 16 collections; dispositions: orphans→quarantine, EAV→customers.attributes[], string dates verbatim; units U0–U7; waves 0–3; widths 2/3/1). Mapping spec v1.0-proposed → v1.0 | dhrov.subramanian ("approve", this session) | APPROVED |
| 2026-09-01 | Phase transition: phase 2 (inventory & data model) → phase 3 (fan-out across waves) | orchestrator | RECORDED |
