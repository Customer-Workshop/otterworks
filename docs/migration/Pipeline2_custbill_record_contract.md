# Pipeline 2 — CUSTBILL record contract (wave 0)

Status: **proposed, pinned at STOP C**. Nothing in pipeline 2 is built before this is approved.

This is the behavioural contract for the fixed-width CUSTBILL extract and everything the
legacy chain derives from it. It is written from **observed legacy behaviour**, not from the
copybook comment in `parse_custbill_fixedwidth.sh`. Where the legacy is wrong, the wrong
behaviour is the contract (`.migration/06_decisions.md`, dirty-output rule). Every clause
below carries an evidence tag; the probe fixture and the captured legacy outputs are in
`databricks/migration/p2/baseline/`.

Evidence was produced by running the real legacy scripts (`sftp_ingest_poll.ksh`,
`parse_custbill_fixedwidth.sh`, `finance_excel_report.pl`) over a purpose-built probe file,
under the repo's `legacy-etl-demo` harness.

## 1. Physical file

| Clause | Contract | Evidence |
|---|---|---|
| C-1.1 | Files are picked up by glob `CUSTBILL*.dat` from the SFTP drop. Anything else is ignored. | source |
| C-1.2 | Record separator is LF. A file may use CRLF; the CR is **not** stripped. For a full-length 65-byte record the CR lands at byte 66 and falls outside every slice, so CRLF files parse identically to LF files. For a short record the CR lands **inside** a field and is carried through. | `P-CRLF` |
| C-1.3 | There is **no character encoding**. Slicing is by **byte** offset. A multi-byte UTF-8 character in any field shifts every later field by the extra byte count and corrupts the record. | `P-UTF8` |
| C-1.4 | Target reads the file as binary, slices bytes, and decodes each field as ISO-8859-1 so every byte round-trips losslessly and no decode ever fails. Exports re-encode ISO-8859-1. | derived from C-1.3 |
| C-1.5 | A data record is 65 bytes. Length is **not** validated. A short record yields empty trailing fields; a long record has the surplus bytes discarded. | `P-SHORT`, `P-LONG` |
| C-1.6 | An empty input file produces an empty (0-byte) parsed file, not an error. | `P-EMPTY` |
| C-1.7 | A blank line produces a parsed **row** (all fields empty), it is not skipped. | `P-BLANK` |

## 2. Field layout (1-based, inclusive, **bytes**)

| Field | Bytes | Width | Copybook |
|---|---|---:|---|
| `cust_id` | 1–10 | 10 | `PIC X(10)` |
| `cust_name` | 11–40 | 30 | `PIC X(30)` |
| `bill_date` | 41–48 | 8 | `PIC 9(8)` YYYYMMDD |
| `bill_amt` | 49–60 | 12 | `PIC 9(10)V99`, implied decimal |
| `currency` | 61–63 | 3 | `PIC X(3)` |
| `rec_type` | 64–65 | 2 | `PIC X(2)`, 01=invoice 02=credit |

## 3. Per-field transformation

| Clause | Contract | Evidence |
|---|---|---|
| C-3.1 | Trailing spaces are stripped from `cust_id`, `cust_name`, `currency` **only**. `bill_date`, `bill_amt` and `rec_type` keep theirs — a record type of `1 ` stays `1 `. | `P-ODD` |
| C-3.2 | Leading spaces are never stripped, in any field. | `P-LEAD` |
| C-3.3 | Amount = C `strtod`-style **prefix** parse of the 12-byte slice, divided by 100, formatted `%.2f`. Leading blanks are skipped; parsing stops at the first non-numeric byte; no prefix at all yields 0. `12AB`→0.12, `1e3`→10.00, `+5`→0.05, `.5`→0.01, `0x1A`→0.00, empty→0.00. | `P-BADAMT`, awk coercion probe |
| C-3.4 | A leading `-` is honoured, so **negative amounts are possible** even though the copybook says unsigned. | `P-NEG` |
| C-3.5 | Date = `substr(1,4)-substr(5,2)-substr(7,2)` of the 8-byte slice. **No validity check**: `20259999` → `2025-99-99`, 8 spaces → `    -  -  `, empty → `--`. Output is not always 10 characters and is not always a date. | `P-BADDATE`, `P-NODATE`, `P-SHORT` |
| C-3.6 | No field is ever NULL. Missing means empty string. The silver table stores empty strings, never NULL. | source |

## 4. Header, trailer, and silent record loss

| Clause | Contract | Evidence |
|---|---|---|
| C-4.1 | Any line whose first three bytes are `HDR` or `TRL` is deleted before parsing — including a **data** record whose customer id starts with those letters. | `P-HDRFAKE` |
| C-4.2 | That loss is silent today: the probe file declared 15 records, 14 were parsed, the job logged both numbers and exited 0. | `P-HDRFAKE` |
| C-4.3 | The trailer count is logged and **never enforced** (ETL-0187, open since 2011). The target records `trailer_count` vs `parsed_count` per file in an audit table and raises a non-fatal expectation; it must not change which rows are produced. | source |

## 5. Delimiter collision — the nastiest clause

The parser renders the six slices into a pipe-delimited line. If any slice **contains a `|`
byte**, the line gains extra fields and every downstream consumer reads the wrong column.

Observed, for a name containing `PIPE|NAME CO` (`P-PIPE`):

```
in :  C000000002  PIPE|NAME CO ...  20240101  000000020000  USD  01
psv:  C000000002|PIPE|NAME- C-O            |202401.01|000000020000|USD|01
gold: currency="000000020000", rec_type="USD" -> UNKNOWN(USD), amount 202401.01
```

The date transform is applied to the *name* remainder, the amount transform to the *date*, and
the report reads currency from the raw amount digits. This is contract.

**C-5.1** The silver table therefore stores both the six sliced fields **and** the rendered
`psv_line`. The gold aggregation is computed by re-splitting `psv_line` on `|` and taking
positional fields 1/5/6, exactly as `finance_excel_report.pl` does. Aggregating the clean
sliced columns would silently "fix" the bug and break parity.

## 6. Expectations and quarantine

Every field the legacy parser implicitly trusts gets an expectation. All of them are
**warn-and-route**, never `DROP ROW`:

| Expectation | Fails when |
|---|---|
| `rec_len_65` | record is not exactly 65 bytes |
| `cust_id_nonempty` | field 1 empty after rstrip (the report skips these rows) |
| `bill_date_valid_iso` | date slice is not a real calendar date |
| `bill_amt_all_digits` | amount slice is not 12 digits |
| `bill_amt_non_negative` | parsed amount < 0 |
| `currency_known` | currency not in (`USD`,`EUR`,`GBP`), case-sensitive |
| `rec_type_known` | record type not in (`01`,`02`) |
| `no_delimiter_collision` | any slice contains `|` |
| `not_hdr_trl_shadowed` | a data line was deleted by the HDR/TRL rule |
| `ascii_only` | any byte > 0x7F |

**C-6.1** A failing row is **copied** to `ow_tp.bronze.custbill_quarantine` with the raw bytes,
the byte offset, the file, and the list of failed expectations — and **still flows** to silver
and gold. Quarantine is observability, not a filter: the legacy processes these rows, so
filtering them would break parity. Nothing is dropped, and nothing is dropped *silently*
either, which is the actual requirement.

**C-6.2** Turning any expectation into a real filter is a post-cutover decision for the user
(P2-D02), not a migration change.

**C-6.3** Hard rule, and the acceptance test for it: **gold contains every record the legacy
chain produced, byte for byte, including the corrupt ones.** Quarantine is an additional
observability table and is never a gate on the output. `count(gold) == count(legacy report
rows)` and `count(silver) == count(legacy psv lines)` hold *independently of how many rows
quarantine holds*, and a recon that satisfies row counts only because an expectation removed
a row is a failed recon. If any expectation is ever found to drop a record from gold, the
unit stops and the behaviour goes back to the user rather than being reconciled around.

## 7. Aggregation and report contract

| Clause | Contract | Evidence |
|---|---|---|
| C-7.1 | The report aggregates **every** `CUSTBILL*.psv` in the parsed directory, not a day's slice. It is cumulative over the whole retained history and grows every run. | source (`readdir` + glob) |
| C-7.2 | Rows whose field 1 is empty are skipped. | `P-NOCUST` |
| C-7.3 | Group key is the raw `currency|rec_type` **byte string** from the re-split psv line. `usd` and `USD` are different groups; `1 ` and `01` are different groups. | `P-ODD` |
| C-7.4 | Label: `01`→`INVOICE`, `02`→`CREDIT`, anything else→`UNKNOWN(<raw>)`, trailing spaces included. | `P-RT03`, `P-ODD` |
| C-7.5 | Rows are ordered by ascending **ASCII byte order of the group key**, so uppercase sorts before lowercase and `|` (0x7C) sorts last. Not alphabetical, not by label. | probe report |
| C-7.6 | Header line is exactly `Currency,RecordType,RecordCount,TotalAmount` + LF. No quoting, no escaping — a comma inside a currency value would corrupt the CSV, as it does today. | source |
| C-7.7 | `RecordCount` is `%d`, `TotalAmount` is `%.2f`. | source |
| C-7.8 | Empty input produces a **header-only** file, not an empty file and not an error. | source |
| C-7.9 | Legacy sums IEEE doubles; the target sums `DECIMAL(38,2)`. Every psv amount is already exactly 2dp, so the two agree bit-for-bit while `abs(total) < 2^53/100 ≈ 9.0e13`. Above that the double loses cents and the target is *more* accurate; that divergence is reported as an anomaly, never silently absorbed. | derived |
| C-7.10 | Output files are `finance_billing_<YYYYMMDD>.csv` and `.xls`, stamped with the **run date in the job timezone** (P2-D04: UTC proposed). | source |
| C-7.11 | The `.xls` file is a **byte-identical copy of the CSV**. It is not an Excel workbook and never was; the extension is a lie kept for compatibility. | `cmp` on baseline run |
| C-7.12 | The sendmail step is removed. It has been a no-op for years (the binary is absent on the current boxes) so no delivery behaviour is lost. Failure notification moves to the Lakeflow Job. | D4-01, parent decision |

## 8. Idempotency

| Clause | Contract | Evidence |
|---|---|---|
| C-8.1 | Re-running the legacy parse is a no-op: inputs were renamed `.done` on the first pass. | rerun probe |
| C-8.2 | Re-running the report re-reads the same psv set and writes byte-identical output to the same dated name. | rerun probe |
| C-8.3 | Target: bronze ingestion is file-level exactly-once (streaming table + processed-file ledger keyed on path/size/mtime); silver is a deterministic function of bronze; gold is a full recompute of silver. Re-running any stage produces identical output. Proven by an actual second run in recon, not asserted. | design |

## 9. What this contract does **not** cover

- File permissions, ownership, and the timestamped `archive/` copy naming.
- Mail delivery (removed), lock files (removed), and log-line text.
- The partially-written-input race: ingest polls `*/15` with a 1-second double-stat, parse runs
  5 minutes later, and the legacy can legitimately produce output from a half-written file.
  Recon runs against a pinned, stable fixture set, so **the race itself is unverified** and is
  listed as such in every recon report.
- Structure, not rows: grants, constraints, table properties and Unity Catalog permissions are
  outside row-level parity (carried forward from pipeline 1's finding).
- Anything `MVSPROD` job `CB77340` does upstream (D3-01).

## Captured baseline

`databricks/migration/p2/baseline/capture_legacy_baseline.sh` runs the real legacy chain over
the standard fixture set plus the probe file and keeps its output verbatim under
`captured/` — inputs, `parsed/*.psv`, `reports/*.csv` and `.xls`, the stage logs, the
rerun-is-a-no-op log, and the `cmp` result. That directory is the **source side** of every
pipeline-2 recon: the target recomputes from the same `.dat` inputs and never reads it.

The clause the captured report settles most usefully is C-7.5. Ordering is ASCII byte order
of the raw group key, and the probe output proves all three of its consequences at once:

```
000000020000,UNKNOWN(USD),1,202401.01     <- digits sort before letters (P-PIPE)
EUR,INVOICE,27,123192.40                  <- 01 before 02 within a currency
USD,UNKNOWN(03),1,900.00
usd,UNKNOWN(1 ),1,0.01                    <- lowercase after uppercase
,UNKNOWN(),1,0.00                         <- empty key: '|' (0x7C) sorts last (P-SHORT)
```

## Probe evidence index

| Tag | Case |
|---|---|
| `P-NORMAL` | well-formed record |
| `P-PIPE` | `|` inside the name |
| `P-SHORT` | 19-byte record |
| `P-LONG` | 80-byte record |
| `P-NOCUST` | blank customer id |
| `P-BADAMT` | non-numeric amount |
| `P-BADDATE` | `20259999` |
| `P-NODATE` | blank date |
| `P-RT03` | record type `03` |
| `P-LEAD` | leading spaces in name |
| `P-NEG` | signed amount |
| `P-ODD` | lowercase currency, record type `1 `, 0.01 |
| `P-BLANK` | blank line |
| `P-HDRFAKE` | data record starting `HDR` |
| `P-LATIN1` | single 0xE9 byte |
| `P-UTF8` | multi-byte UTF-8 character |
| `P-CRLF` | CRLF line endings |
| `P-EMPTY` | zero-byte file |
