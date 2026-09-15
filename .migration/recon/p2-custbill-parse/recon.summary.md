# Recon summary: `p2-custbill-parse` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p2-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T12:51:35.113865+00:00
- Cost: source 5 statements / 116 rows fetched; target 4 statements / 116 rows; 2.95s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 3 | PASS |
| 3 keyed_diffs | 116 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
