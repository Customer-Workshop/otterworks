# 04 — Progress ledger

## Write-target registry

Every write target is registered here **before** any load runs. A second unit claiming a
registered target is a collision: halt immediately, do not load, escalate.

| Target namespace | Owning unit | Registered at | Mode | Load status |
|---|---|---|---|---|
| `ow_tp_demo.customers` | `customers` | STOP A; claimed 2026-09-01 for the wave-1 load | write (delete + insert, scoped to `ns: demo`) | loaded — 25,000 docs, 8,333 embedded `attributes[]` |
| `ow_tp_demo_quarantine.customers` | `customers` | STOP A; claimed 2026-09-01 for the wave-1 load | write (delete + insert, scoped to `ns: demo`) | loaded — 81 field-level quarantine records |
| `ow_tp_demo.counters` | `customers` | STOP B, D3 approved 2026-09-01 | write (single upsert, `_id: demo:customers.cust_seq_no`) | loaded — `cust_seq_no` seeded to 125,000 |
| `ow_tp_demo.invoices` | `invoices` | STOP A | write | not loaded |
| `ow_tp_demo_quarantine.invoices` | `invoices` | STOP A | write | not loaded |

The wave-1 unit writes those three collections and nothing else; `ow_tp_demo.invoices` and
`ow_tp_demo_quarantine.invoices` stay untouched until wave 2 claims them. No collection is
claimed by two units, so there is no collision to escalate. The unit never drops a
collection: it deletes only `{ns: "demo"}` documents before reloading them.

Playbook 2 wrote nothing to the migration cluster and nothing to the source: the census is
`SELECT`-only and the mapping spec was validated offline by `recon.config.load_mapping_spec`.

Registered and already released: `ow_tp_demo._migration_preflight` (STOP A capability
probe; document inserted, read, deleted, collection dropped — no residue).

Explicitly **not** owned by this engagement, on the same cluster:
`ow_tp_billing_demo`, `ow_tp_demo1`, `ow_tp_mongodb_demo`, `ow_tp_mongodb_demo_quarantine`.
A write to any of them is a guardrail breach, not a collision to negotiate.

## Unit / wave ledger

| Wave | Unit | Mapping version | Tolerance version | Recon verdict | PR | Status |
|---|---|---|---|---|---|---|
| 1 | `customers` | 1.0.0 (STOP B approved) | 1 | **PASS** (live; T1 2 / T2 42 / T3 25,000 / T4 2 checks) | — | in flight — `!mongo_unit`, loaded + green, PR open |
| 2 | `invoices` | 1.0.0 (STOP B approved) | 1 | — | — | modeled — not started (wave 2) |

### Wave 1 `customers` load record

| Fact | Value |
|---|---|
| Source scope | `CONVERSION_BATCH_NO = 85559852` (`ns_batch_no("demo")`) |
| `ow_tp_demo.customers` | 25,000 documents, `_id = CUST_NO`, every document `ns: "demo"` |
| Embedded `attributes[]` | 8,333 EAV rows (duplicate `(ENTITY_ID, ATTR_NAME)` pairs preserved, D2) |
| `ow_tp_demo_quarantine.customers` | 81 records — 50 `unparseable_legacy_date` (D4), 31 `malformed_delimited_list` (D5); both are the STOP B-approved policy, no new quarantine class |
| Recon evidence | `.migration/recon/customers/result.json`, `report.md`, `recon.summary.md` |
| Harness | vendored pinned copy, `.migration/vendor/mongo-recon-harness` (H1 fix only) |

A unit is **done** only when its PR is merged into `tp-run/mongodb-20260831T232410Z` with a
green harness verdict recorded above. "Code written" and "recon run locally" are not done.

Declared coverage gaps (no unit will ingest these; see `00_context.md`): the Postgres
`documents` workload, the DynamoDB `files` workload, and the 16 `OW_BILLING` tables outside
the two units.

## Circuit-breaker log

Rule: 3 same-class failures across units halts the wave and escalates. Retrying past the
third is a breach.

| # | Date | Unit | Failure class | Action |
|---|---|---|---|---|
| — | — | — | — | no failures recorded |

H1/H2 in `06_census.md` are **harness findings raised before any run**, not unit failures:
nothing has executed to fail, so the breaker stays at 0.
