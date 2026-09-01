# U1 pre-PR self-check evidence

Evidence produced for U1 (customers + customer_master_hist) against this VM's own
deterministic NS=demo fixture — `run_mode: fixture`, a child self-check, not the parent's
uncontended live proof. The authoritative artifact is
`.migration/recon/U1/gate/result.json`: **verdict FAIL**, Tier 1 PASS (3 checks),
Tier 2 FAIL (311 checks, 36 findings), Tier 3 PASS (33,333 checks). It was not modified,
and no verdict is restated here by hand. Mapping `1.0`, tolerances `1.0`,
canonicalization `1.0`, seed `0`, mode `live`, batch `85559852`.

- [x] **NULL and missing attribution cannot fail open.** `scripts/tp_mongo/load_u1.py` builds every converter from the approved spec pair (`bson_type`/`source_type`) and maps source NULL to an explicit BSON null, so the field is always present and NULL never collapses into missing; an unknown pair raises instead of falling back. Tier 2 deferred the 258 `empty_string_is_null`/`rstrip_spaces` fields to Tier 3, which value-graded every key post-canonicalization.
- [x] **Every reference is scoped to the unit namespace.** The loader accepts only `ow_tp_mongodb_032752` and only the two U1 collections registered in `.migration/04_progress.md` (`ow.customers`, `ow.customer_master_hist`); no quarantine collection is used, because the embed has 0 orphans. Both load reports record the target db and `ns_docs_after` 25,000 / 0.
- [x] **No DDL drops, replaces, or alters a shared table.** Oracle access is SELECT-only (source-load cap 1, single serialized read); drops are limited to the two owned MongoDB collections.
- [x] **Idempotency proven by rerun, not inferred.** Two full loads: `load_report.json` and `load_report.rerun.json` both show `dropped`/`recreated` true with identical counts (customers 25,000 source/inserted/docs_after/ns_docs_after; embedded attributes 8,333 source and 8,333 after across 7,075 roots; `customer_master_hist` 0/0/0/0), and a post-rerun shell count confirmed `customers` holds exactly 25,000 documents with `ns = mongo_032752` on all of them and 0 documents carrying any other `ns` — no doubling.
- [x] **Recon values recomputed from the target platform.** The gate read Atlas live through the harness adapters (`--mode live`); nothing was copied from a previous report. Tier 3 ran as a full keyed diff — `customers` `full_diff` over population 25,000, `customer_master_hist` `full_diff` over population 0, and `embeds_graded` `customers.attributes: 8333`, so every declared element key and field was value-graded, no sampling and no UNGRADED embed.
- [x] **Index plan is exactly the approved plan.** `customers` reports `_id_`, `conversion_batch_no_1`, `tenant_id_1`; `customer_master_hist` reports `_id_` only. No index on `attributes.*`, no shard key.
- [x] **Parity-versus-tolerance decision comes from the contract.** Tolerances 1.0 and canonicalization 1.0 were passed unmodified; the 36 Tier 2 findings are reported to the engagement as PROFILE FEEDBACK plus an amendment request, exactly as `.migration/contracts/U1.md` pre-declared, and were **not** worked around in the load, the tolerance record, or the verdict.
- [x] **App-path parity evidenced separately, as declared.** Harness Tier 4 is not reachable from the `recon` CLI, so the `BALANCES_SQL` (RPT-114) rewrite is evidenced by `scripts/tp_mongo/parity_balances_u1.py`: `parity/balances_parity.json` verdict **PASS**, Oracle and MongoDB both shaped to `customer_count 25000`, `current_balance_total "39799450.31"`, `past_due_total "7330214.66"`. This is unit evidence, not a harness verdict.
- [x] **No secrets or requester identity in source, evidence, or history.** Secrets are referenced by env-var name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`, `OW_BILLING_MONGO_URI`); the load reports and the parity JSON record `secret_names`, never values.
- [x] **Unverified paths declared.** `customer_master_hist` is empty at source (0 rows): the collection is created and graded empty, so the trigger-replacement history write path (`scripts/tp_mongo/customer_write_path.py`) is unit-tested only and no migrated row exercises it. The MongoDB balances backend is exercised by the parity script and unit tests; the HTTP reader path with `OW_BILLING_MONGO_URI` set in a deployed service is not exercised here.
- [x] **`make tp-smoke` is green** (verified on this branch before the load handoff; no code changed in this handoff).

## Tier 2 findings (36) — pre-declared null-semantics gap

All 36 findings are in `customers` and fall into exactly two classes over the 19
NULL-bearing numeric columns named in `.migration/contracts/U1.md`:

- `aggregate_distinct_count` (19): Oracle `COUNT(DISTINCT col)` excludes NULLs while the
  target distinct grouping counts the null group — 17 all-NULL columns report source `0`
  vs target `1`, plus the two partially NULL columns `SUB_STATUS_CD` (2 vs 3) and
  `CREDIT_LIMIT_AMT` (4 vs 5).
- `aggregate_sum` (17): Oracle `SUM` over an all-NULL column is NULL while the target
  `$sum` of an all-null field is `0` — source `None` vs target `0.0` on the 17 all-NULL
  columns (`SUB_STATUS_CD` and `CREDIT_LIMIT_AMT` are not all-NULL, so their sums agree).

Columns: `PHONE3_TYPE_CD`, `PHONE4_TYPE_CD`, `TERRITORY_CD`, `CHANNEL_CD`,
`RATE_CLASS_CD`, `LTD_BILLED_AMT`, `YTD_PAID_AMT`, `UDF_AMT_01..10` (all-NULL);
`SUB_STATUS_CD`, `CREDIT_LIMIT_AMT` (partial). No finding falls outside these two classes
or these 19 columns, and Tier 3's full keyed diff over the same columns is clean — the
per-row values match, so this is a cross-engine aggregate-semantics difference, not a load
defect. No load-side representation satisfies both this comparison and the approved
"source NULL -> explicit BSON null, NULL != missing" rule.

## Environment note

`/home/ubuntu/.venvs/recon` is the locally rebuilt harness venv from the plugin-provided
source (`recon selftest`: PASS, 9 rules); the runner prefers the blueprint path and falls
back to `recon` on PATH. Flask was added to that venv so the parity script can import the
legacy report module by path. The Oracle fixture container was reused as-is (healthy,
CUSTOMER_MASTER 25,000 / ENTITY_ATTR_VALUE 8,333 / CUSTOMER_MASTER_HIST 0, batch
85559852) — no reseed was needed and Oracle was read-only throughout.
