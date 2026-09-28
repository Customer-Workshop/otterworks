# dbx-recon attempts, unit custbill_lakeflow, run 20260927c

| # | session | mode/depth | outcome |
|---|---------|-----------|---------|
| 1 | attempt-1 predecessor | live / full | stalled ~35 min, killed, no result.json (recorded in PR #1731 body) |
| 2 | this session | live / sampled | stalled 10 min (1 s CPU, Oracle socket idle), killed. py-spy dump: blocked in `databricks.sql.auth.oauth.__get_authorization_code` -> `socketserver.handle_request` (U2M browser-redirect wait). Cause: `recon.adapters._databricks_connect` passes `oauth_client_id/oauth_client_secret` to databricks-sql-connector 4.6.0, which has no client-secret M2M kwarg and falls into the interactive flow. Attempt 1's stall matches the same signature. |
| 3 | this session | live / sampled | launched with DATABRICKS_CLIENT_ID/SECRET/AUTH_TYPE removed from the harness env and DATABRICKS_TOKEN set in-process (launcher) from `databricks.sdk.core.Config().authenticate()` under the same oauth-m2m SP d9d1c4ec-29da-4ec7-9aa0-e932710d61e2, so the harness takes its `access_token` path. Verified `current_user()` = the SP before launch. See result.json. |
