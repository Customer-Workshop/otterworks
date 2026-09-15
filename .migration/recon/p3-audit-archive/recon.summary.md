# Recon summary: `p3-audit-archive` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p3-v1` / tolerances `v1` / seed `0` / depth `full` / params `{'run_date': '2026-09-15', 'batch': 'p3probe'}`
- Generated: 2026-09-15T20:19:33.837347+00:00
- Cost: source 10 statements / 84 rows fetched; target 8 statements / 84 rows; 8.04s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 7 | PASS |
| 3 keyed_diffs | 84 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
