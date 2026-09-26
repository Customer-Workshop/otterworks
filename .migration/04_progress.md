# 04_progress: unit ledger

| Unit | Wave | Status | Parity | Quarantine rate | Unverified paths | Cost | PR | Merge state |
|---|---|---|---|---|---|---|---|---|
| u-00-codes | 0 | FAIL-by-rule (offline_no_live_recon); independent recon PASS (fixture, local) | fixture PASS 32/32, target_class=local, merge_eligible=false | 0 | live recon (no source) | ~0.5 h lead+sidekick | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1708 | open, not mergeable on offline evidence |
| u-01-tenancy | 1 | FAIL (offline_no_live_recon; fixture recon PASS) | 143/143 + 282-op app parity PASS, local, merge_eligible=false | 0 | live recon | 12.29 ACU | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1712 | open, unmerged |
| u-02-customers (XL) | 1 | FAIL (tolerance_ambiguous) | T1/T2 PASS; T3 63 diffs == 63 quarantined (bad_date 50, malformed_csv 13) | 63 / 33,338 | live recon; grading of quarantined values | 12.67 ACU | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1716 (+ contract PR https://github.com/Cognition-Partner-Workshops/otterworks/pull/1710) | open, unmerged |
| u-03-invoicing-core | 1 | FAIL (offline_no_live_recon; fixture recon PASS) | 19/19, local, merge_eligible=false | 0 | live recon | 6.50 ACU | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1711 | open, unmerged |
