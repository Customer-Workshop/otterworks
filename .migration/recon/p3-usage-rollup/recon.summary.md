# Recon summary: `p3-usage-rollup` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full` / params `{'batch': 'p3probe'}`
- Generated: 2026-09-15T18:00:44.900209+00:00
- Cost: source 5 statements / 7 rows fetched; target 4 statements / 7 rows; 2.195s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 12 | PASS |
| 3 keyed_diffs | 7 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
