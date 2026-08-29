# 11 — Quarantine reason codes

Every quarantined row carries exactly one `quarantine_reason` from this table, plus `ns`,
the source table or file it came from, and the raw source payload. The codes are closed:
a child that meets a rejection cause not listed here **stops and reports** so a code is
added centrally, rather than inventing one or folding it into `OTHER`. There is no `OTHER`.

Quarantine is accounting, not disposal. For every unit,
`loaded_rows + quarantined_rows == source_rows`, the quarantine count is reported next to
every money figure (`.migration/03_recon_tolerances.md`), and a unit whose quarantine rate
exceeds **5%** of source rows halts and escalates (`STOPA-QUARANTINE`).

| Code | Cause | Where it fires | Dictionary reference |
|---|---|---|---|
| `BAD_DATE` | A `VARCHAR2` date column holds a value no format in the dictionary can parse. | `bronze_wide` (`CUSTOMER_MASTER` `VARCHAR2(9)` dates), `bronze_hist` (`HIST_DT`) | D-06 |
| `DATE_INVALID` | The value parses structurally but is not a real date (month `13`, day `00`, `00000000`). | `bronze_custbill` (`BILL-DATE`), `bronze_wide` | D-06, T4 |
| `AMT_NON_NUMERIC` | A money field is not numeric. The legacy CUSTBILL parser coerces this to `0` via awk `$4+0`; the target refuses to, because a silent zero is indistinguishable from a real zero amount. | `bronze_custbill` (`BILL-AMT`) | D-21 |
| `RECORD_SHORT` | A fixed-width record is shorter than its copybook length, so column positions cannot be trusted. The legacy parser pads it into empty fields instead. | `bronze_custbill` (`CBCUST01`, 65 bytes) | D-21 |
| `ENC_INVALID` | A byte sequence cannot be decoded under the unit's declared encoding, or a non-ASCII byte appears in a byte-positional feed. | any unit; `bronze_custbill` treats it as fatal to slicing | D-25 |
| `KEY_NULL` | A column in the unit's declared natural `MERGE` key is null, so the row cannot be made idempotent on rerun. | any unit with a `MERGE` target | D-14 |
| `KEY_DUPLICATE` | Two source rows collide on the declared natural key with differing payloads, so `MERGE` cannot resolve them deterministically. | any unit with a `MERGE` target | D-14 |
| `FK_ORPHAN` | A row references a parent that does not exist and the unit's contract declares the reference mandatory. Not used where the source itself has no FK: `bronze_hist` rows for deleted customers are **loaded**, not quarantined. | `silver_*` units only | D-19 |
| `CODE_UNKNOWN` | A coded value has no matching `CODES` row for its `code_type` (the rule `trg_usage_events_check` enforced in-source). | `bronze_core` (`USAGE_EVENTS.kind_cd`), `silver_*` | D-16, STOPA-TRIGGERS |
| `NUMERIC_OVERFLOW` | A source value does not fit the declared target decimal type. Never widen the type or round to make it fit; money is `DECIMAL(14,2)` and any silent rescale is a parity break. | any unit | D-23, T6 |

Two rules that keep this table honest:

- **A quarantined row is not a deleted row.** The raw payload is retained in the unit's
  `quarantine_<unit>` table, so a rejected row can be replayed after a dictionary fix
  without re-reading Oracle.
- **A quarantine is not a licence to pass.** A green recon over a shrunken population is
  the failure mode this table exists to prevent, which is why the rate is capped at 5% and
  the count sits beside every money figure rather than in a separate report.
