> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-pkg-rating` - **PASS**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T11:24:38.171624+00:00
- Cost: source 12 statements / 244 rows fetched; target 11 statements / 244 rows; 0.062s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 13 | PASS |
| 3 keyed_diffs | 6 | PASS |
| 4 app_level_parity | 2 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
