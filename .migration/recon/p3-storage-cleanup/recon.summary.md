# Recon summary: `p3-storage-cleanup` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full` / params `{'batch': 'p3probe'}`
- Generated: 2026-09-15T17:17:04.177583+00:00
- Cost: source 5 statements / 17 rows fetched; target 4 statements / 17 rows; 3.134s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 2 | PASS |
| 3 keyed_diffs | 17 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
