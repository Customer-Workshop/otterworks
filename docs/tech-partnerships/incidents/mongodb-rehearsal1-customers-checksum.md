# Incident: `customers-checksum` recon failure — MongoDB namespace `rehearsal1`

- **Detected by:** hand-triggered recon job (`scripts/tp_mongo/showcase.py --ns rehearsal1 run-job`),
  which fired the Devin automation webhook with `failing_checks=["customers-checksum"]`.
- **Failing report:** `docs/tech-partnerships/showcase/recon.rehearsal1.red.json`
  (`customers-checksum` expected `6b9bc920a1b8cb4508f36e16de73bbca`,
  actual `0700c4792261bba035e971d66ebf2153`; all other 10 checks passing).
- **Remediation:** autonomous Devin session (this PR).

## Confirmation

The remediation session independently re-ran recon against Atlas before touching
anything: `recon.rehearsal1.custchecksum.before.json` (in this directory) reproduces
the exact same single failing check and actual checksum as the webhook report.

The baseline manifest (`testdata/legacy/manifests/rehearsal1.json`) was regenerated
from the deterministic seeders (`make oracle-billing-seed NS=rehearsal1`,
`make seed-legacy NS=rehearsal1`) and reproduced the expected
`CUSTOMER_MASTER` checksum `6b9bc920a1b8cb4508f36e16de73bbca` byte-identically —
the baseline was valid; the target had drifted.

## Root cause

Post-migration data corruption (drift) in `ow_tp_mongodb_rehearsal1.customers`.
A field-by-field diff of Atlas `balances.current` against the Oracle source of
truth (`OW_BILLING.CUSTOMER_MASTER.CUR_BAL_AMT`, `conversion_batch_no` for
`rehearsal1`) found **exactly 100 documents** — the first 100 by `_id` ascending —
whose `balances.current` was shifted **+0.01** relative to the source:

```
ns=rehearsal1 atlas_docs=25000 oracle_rows=25000 mismatches=100
{"_id": "000c490f-2007-0191-edfd-6d08d7fd8135", "oracle_cur_bal_amt": 376.44, "atlas_balances_current": 376.45}
{"_id": "000eb3d6-679e-3778-a881-73181014b26d", "oracle_cur_bal_amt": 1050.87, "atlas_balances_current": 1050.88}
{"_id": "000f5b4a-b582-8e07-6f21-ac43402c7402", "oracle_cur_bal_amt": 56.17,   "atlas_balances_current": 56.18}
... (97 more, all +0.01)
```

The corruption was schema-valid (the `$jsonSchema` validator cannot catch a
plausible-looking balance), so only the recomputed checksum caught it. Counts
(25000), EAV entries (8333), and every other collection were unaffected.

## Remediation

Re-ran the idempotent customers migration for the namespace — no hand-edits to
target documents, no manifest changes, no code changes:

```
MONGODB_URI=$MONGODB_ATLAS_URI scripts/tp-run-deterministic.sh \
  uv run migrations/mongodb/customers/migrate.py --ns rehearsal1
# [migrate] ns=rehearsal1 customers=25000 eav_rows=8333 quarantined=81
```

Upserts keyed by the customer PK restored the 100 drifted balances from the
Oracle source. The source diff after the re-run reports `mismatches=0`.

## Proof

- `recon.rehearsal1.custchecksum.after.json` (in this directory): all 11 checks
  **pass**, including `customers-checksum = 6b9bc920a1b8cb4508f36e16de73bbca`.
- Idempotency: the migration was run a second time (same counts:
  `customers=25000 eav_rows=8333 quarantined=81`) and recon stayed green.
- Recon job re-triggered: `showcase.py --ns rehearsal1 run-job` → recon GREEN
  (11 checks), webhook not fired.
