# Recon summary: `p3-audit-archive` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T17:33:44.753868+00:00
- Cost: source 10 statements / 84 rows fetched; target 8 statements / 84 rows; 3.656s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 7 | PASS |
| 3 keyed_diffs | 84 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
