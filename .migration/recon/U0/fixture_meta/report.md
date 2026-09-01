# Recon report: unit `U0-fixture_meta`

- **Verdict: FAIL**
- Mode: `live`
- Mapping version: `1.0`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T04:17:31.755219+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 0 | PASS |
| 3 | keyed_diffs | 2 | FAIL (2 findings) |

## Tier 3 coverage
```json
{
  "fixture_meta": {
    "mode": "full_diff",
    "population": 1
  }
}
```

## Tier 3 findings (2)
- `fixture_meta` missing_doc: key=(datetime.datetime(2026, 9, 1, 3, 59, 49, 454979),)
- `fixture_meta` extra_doc: key=(datetime.datetime(2026, 9, 1, 3, 59, 49, 454000),)
