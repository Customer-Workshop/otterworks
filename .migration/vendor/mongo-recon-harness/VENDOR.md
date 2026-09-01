# Vendored recon harness (pinned)

Upstream: `mongo-recon-harness` **0.1.0**, shipped in plugin
`account-upload_org-default-8486a6b8` **v0.1.2**
(`skills/mongo-recon-harness/harness`). Copied verbatim, then carrying exactly one
functional change, approved at STOP B as decision **H1** option (b).

Wave 1 and wave 2 run their recon gate against this copy so the verdict is reproducible
from the repository alone, at a fixed harness revision, instead of whatever plugin version
happens to be installed on the machine that runs it.

## The one change: Tier 2 `sum` is not type-aware

`recon/tiers.py`, `tier2_aggregates`.

For a column with no numeric sum — a `VARCHAR2`/`CHAR` column, or a numeric column whose
every row is NULL — the two sides answer the same fact in different vocabularies:

| Side | Expression | Answer |
|---|---|---|
| Oracle | `SELECT SUM(CUST_NAME) FROM …` | raises `ORA-01722`; the adapter records `sum: None` |
| Oracle | `SELECT SUM(ZIP) FROM …` (digits in a `VARCHAR2`) | a number, via implicit string→number conversion |
| MongoDB | `{"$sum": "$cust_name"}` / `{"$sum": "$zip"}` | `0` (`$sum` ignores non-numeric input) |

So every string field produced an `aggregate_sum` finding on a byte-perfect load — 40 of the
42 `customers` fields, and Tier 2 is a gating tier. Worse, a field carrying
`empty_string_is_null` or `null_missing_equiv` has its other four statistics deferred to
Tier 3 by design, so `sum` was its *only* Tier 2 check: the tier could not pass.

The fix makes the `sum` comparison type-aware — it runs only where the mapping declares a
summable `bson_type` and the source reports a numeric sum — and records the skipped fields
in the tier's `stats` under `sum_not_comparable` so the evidence stays visible in
`result.json`. Nothing else is loosened: `null_rate`, `distinct_count`, `min` and `max`
still run, and every skipped field is still compared value-by-value by Tier 3's keyed
post-canonicalization diff.

Regression tests, both of which fail against the unmodified upstream file:
`tests/test_tiers.py::test_tier2_skips_sum_when_source_has_no_numeric_sum` (source `None`)
and `::test_tier2_skips_sum_for_a_numeric_looking_string_column` (source converts, target
answers `0`).

## Upstream feedback

This is a harness defect, not a profile trap: any Oracle or SQL Server source with a text
column hits it on the first green load, and a text column holding digits (a zip, a legacy
account number) hits it even where the engines both produce a number. The change is offered
upstream as-is; when a plugin release carries an equivalent fix, delete this directory and
point the gate back at the plugin copy — the mapping spec, tolerances and canonicalization rules are unaffected.

## Running the gate against this copy

```bash
python3 -m venv ~/.venvs/recon
~/.venvs/recon/bin/pip install -e ".migration/vendor/mongo-recon-harness[all]"
~/.venvs/recon/bin/recon run --unit customers --family oracle …
```
