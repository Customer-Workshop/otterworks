-- Pipeline 1 governance: APPROVED rows only.
-- Source of truth: databricks/migration/governance/p1_governance_map.json (row G-07).
-- Every PROPOSED or GAP row is deliberately absent; adding one here needs a human decision
-- recorded in .migration/06_decisions.md.
--
-- Scope: the migration catalog `ow_tp` and the Lakebase branch database only. No production
-- catalog, no account-group creation, no PUBLIC grant. Run once by the orchestrator session;
-- fan-out children never execute grants.
-- Idempotent: every statement is a GRANT of a privilege the principal already needs to hold
-- for the factory-doctor to be green.

-- === Unity Catalog (analytical track) ===
GRANT USE CATALOG ON CATALOG ow_tp TO `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`;
GRANT USE SCHEMA, CREATE TABLE, MODIFY, SELECT ON SCHEMA ow_tp.bronze TO `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`;
GRANT USE SCHEMA, CREATE TABLE, MODIFY, SELECT ON SCHEMA ow_tp.silver TO `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`;
GRANT USE SCHEMA, CREATE TABLE, MODIFY, SELECT ON SCHEMA ow_tp.gold   TO `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME ow_tp.bronze.landing TO `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`;

-- === Lakebase (operational track) ===
-- Run against the migration branch endpoint (project ow-tp-billing, database ow_tp),
-- never the `production` branch. DSN generated at runtime; never stored.
-- psql "$OW_TP_LAKEBASE_DSN" -f p1_grants_approved.sql  (the block below only)
--
--   GRANT USAGE, CREATE ON SCHEMA billing TO "2e90bc1d-e9a1-4703-8c48-ad28ebb1864d";
--   ALTER DEFAULT PRIVILEGES IN SCHEMA billing
--     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "2e90bc1d-e9a1-4703-8c48-ad28ebb1864d";
--
-- (kept commented because this file is executed against Unity Catalog; the Lakebase half is
-- applied by the wave-0 scaffolding unit with the same two statements.)
