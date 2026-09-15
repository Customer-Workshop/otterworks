> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-billing-audit-log` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T08:15:27.108926+00:00
- Cost: source 5 statements / 0 rows fetched; target 4 statements / 0 rows; 1.23s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 4 | PASS |
| 3 keyed_diffs | 0 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
