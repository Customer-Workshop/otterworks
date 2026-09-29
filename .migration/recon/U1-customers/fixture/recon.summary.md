# Recon summary: `U1-customers` - **PASS**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging) | Target: `local` (local target: NOT a merge verdict)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping `map-1` / tolerances `1` / seed `1`
- Generated: 2026-09-29T18:11:29.653889+00:00
- **WARNING: embed customers.attributes: scoped by a where-predicate; extra target elements not checked**

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 15 | PASS |
| 3 keyed_diffs | 33338 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
