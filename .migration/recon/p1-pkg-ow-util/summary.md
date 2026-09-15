# p1-pkg-ow-util (U-20, wave 0 / batch w0-a) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
Not an official harness verdict: D10-01 was denied, so Oracle is read over JDBC with a
repo-local source adapter while every tier, tolerance and canonicalization rule stays the
harness's own. See `DEGRADED.md`, `result.json`, `recon.summary.md`.

## D2-01 — MD5/UUID parity

`billing.f_md5_uuid` is compared against the Oracle package body's own expression
(`STANDARD_HASH(UTL_RAW.CAST_TO_RAW(x),'MD5')` formatted 8-4-4-4-12) over the inputs the
estate actually hashes. Three Tier-4 ops, all PASS, zero mismatched values:

| op | input vector (distinct) | rows |
|---|---|---|
| `f_md5_uuid_vs_oracle_rating_result_inputs` | `rating_results.period_id` | 3 |
| `f_md5_uuid_vs_oracle_invoice_inputs` | `invoices.period_id \|\| 'invoice'` | 2 |
| `f_md5_uuid_vs_oracle_invoice_line_inputs` | `invoice_lines.invoice_id \|\| line_no` | 2 |

The target side reads the same inputs from `billing.md5_parity_input`, seeded over the
read-only JDBC path by `databricks/migration/lakebase/w0a_seed_md5_vectors.py` (`TRUNCATE`
then insert, so a reseed is a no-op). Inputs are distinct per vector: the function is
deterministic, so a repeated input adds nothing and the seed table keys on it.

NULL, empty-string and non-ASCII inputs are covered by
`databricks/migration/lakebase/w0a_md5_parity.py` rather than by an op: they do not occur in
the estate's own call sites, so putting them in the gate's input set would compare rows that
no source table can produce.

## Idempotency

The gate was rerun unchanged and the two results are identical apart from `generated_at` and
the cost block (`idempotent: true`). The bronze loads of this wave are digested directly from
the target platform by `databricks/migration/transport/target_state_digest.py`
(SHA-256 over sorted per-row SHA-256 hashes): `codes` 32 rows, `customer_master` 25,000,
`invoice_header` 18,750, `invoice_line` 150,000, each unchanged across a rerun.

## Date parity (f_str2dt / f_dt2str)

`databricks/migration/lakebase/w0a_date_parity.py` compares Oracle and Lakebase over 21
vectors from the live estate — unpadded days, punctuation separators, four-digit years,
lowercase month names, leading/trailing whitespace, the two-digit-year pivot, and
unparseable values. Zero mismatches. Unparseable input returns NULL on both sides; that NULL
is legacy behaviour and stays in the declared anomaly set.

## NOT DATA-PROVEN / unverified paths

- `billing_audit_log` is empty on both sides: schema parity and an empty-set assertion only.
- Tiers 5–7 source-side constraint, index and identity metadata: the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. This is also why
  the result is not merge-eligible — the harness withholds merge eligibility from any run
  carrying an unverified warning.
- `pkg_ow_util.f_md5_uuid` is not called through the package: the read-only user has no
  EXECUTE on it (ORA-41900) and granting it would be DDL on a read-only source. The proof is
  that the algorithm matches, not that the entrypoint is reachable.
- `f_code_desc` is graded at the wave-1 CODES gate (it needs `billing.codes`); `f_str2dt` is
  graded at each string-date unit's `str_date_parse` op.
- `log_msg`: Oracle's `PRAGMA AUTONOMOUS_TRANSACTION` has no in-database equivalent here —
  `dblink` and `postgres_fdw` are both unavailable on the project and extension creation is
  refused. A caller that rolls back keeps its audit rows on Oracle and loses them on
  Lakebase. Declared divergence P1-D1a; it needs an out-of-database writer and an owner at
  STOP E, and parity is not claimed for it.
