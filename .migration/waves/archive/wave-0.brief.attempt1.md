# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 7s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- *.log is gitignored repo-wide; apply/load log evidence under .migration/recon/<unit>/ needs `git add -f`.
- --routine-dependencies requires the file to already be committed in HEAD (git cat-file check) and the default path is .migration/units/<unit>/ which children may not write; the brief should say to commit .migration/recon/<unit>/dependencies.json first and pass the flag.
- Guard: doctor/recon/loader invocations that need OW_BILLING_RO_DSN must inject it in-process via a ~/bin python wrapper; `source`-ing an export script is blocked as redefining a trusted name.
- psycopg >= 3.2: Cursor.copy() is a context manager, not the Copy object; calling write_row on it deadlocks the connection lock during rollback. Loader must use `with cur.copy(...) as copy`.
- rerun-proof: a unit whose declared shape is unchanged since its prior committed proof can never produce a supported evolved leg (pre_shape == fresh shape), so merge_eligible is unreachable without a human override; the harness needs an explicit rule for no-evolution units.

Per batch:
- w0-lakebase-scaffold: FAIL. Lakebase billing schema + 4 reference tables (918 rows) landed on mig-20260927c-w0 with live recon PASS on all tiers; not merge-eligible only because rerun-proof's evolved leg is 'unsupported' (shape unchanged since prior proof) — needs a merge_override or harness rule at wave close. PR #1729 open, CI green. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1729
