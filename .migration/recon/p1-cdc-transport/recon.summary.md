> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-cdc-transport` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `threshold`
- Generated: 2026-09-15T06:40:08.802469+00:00
- Cost: source 15 statements / 193750 rows fetched; target 12 statements / 193750 rows; 546.123s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 3 | PASS |
| 2 per_field_aggregates | 184 | PASS |
| 3 keyed_diffs | 193750 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
