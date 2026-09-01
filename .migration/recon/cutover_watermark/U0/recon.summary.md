# Recon summary: `U0` - **FAIL**

- Mode: `live`
- Mapping `1.2` / tolerances `1.0` / seed `0`
- Generated: 2026-09-01T18:01:12.827867+00:00

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 4 | PASS |
| 2 per_field_aggregates | 12 | PASS |
| 3 keyed_diffs | 106 | FAIL (2) |

Top findings (2 of 2; full list in result.json):
- T3 `fixture_meta` missing_doc: key=(datetime.datetime(2026, 9, 1, 3, 28, 46, 978000),)
- T3 `fixture_meta` extra_doc: key=(datetime.datetime(2026, 9, 1, 17, 6, 8, 675000),)

Full evidence: result.json, report.md (linked from the PR, not pasted).
