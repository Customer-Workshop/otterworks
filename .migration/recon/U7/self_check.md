# U7 pre-PR self-check evidence

Evidence produced for U7 against the deterministic `NS=demo` Oracle fixture. The
authoritative migration gate is `.migration/recon/U7/gate/result.json` (verdict PASS,
tiers 1/3/0 with no warnings); it was not modified.

Run order, so the artifacts read in the right sequence: load → transcript replay → write-path
probes → second load (drop+recreate, which also clears the probe documents) → gate →
gate rerun.

- [x] **Counts reconcile through the mapping.** The harness passed its tier-1 check:
  `BILLING_AUDIT_LOG` has 0 rows and `billing_audit_log` has 0 documents.
- [x] **Mapped field values reconcile.** 3 tier-2 aggregate checks passed and tier 3 ran a
  `full_diff` over a population of 0. This is the whole grade an empty source population can
  carry, and it is declared as such below rather than described as field coverage.
- [x] **NULL and missing cannot fail open.** The approved contract keeps source NULL as an
  explicit BSON null with the field always present; the loader's `vc()` rule implements
  `empty_string_is_null`. No row exists to exercise it, so it is declared unverified below.
- [x] **The legacy package conversion is pinned to the source, not to a reading of it.**
  `util_transcript.json` records 82 calls to `f_md5_uuid`, `f_code_desc`, `f_dt2str` and
  `f_str2dt` captured read-only from the fixture; `util_parity.json` replays all 82 through
  the port (with the migrated `codes` collection behind the lookup) and reports 82/82
  matched, including the ORA-06502 raw-length ceiling, `TO_CHAR` rendering of `.5`, the `YY`
  current-century pivot and every silently-nulled dirty date.
- [x] **`log_msg` is an independent audit write.** The probe opened a caller transaction,
  wrote through it, called `log_msg`, then aborted the caller transaction: the caller's
  write rolled back, the audit document survived, no `ClientSession` was passed, and the
  audit handle carried its own `{'w': 'majority'}` write concern.
- [x] **`log_msg` truncates and never raises.** 40 characters of module stored as 30, 5,000
  characters of message stored as 4,000, `_id` an `ObjectId`, `logged_at` at whole-second
  granularity, `ns` tagged; against an unreachable target it returned `False`, raised
  nothing, and still recorded `last_module`. The truncation is a **declared divergence**,
  not parity — see below.
- [x] **Retention is preserved without the scheduler job.** The TTL index read back from the
  target is `logged_at` ascending with `expireAfterSeconds = 7776000` (90 days), asserted by
  the loader on every run and re-read by the probes.
- [x] **Every migrated document is namespace tagged.** 0 rows migrate, so the load assertion
  is 0 = 0; every document the write path creates carries `ns: mongo_032752`, as the
  truncation probe confirms on a real inserted document.
- [x] **The loader is idempotent.** The rerun dropped and recreated only
  `ow.billing_audit_log`, rebuilt the TTL index, cleared the probe documents, and produced
  the same 0/0/0 counts. Both gate runs passed with identical tier counts.
- [x] **Only the registered Mongo target is written.** Oracle access is SELECT-only and
  `pkg_ow_util.log_msg` is never called against the source (it inserts); Mongo writes are
  limited to `ow.billing_audit_log`. `ow.codes` is read only.
- [x] **No secrets in source or evidence.** Credentials are referenced by environment
  variable name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`).
- [x] **No ungraded embed.** U7 has no embed at all, and `gate/result.json` carries no
  warnings.
- [x] **`make tp-validate-recon` is green for `U7.recon.json`, and `make tp-smoke` is green.**

## Declared divergence: audit acceptance rules

Read-only probes against the fixture (`audit_acceptance_probe.json`; anonymous PL/SQL
blocks, no table writes) show the source is narrower than it looks. `g_last_module` is
`VARCHAR2(30)` under `NLS_LENGTH_SEMANTICS=BYTE` on an `AL32UTF8` database, so
`g_last_module := p_module` raises `ORA-06502 (character string buffer too small)` before
the INSERT for any module over 30 bytes — 40 ASCII characters and 30 `ö` characters (60
bytes) both raise — and `WHEN OTHERS THEN ROLLBACK` then drops the event silently, leaving
`g_last_module` unchanged. The `SUBSTR(p_module, 1, 30)` in the INSERT is unreachable for
those calls. A message truncated to 4,000 characters can likewise exceed the 4,000-**byte**
column and lose the event at insert time.

The port deliberately does not reproduce that loss: per the unit spec the audit write is
unconditional, the Mongo target has no byte ceiling, and truncation is by characters. Audit
coverage is therefore strictly wider than the source, and `last_module` is recorded even for
an over-long module. Flagged for the wave gate as a semantics choice, not an accident.

## Declared unverified paths

- `BILLING_AUDIT_LOG` is empty at source, so no migrated document exercises the
  `LOGGED_AT` / `MODULE` / `MESSAGE` transforms. Tier 2 additionally defers the `module` and
  `message` aggregates to tier 3 under mapping v1.1, and tier 3's population is 0 — with no
  rows, that deferral grades nothing. The write path is covered by unit tests and the probes
  above, never by the harness verdict.
- Three-digit years in `f_str2dt` are not in the transcript: the port accepts them literally
  under the documented 1-4 digit shape, and that choice is unverified against the source.
- The PL/SQL callers of `log_msg` (`pkg_rating`, `pkg_invoicing`, `pkg_dunning`) belong to
  units U3-U6 and are not migrated here, so no migrated caller exercises the audit path in
  situ. No substitute caller was invented.
- TTL expiry timing is a background-sweep observation, not a contract: the probe records what
  it saw in its window. Retention itself is evidenced by the index specification.
- Fixture-only evidence (`run_mode=fixture`); the wave gate runs LIVE independently.

## Evidence artifacts

- `.migration/recon/U7/load_report.json`
- `.migration/recon/U7/load_report.rerun.json`
- `.migration/recon/U7/gate/result.json`
- `.migration/recon/U7/gate/report.md`
- `.migration/recon/U7/gate/recon.summary.md`
- `.migration/recon/U7/gate_rerun/result.json`
- `.migration/recon/U7/util_transcript.json`
- `.migration/recon/U7/util_parity.json`
- `.migration/recon/U7/supplemental.json`
