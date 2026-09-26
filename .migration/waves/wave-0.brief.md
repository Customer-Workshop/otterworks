# Wave 0 close

Exceptions: 1 (w0-b01 FAIL-by-rule offline_no_live_recon; fixture recon PASS).
Landed: 0 of 1 batches PASS by rule (fixture/local evidence is never PASS).
Independent verify: RUN (fresh session devin-a43ac910a9f44615ad85cd776a72e636) — wave verdict fixture PASS, live recon pending customer run; w0-b01 PASS.
Failed: w0-b01 (offline_no_live_recon only).
Blocked on missing inputs: none. Held back by circuit breaker: none.
Awaiting manual merge: none (PR #1708 open; not mergeable on offline evidence).
Verifier findings: F1 codeVal int32 vs spec long (harness gap: key fields not type-checked); F2 missing (codeType,codeVal) index; F3-F5 informational.
Skill feedback: harness should type-check key fields; harness needs a per-collection selector; fixture bootstrap ~1 min when image cached.
Per batch:
- w0-b01: FAIL-by-rule. u-00-codes 32/32 loaded, 0 quarantined, fixture recon PASS (map-draft-2/tol-1), local target. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1708
