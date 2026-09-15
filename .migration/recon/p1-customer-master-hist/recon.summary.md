> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-customer-master-hist` - **PASS**

- Mode: `live`
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T08:04:00.726587+00:00
- Cost: source 6 statements / 0 rows fetched; target 5 statements / 0 rows; 2.897s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 158 | PASS |
| 3 keyed_diffs | 0 | PASS |
| 4 app_level_parity | 1 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
