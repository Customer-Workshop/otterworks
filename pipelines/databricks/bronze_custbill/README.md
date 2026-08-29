# bronze_custbill

Fixed-width CUSTBILL feed (copybook `CBCUST01`) into `ow_tp.bronze.custbill_records`,
with rejects in `ow_tp.bronze.quarantine_bronze_custbill`. Landing prefix is
`/Volumes/ow_tp/bronze/landing/<ns>/custbill/`.

| Path | Role |
| --- | --- |
| `notebooks/bronze_custbill.py` | The pipeline. Databricks notebook task deployed by `infrastructure/terraform-databricks/jobs_bronze_custbill.tf`; also importable so evidence runs execute the shipped SQL rather than a copy of it. |
| `tools/make_custbill_field_samples.py` | Deterministic field-level sample generator (implied-decimal, non-numeric amount, invalid date, short record, non-ASCII, overlength, trailer mismatch, partial transfer). |
| `tools/run_bronze_custbill.py` | Evidence runner: lands files, runs the pipeline twice, recomputes every acceptance check from the target, writes the recon report. |
| `bronze_custbill.recon.json` | Measured recon report for `ns=demo`. |

## Behaviour worth knowing

- A `.dat` is ingested only when a `<name>.dat.sha256` completed-transfer marker matches the
  landed bytes, so a file still being written is skipped rather than half-loaded.
- Bytes 1-65 are sliced per the copybook. Only `CUST-ID`, `CUST-NAME` and `CURRENCY` are
  right-trimmed; `BILL-DATE`, `BILL-AMT` and `REC-TYPE` keep their padding, and surplus bytes
  past 65 are kept in `raw_overflow` instead of being truncated.
- `BILL-AMT` is `PIC 9(10)V99`: digits are integer cents, materialised as `DECIMAL(14,2)`.
- Quarantined rows keep the raw record plus the value the legacy parser would have produced,
  so a parity replay stays possible without adopting the legacy coercion as truth.
- A trailer count that disagrees with the detail count rejects the whole file.
- No files present is a normal poll: nothing is written and prior output is left intact.
- `MERGE` on `(ns, record_uid)` makes a rerun a no-op.

## Reproducing the evidence

```sh
export DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN"

# golden baseline: the legacy parser's own .psv output, frozen clock
OTTERWORKS_LEGACY_ROOT=<root> scripts/tp-run-deterministic.sh bash etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh

python3 pipelines/databricks/bronze_custbill/tools/run_bronze_custbill.py \
  --ns demo --landing-source <staged files> --baseline <root>/parsed \
  --out pipelines/databricks/bronze_custbill/bronze_custbill.recon.json

make tp-validate-recon FILE=pipelines/databricks/bronze_custbill/bronze_custbill.recon.json
```
