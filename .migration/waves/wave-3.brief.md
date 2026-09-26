# Wave 3 close

Exceptions: 2 (both batches FAIL-by-rule `offline_no_live_recon`; fixture recon PASS everywhere; 2 low verifier findings).
Landed: 0 of 2 batches merge-eligible (auto_merge: false, offline evidence never merges).
Independent verify: RUN (recon-w3, c961af93): fixture PASS, live recon pending customer run; agrees tier-for-tier with both batches.
Failed: none (by gate). Blocked by rule: w3-b01 (PR #1725), w3-b02 (PR #1726).
Held back by circuit breaker: none. Collisions: none. Undeclared targets: none.
Awaiting manual merge: none (nothing may merge on local evidence).

Verifier findings: F1 (low) u-07 `code_desc(type, None)` raises vs `UNKNOWN(-1)`; F2 (low) u-11 `suspend_overdue` cutoff timestamp- vs day-granular; D1 u-07/u-08 subset files labelled map-draft-2 (content = 3.1). All unreachable from current writers/fixture; dispositioned to open-issues, fix before any live run.

Skill feedback to fold in: harness `--expect-mapping-version`; probe checklist for PL/SQL units; test day-granular compares with non-midnight timestamps.
Also closed this wave: u-06 re-run under map-draft-3.1 PASS all tiers (37 orphan lines quarantined, gap cleared, D-019).
