# Wave 1 close

Landed: 0 of 3 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w1-b01, w1-b02, w1-b03.
Blocked on missing inputs: none.
Held back by circuit breaker: none.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- App-parity replay via per-call app connections exhausts Oracle Free listener; reuse one connection under source concurrency 1
- Brief references load_codes.py as the accepted loader pattern but it does not exist on the run branch.
- CI pins Python deps in .github/workflows/tp-golden-smoke.yml rather than requirements.txt; brief should tell children to add new driver pins there too
- Fixture counts (25001 customers / 8337 EAV) differ from the seeder's nominal 25000/8333 because 04_upgrade_static.sql adds an admin customer and 4 static attributes; brief says 33338 rows.
- Oracle profile/harness has no quarantine-aware grading rule: date_string_to_date and csv_to_array keep/split unparseable values while 05_decisions mandates quarantine, so a correct loader can never pass Tier 3 on planted dirty data; needs an `unparseable: null` rule param or grader awareness of _quarantine.
- Profile should say how to grade $lookups into another unit's collection (codes) absent from a child's namespace
- Profile should state how Decimal128 scale is rendered back to Oracle NUMBER strings (normalize()) so API parity holds
- Recon harness salts keys in findings, so quarantine<->finding correspondence can only be proven at collection/field/count level, not per key.
- brief referenced load_codes.py on the run branch as the loader pattern but it is not present there
- dbx_guard rejects cursor.execute(<variable>); generated SQL must be an inline literal/f-string in the call.
- harness has no per-collection flag; child must materialize a verbatim mapping-spec subset file containing only its collections
- legacy-billing CI runs uv with a fixed --with dep list lacking pymongo; pymongo imports in shared modules must be lazy (or the CI dep list updated by the orchestrator)
- make tp-smoke Go/Node stages not runnable on the child box (go missing); rely on CI or add toolchains to blueprint
- oracle profile: oracledb fetch_decimals=True yields Decimal('149') for integral NUMBER(12,2); Mongo read path must format Decimal128 via normalize()+'f' and str(Int64) to be byte-identical to the Oracle facade JSON
- recon venv needs psycopg[binary] to run the existing test_facade.py alongside the new tests
- tp-golden-smoke CI installs test deps via `uv run --with ...` in both Makefile and workflow; new app deps must be added in both places.

Per batch:
- w1-b01: FAIL. u-01-tenancy landed in PR #1712 (unmerged, CI green): Mongo tenancy read backend + loader, 143 rows loaded with 0 quarantined, fixture/local recon PASS (map-draft-2/tol-1, merge_eligible=false) and 282-op app parity PASS; status is not PASS because live recon is impossible offline, so fixture evidence is not merge evidence. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1712
- w1-b02: FAIL. u-02-customers loader + /customer,/me Mongo slice landed in PR #1716 (unmerged, CI green, contract PR #1710); fixture recon target_class=local FAIL: T1/T2 PASS, T3's 63 diffs are exactly the 63 quarantined values (bad_date 50, malformed_csv 13) - harness vs quarantine decision conflict (tolerance_ambiguous); live recon not possible (offline). https://github.com/Cognition-Partner-Workshops/otterworks/pull/1716
- w1-b03: FAIL. u-03-invoicing-core landed in PR #1711 (CI green, unmerged): loader + Mongo invoice/lines read path, fixture recon PASS on local target (19 rows, quarantine 0, idempotent); status FAIL-by-rule only because live/snapshot recon is impossible in this offline engagement. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1711
