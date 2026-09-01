# Recon summary: `U1` - **FAIL**

- Mode: `live`
- Mapping `1.0` / tolerances `1.0` / seed `0`
- Generated: 2026-09-01T05:49:59.031174+00:00

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 3 | PASS |
| 2 per_field_aggregates | 311 | FAIL (36) |
| 3 keyed_diffs | 33333 | PASS |

Top findings (5 of 36; full list in result.json):
- T2 `customers` aggregate_distinct_count: field PHONE3_TYPE_CD->phone3_type_cd
- T2 `customers` aggregate_sum: field PHONE3_TYPE_CD->phone3_type_cd
- T2 `customers` aggregate_distinct_count: field PHONE4_TYPE_CD->phone4_type_cd
- T2 `customers` aggregate_sum: field PHONE4_TYPE_CD->phone4_type_cd
- T2 `customers` aggregate_distinct_count: field SUB_STATUS_CD->sub_status_cd

Full evidence: result.json, report.md (linked from the PR, not pasted).
