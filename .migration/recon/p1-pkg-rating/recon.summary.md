> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-pkg-rating` - **PASS**

- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T11:24:56.091863+00:00
- Cost: source 35 statements / 264 rows fetched; target 29 statements / 258 rows; 3.105s
- Consistency window: source isolation `snapshot`, target isolation `repeatable_read`, held
- **WARNING: UNVERIFIED schema_parity: rating_periods: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**
- **WARNING: UNVERIFIED schema_parity: rating_results: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Checks | Result |
|---|---|---|
| 0 consistency_window | 2 | PASS |
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 13 | PASS |
| 3 keyed_diffs | 6 | PASS |
| 4 app_level_parity | 2 | PASS |
| 5 pk_set_diff | 2 | PASS |
| 6 cdc_lag_ordering | 0 | PASS |
| 7 schema_parity | 0 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
