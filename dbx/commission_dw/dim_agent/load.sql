-- dim_agent loader: initialise from the DIM_AGENT baseline snapshot, then apply the
-- dw_etl_pkg.load_commission_facts MERGE (02_etl_pkg.sql L23-33) from the AGENTS feed.
-- Statements are `;`-terminated and run in order by run.py after ddl.sql.

-- 1. Initialise from the baseline snapshot: agent_key values carried over verbatim (DEC-003).
--    Explicit schema + FAILFAST: a malformed or extra-field record aborts the load.
INSERT INTO ow_tp.silver.dim_agent_cdw (agent_key, agent_id, agent_code, full_name, status, loaded_at)
SELECT agent_key, agent_id, agent_code, full_name, status, current_timestamp()
  FROM read_files(
         '/Volumes/ow_tp/bronze/landing/cdw/baseline/DIM_AGENT.csv',
         format => 'csv', header => true,
         schema => 'agent_key BIGINT, agent_id BIGINT, agent_code STRING, full_name STRING, status STRING',
         mode => 'FAILFAST');

-- 2. Baseline guard: NOT NULL attributes must not fail open (empty CSV field reads as NULL).
SELECT assert_true(
         count_if(agent_key IS NULL OR agent_id IS NULL OR agent_code IS NULL
                  OR full_name IS NULL OR status IS NULL) = 0,
         'dim_agent baseline contains NULL in a NOT NULL column')
  FROM ow_tp.silver.dim_agent_cdw;

-- 3. Feed guard: the legacy MERGE inserts NOT NULL columns straight from AGENTS; a NULL
--    there raised ORA-01400 and aborted the load, so fail here too instead of merging.
SELECT assert_true(
         count_if(agent_id IS NULL OR agent_code IS NULL OR full_name IS NULL OR status IS NULL) = 0,
         'agents feed contains NULL in a NOT NULL dim_agent column')
  FROM ow_tp.bronze.agents_cdw;

-- 4. MERGE INTO dim_agent ... ON (d.agent_id = s.agent_id)
--    WHEN MATCHED: update agent_code, full_name, status (and nothing else, as the legacy did)
--    WHEN NOT MATCHED: insert with agent_key = max(agent_key) + row_number() OVER (ORDER BY agent_id)
MERGE INTO ow_tp.silver.dim_agent_cdw AS d
USING (
    SELECT s.agent_id,
           s.agent_code,
           s.full_name,
           s.status,
           CASE WHEN e.agent_id IS NULL
                THEN m.max_key + row_number() OVER (PARTITION BY (e.agent_id IS NULL) ORDER BY s.agent_id)
           END AS new_agent_key
      FROM ow_tp.bronze.agents_cdw s
      LEFT JOIN ow_tp.silver.dim_agent_cdw e ON e.agent_id = s.agent_id
      CROSS JOIN (SELECT coalesce(max(agent_key), 0) AS max_key FROM ow_tp.silver.dim_agent_cdw) m
) AS s
ON d.agent_id = s.agent_id
WHEN MATCHED THEN UPDATE SET
     d.agent_code = s.agent_code,
     d.full_name  = s.full_name,
     d.status     = s.status
WHEN NOT MATCHED THEN
     INSERT (agent_key, agent_id, agent_code, full_name, status, loaded_at)
     VALUES (s.new_agent_key, s.agent_id, s.agent_code, s.full_name, s.status, current_timestamp());
