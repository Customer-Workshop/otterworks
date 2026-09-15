# Recon summary: `p3-analytics-daily` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full` / params `{'run_date': '2026-09-15', 'batch': 'p3probe'}`
- Generated: 2026-09-15T17:07:16.410685+00:00
- Cost: source 20 statements / 224 rows fetched; target 16 statements / 224 rows; 10.046s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 4 | PASS |
| 2 per_field_aggregates | 25 | PASS |
| 3 keyed_diffs | 224 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
