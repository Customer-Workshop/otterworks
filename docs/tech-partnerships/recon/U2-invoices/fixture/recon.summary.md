# Recon summary: `U2-invoices` - **PASS**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging) | Target: `local` (local target: NOT a merge verdict)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping `map-1` / tolerances `1` / seed `0`
- Generated: 2026-09-29T19:06:10.082259+00:00
- **WARNING: embed invoices.lines: scoped by a where-predicate; extra target elements not checked**

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 3 | PASS |
| 2 per_field_aggregates | 5 | PASS |
| 3 keyed_diffs | 168750 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
