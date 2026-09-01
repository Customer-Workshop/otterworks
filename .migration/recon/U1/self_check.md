# U1 pre-PR self-check evidence

This run covers U1 (`customers` + `customer_master_hist`) against the freshly seeded
NS=demo Oracle fixture. The authoritative artifact is
`.migration/recon/U1/gate/result.json`; its verdict is **PASS**, with Tier 1 PASS
(3 checks), Tier 2 PASS (311 checks), and Tier 3 PASS (33,333 checks). The gate
ran in `mode: live`; this child evidence is `run_mode: fixture`, not the parent's
uncontended live proof. Mapping `1.1`, canonicalization `1.1`, tolerances `1.0`,
seed `0`, and the fixture's batch `85559852` were used.

- [x] **NULL and missing attribution cannot fail open.** `scripts/tp_mongo/load_u1.py`
  maps source NULL to an explicit BSON null, including for the 17 grading-blanked
  fields whose write types are deterministically re-derived from `source_type`;
  unsupported blank types and unknown mapping pairs raise instead of falling back.
  The 19 `null_missing_equiv` numeric fields are deferred by the approved amendment
  to the Tier 3 keyed diff, where their per-row values pass.
- [x] **Every reference is scoped to the unit namespace.** The loader accepts only
  `ow_tp_mongodb_032752` and only the two U1 collections registered in
  `.migration/04_progress.md` (`ow.customers`, `ow.customer_master_hist`); no
  quarantine collection is used because the embed has 0 orphans. Both load reports
  record `ns_docs_after` 25,000 / 0.
- [x] **No DDL drops, replaces, or alters a shared table.** Oracle access is
  SELECT-only with source-load concurrency 1; drops are limited to the two owned
  MongoDB collections.
- [x] **Idempotency proven by rerun, not inferred.** Two full loads,
  `.migration/recon/U1/load_report.json` and
  `.migration/recon/U1/load_report.rerun.json`, both show dropped/recreated true
  with identical counts: customers 25,000 source/inserted/docs_after/ns_docs_after;
  embedded attributes 8,333 source and after across 7,075 roots; and
  `customer_master_hist` 0/0/0/0. A direct post-rerun count confirmed exactly
  25,000 customer documents with `ns = mongo_032752` and 0 with any other `ns`.
- [x] **Recon values recomputed from the target platform.** The gate read Atlas live
  through the harness adapters and recomputed all values. Tier 3 ran a full keyed
  diff over 25,000 customer roots and the empty history population; declared
  `customers.attributes` elements were value-graded (8,333), with no UNGRADED embed.
- [x] **Index plan is exactly the approved plan.** `customers` reports `_id_`,
  `conversion_batch_no_1`, and `tenant_id_1`; `customer_master_hist` reports `_id_`
  only. No index on `attributes.*` and no shard key were added.
- [x] **Parity-versus-tolerance decision comes from the contract.** Tolerances `1.0`
  and canonicalization `1.1` were passed unmodified. The two Tier 2 deferral
  classes introduced by the approved grading-only amendment (NULL-inclusive
  distinct counts and all-NULL sums) are deferred to Tier 3 rather than reported
  as findings; the loaded NULL/type contract is unchanged.
- [x] **App-path parity evidenced separately, as declared.** The balances rewrite
  is evidenced by `.migration/recon/U1/parity/balances_parity.json`, which reports
  PASS with customer_count 25,000 and matching Oracle/MongoDB totals. This is unit
  evidence, not a harness verdict.
- [x] **No secrets or requester identity in source, evidence, or history.** Secrets
  are referenced by environment-variable name only (`OW_BILLING_FIXTURE_DSN`,
  `MONGODB_ATLAS_URI`, `OW_BILLING_MONGO_URI`); reports record names, never values.
- [x] **Unverified paths declared.** `customer_master_hist` is empty at source
  (0 rows), so the trigger-replacement history write path is unit-tested only and
  no migrated row exercises it. The deployed HTTP reader path with
  `OW_BILLING_MONGO_URI` set is also unexercised.
- [x] **`make tp-smoke` is green** (verified for this branch after the U1 loader and
  evidence updates).

## Tier 2 amendment coverage

The approved v1.1 grading amendment defers the 19 NULL-bearing numeric
`customers` fields to Tier 3: 17 all-NULL fields (`PHONE3_TYPE_CD`,
`PHONE4_TYPE_CD`, `TERRITORY_CD`, `CHANNEL_CD`, `RATE_CLASS_CD`, `LTD_BILLED_AMT`,
`YTD_PAID_AMT`, and `UDF_AMT_01..10`) and 2 partially NULL fields
(`SUB_STATUS_CD`, `CREDIT_LIMIT_AMT`). Their native aggregate semantics differ
between Oracle and MongoDB, while the full keyed diff confirms the loaded values
match and preserves explicit BSON nulls.

## Environment note

The Oracle fixture was freshly seeded as NS=demo and verified at
`CUSTOMER_MASTER=25,000`, `ENTITY_ATTR_VALUE=8,333`, and
`CUSTOMER_MASTER_HIST=0`; Oracle remained read-only after seeding. The
`/home/ubuntu/.venvs/recon` environment was rebuilt from the plugin harness source,
with `pymongo`, `oracledb`, `flask`, and `pytest` installed; `recon selftest` passed.
