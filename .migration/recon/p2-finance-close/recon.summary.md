# Recon summary: `p2-finance-close` - **PASS**

- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping `map-p2-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T13:28:35.665192+00:00
- Cost: source 5 statements / 11 rows fetched; target 4 statements / 11 rows; 3.028s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 6 | PASS |
| 3 keyed_diffs | 11 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
