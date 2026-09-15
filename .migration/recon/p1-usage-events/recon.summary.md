> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-usage-events` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T07:07:23.681324+00:00
- Cost: source 8 statements / 885 rows fetched; target 7 statements / 885 rows; 4.626s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 5 | PASS |
| 3 keyed_diffs | 814 | PASS |
| 4 app_level_parity | 3 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
