# U4 pre-PR self-check evidence

Evidence produced for U4 against the deterministic `NS=demo` Oracle fixture. The
authoritative migration gate is `.migration/recon/U4/gate/result.json` (verdict PASS,
tiers 3/15/820); it was not modified.

This is a child self-check (`run_mode=fixture`): the source is the local deterministic
read-only `NS=demo` Oracle fixture. The harness CLI models that with `--mode live`
(its modes are `live`, `snapshot`, `continuous`), as the U0-U2 wrappers do; the parent
runs the independent live gate.

- Harness tier 1 `counts_through_mapping`: **PASS** (3 checks).
- Harness tier 2 `per_field_aggregates`: **PASS** (15 checks).
- Harness tier 3 `keyed_diffs`: **PASS** (820 checks).

- [x] **Root counts reconcile.** The harness passed 3 tier-1 checks: `usage_events` 814
  docs, `rating_periods` 3 docs, `rating_results` 3 docs, each equal to its source table.
- [x] **Mapped field values reconcile.** The harness passed all 15 tier-2 aggregate
  checks and all 820 tier-3 keyed-diff checks, with `full_diff` coverage over every
  document in all three collections (814 / 3 / 3); no embeds exist in this unit.
- [x] **Stored-procedure behavior is preserved.** All 8 recorded Oracle rating
  transcripts replay PASS against the migrated service
  (`.migration/recon/U4/parity_rating.json`), covering `fn_usage_rating`,
  `fn_usage_summary`, and `sp_finalize_rating`, including the double rollover cap, the
  101-unit tier break, suspension proration, and `GREATEST(quota-used,0)` stored
  rollover.
- [x] **Application port is unit-tested.** `pytest scripts/tp_mongo/tests
  scripts/tp_mongo/test_load_u2.py -q` reports 31 passed, covering `md5_uuid`,
  `ADD_MONTHS` clamping, day-granularity window inclusivity, the NULL-plan path, the
  rollover cap, half-away-from-zero rounding, suspension proration, the
  insert-then-update upsert, and usage-event rejection messages.
- [x] **Every migrated document is namespace tagged.** Load assertions report 814, 3, and
  3 namespace-tagged documents, equal to the per-collection source rows.
- [x] **The loader is idempotent.** The rerun dropped and recreated only the three owned
  collections and produced identical numbers (814 / 3 / 3 source rows, inserted,
  docs_after, and ns_docs_after) with no doubling, and it cleared the finalize writes made
  by the `sp_finalize_rating` transcript replay before the gate ran.
- [x] **Indexes are as contracted.** `usage_events` carries
  `tenant_id_1_occurred_at_1_kind_cd_1` and `rating_results` carries `period_id_1`,
  alongside the implicit `_id_` indexes.
- [x] **Only the registered Mongo targets are written.** Oracle access is SELECT-only;
  writes are limited to `ow.usage_events`, `ow.rating_periods`, and `ow.rating_results`
  in `ow_tp_mongodb_032752`.
- [x] **No secrets are included in source or evidence.** Credentials are referenced by
  environment-variable name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`).
- [x] **No ungraded values.** `gate/result.json` carries no warnings and no UNGRADED
  finding; the unit has no embedded arrays.
- [x] **NULL is explicit, not missing.** Source NULL is written as BSON null for
  `quota_units`, `rollover_units`, `billable_units`, `overage_amount`, and
  `subscription_id`, and the service preserves the source NULL propagation.

## Declared unverified paths

- The audit-log write is suppressed: `pkg_ow_util.log_msg` targets `BILLING_AUDIT_LOG`,
  which unit U7 owns. The service keeps the seam and the source message strings, so the
  audit write path itself is unexercised here.
- The Mongo-backed `subscriptions` read path is unexercised pending U3. Covering
  subscriptions are served from a read-only Oracle `SUBSCRIPTIONS` extract for parity, and
  from the static seam in unit tests; `MongoSubscriptionSource` is not exercised against a
  loaded collection.
- The `UNKNOWN` usage-kind `DECODE` default is not exercised: the fixture contains only
  kind codes 1, 2, and 3.
- This is fixture-only evidence (`run_mode=fixture`); the harness ran against the
  read-only `NS=demo` Oracle fixture and the wave gate runs LIVE independently.

## Evidence artifacts

- `.migration/recon/U4/load_report.json`
- `.migration/recon/U4/load_report.rerun.json`
- `.migration/recon/U4/parity_rating.json`
- `.migration/recon/U4/gate/result.json`
- `.migration/recon/U4/gate/report.md`
- `.migration/recon/U4/gate/recon.summary.md`
- `.migration/recon/U4/mapping/u4.json`
