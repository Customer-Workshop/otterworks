# Recon summary: `p3-user-activity` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full` / params `{'batch': 'p3probe', 'run_date': '2026-09-15'}`
- Generated: 2026-09-15T18:56:02.652298+00:00
- Cost: source 20 statements / 3141 rows fetched; target 16 statements / 3141 rows; 13.897s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 4 | PASS |
| 2 per_field_aggregates | 29 | PASS |
| 3 keyed_diffs | 3141 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
