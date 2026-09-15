> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon summary: `p1-invoice-lines` - **PASS**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping `map-p1-v1` / tolerances `v1` / seed `0` / depth `full`
- Generated: 2026-09-15T10:15:12.845317+00:00
- Cost: source 5 statements / 2 rows fetched; target 5 statements / 2 rows; 0.029s

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 6 | PASS |
| 3 keyed_diffs | 2 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
