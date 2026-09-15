# Recon summary: `p2-sftp-ingest` - **PASS**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping `map-p2-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T12:18:18.039366+00:00
- Cost: source 5 statements / 123 rows fetched; target 4 statements / 123 rows; 3.722s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 4 | PASS |
| 3 keyed_diffs | 123 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
