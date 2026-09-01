# Recon report: unit `U0`

- **Verdict: FAIL**
- Mode: `live`
- Mapping version: `1.2`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T18:01:12.827867+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 12 | PASS |
| 3 | keyed_diffs | 106 | FAIL (2 findings) |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "tenants.name",
    "tenants.tax_exempt_yn",
    "plans.code",
    "plans.active_yn",
    "codes.code_type",
    "codes.code_desc"
  ]
}
```

## Tier 3 coverage
```json
{
  "tenants": {
    "mode": "full_diff",
    "population": 69
  },
  "plans": {
    "mode": "full_diff",
    "population": 3
  },
  "codes": {
    "mode": "full_diff",
    "population": 32
  },
  "fixture_meta": {
    "mode": "full_diff",
    "population": 1
  }
}
```

## Tier 3 findings (2)
- `fixture_meta` missing_doc: key=(datetime.datetime(2026, 9, 1, 3, 28, 46, 978000),)
- `fixture_meta` extra_doc: key=(datetime.datetime(2026, 9, 1, 17, 6, 8, 675000),)
