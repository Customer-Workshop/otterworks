> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-pkg-plans` - **PASS**

- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T08:05:03.244882+00:00
- Cost: source 80 statements / 337 rows fetched; target 77 statements / 273 rows; 8.783s
- Consistency window: source isolation `snapshot`, target isolation `repeatable_read`, held
- **WARNING: UNVERIFIED schema_parity: subscriptions: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Checks | Result |
|---|---|---|
| 0 consistency_window | 1 | PASS |
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 7 | PASS |
| 3 keyed_diffs | 69 | PASS |
| 4 app_level_parity | 2 | PASS |
| 5 pk_set_diff | 1 | PASS |
| 6 cdc_lag_ordering | 0 | PASS |
| 7 schema_parity | 0 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
