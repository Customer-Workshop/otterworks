# CUSTBILL conversion dialect notes (ksh / bash+awk / Perl → Databricks)

Parent-owned, wave 0. Read alongside your unit contract in
`docs/tech-partnerships/contracts/<unit>.contract.json`. These notes encode the
behaviours the reconciliation harness (`scripts/tp_dbx/recon_custbill.py`) checks
to the byte and to the cent; deviate only where the contract says the legacy
behaviour is a defect to retire.

## 0. Shape of a converted unit

- One notebook per task at `/Shared/ow_tp/custbill/<task>` (source of truth in the repo
  under `databricks/<unit>/<task>.py`, deployed with `client.import_notebook`). Serverless
  notebook task, Python; use Spark SQL for set operations, Python only for byte-level work
  (hashing, CSV/xlsx export).
- Parameters via `dbutils.widgets.get("ns")` (and `report_date` for finance). Validate
  `ns` against `^[a-z0-9-]{1,32}$` and fail fast.
- All writes are `DELETE ... WHERE ns = :ns AND <batch key>` followed by `INSERT`, or
  `INSERT OVERWRITE ... REPLACE WHERE ns = :ns` for gold. Never `CREATE`, `ALTER`, `DROP`,
  `TRUNCATE`, never `MERGE` without an `ns` predicate. Tables and the volume already exist
  (Terraform, `infrastructure/terraform-databricks/`).
- Volume paths: `/Volumes/ow_tp/bronze/landing/<ns>/{incoming,archive,reports}`. Use
  `dbutils.fs` / Python `open()` on the `/Volumes/...` path; both are fine on serverless.
- No `sleep`, no lock files, no `2>/dev/null || true`. Raise. The job's
  `max_concurrent_runs = 1` and `depends_on` chain replace all of that.

## 1. ksh `sftp_ingest_poll.ksh` → `ingest`

| Legacy | Target |
|---|---|
| `for f in $SFTP_DROP/CUSTBILL*.dat` | `dbutils.fs.ls(f"{landing}/incoming")`, filter `name.startswith("CUSTBILL") and name.endswith(".dat")`; ignore `*.part`, `*.tmp` |
| size-twice settle check | none; producer contract is write-then-rename (contract `settle_protocol`) |
| `cp $f $INCOMING/$b \|\| true` | read bytes once: `data = open(path,'rb').read()`; `digest = hashlib.sha256(data).hexdigest()` |
| `cp $f $ARCHIVE/$b.$(date +%Y%m%d%H%M%S)` | write `archive/<basename>.<digest[:12]>`; re-read and assert sha256 equal **before** any delete |
| `rm $f \|\| true` | `dbutils.fs.rm(incoming_path)` only after the archive hash matched and the bronze insert committed |
| stdout `date b still growing` | `print()` structured lines: `file=<b> action=<landed|duplicate|skipped> sha256=<digest>` (the recon reads run output for U6-e ordering) |

Bronze rows: split on `b"\n"` (drop the trailing empty element), `line_no` 1-based,
`record_kind` = `HDR` if the line starts with `b"HDR"`, `TRL` if `b"TRL"`, else `BODY`;
`raw_line` = the line decoded as **latin-1** (byte-preserving; the recon rebuilds the file
bytes by re-encoding latin-1 and must get the same sha256). Never `.strip()`.

Dedupe: `SELECT 1 FROM ow_tp.bronze.custbill_raw WHERE ns=:ns AND file_sha256=:d LIMIT 1`
→ if present, log `duplicate`, still archive/remove the incoming copy, insert nothing.

Insert pattern (Spark): build a DataFrame with the exact column order of the table and
`df.write.mode("append").saveAsTable("ow_tp.bronze.custbill_raw")` after
`DELETE FROM ... WHERE ns=:ns AND source_file=:b AND file_sha256=:d`. Do not
`spark.sql(f"INSERT ... VALUES")` with string interpolation of raw lines.

## 2. bash + sed/cut/awk `parse_custbill_fixedwidth.sh` → `parse`

Source rows: `SELECT source_file, line_no, raw_line FROM ow_tp.bronze.custbill_raw
WHERE ns=:ns AND record_kind='BODY'` (HDR/TRL already classified — this *is* the
`sed '/^HDR/d;/^TRL/d'`).

Fixed-width slicing in Spark SQL — `substr` is 1-based like `cut -c`:

```sql
substr(raw_line, 1, 10)  AS cust_id_raw,   -- cut -c1-10
substr(raw_line, 11, 30) AS cust_name_raw, -- cut -c11-40
substr(raw_line, 41, 8)  AS bill_date_raw, -- cut -c41-48
substr(raw_line, 49, 12) AS bill_amt_raw,  -- cut -c49-60
substr(raw_line, 61, 3)  AS currency_raw,  -- cut -c61-63
substr(raw_line, 64, 2)  AS rec_type       -- cut -c64-65 (NOT trimmed by legacy)
```

Legacy awk semantics and their exact Spark equivalents:

| awk | Spark SQL | Note |
|---|---|---|
| `gsub(/ +$/,"",$1)` | `rtrim(cust_id_raw)` | `rtrim` strips spaces only (same as `/ +$/`); do **not** use `trim()` (leading spaces are data) |
| `gsub(/ +$/,"",$2)`, `gsub(/ +$/,"",$5)` | `rtrim(cust_name_raw)`, `rtrim(currency_raw)` | same |
| `amt=$4+0; sprintf("%.2f", amt/100)` | `CAST(bill_amt_raw AS DECIMAL(12,2)) / 100` → `CAST(... AS DECIMAL(12,2))`; guard with `bill_amt_raw RLIKE '^[0-9]{12}$'` | legacy coerces `00000ABC1234` to `0.00` — that row is quarantined `nonnumeric_amount`, never loaded. Never go through DOUBLE. |
| `substr($3,1,4)"-"substr($3,5,2)"-"substr($3,7,2)` | `to_date(bill_date_raw, 'yyyyMMdd')` under `spark.sql.ansi.enabled=false` returns NULL for `20230231` → quarantine `invalid_calendar_date`; or `try_to_date(...)` explicitly | legacy emits `2023-02-31`. Recon compares silver `date_format(bill_date,'yyyy-MM-dd')` to legacy text, so only valid dates are in silver by construction. |
| `cut` on a short line | `length(raw_line) < 65` → quarantine `short_record`, do not slice | legacy pads/truncates silently |
| trailer `grep '^TRL' \| cut -c4-13 \| sed 's/^0*//'` | `CAST(substr(raw_line,4,10) AS INT)` on the TRL row vs `count(*)` of BODY rows per `source_file` → `trailer_count_mismatch` quarantine row with `line_no` = the TRL row's `line_no` | legacy logs `(trailer says N)` and moves on; target loads the body rows anyway (finance parity) |

`raw_line` is ASCII in every fixture, so `substr` character offsets equal byte offsets.
Assert it once per run: `SELECT count(*) ... WHERE raw_line RLIKE '[^\\x00-\\x7F]'` = 0,
else fail loudly (R1 pending — the contract lists EBCDIC as a coverage gap).

Quarantine reasons are a *set per row*: emit one row per defect; `reason` values only
from `short_record | nonnumeric_amount | invalid_calendar_date | trailer_count_mismatch`.

Empty-string fields stay `''` in silver (legacy PSV has empty fields, not `NULL`). Silver
never contains NULL in the six business columns; enforce with a
`WHERE ... IS NOT NULL` filter that routes NULL-producing rows to quarantine.

## 3. Perl `finance_excel_report.pl` → `finance`

| Perl | Spark SQL |
|---|---|
| `readdir` + `grep /^CUSTBILL.*\.psv$/` + concatenated loop | `FROM ow_tp.silver.custbill_records WHERE ns=:ns` — all rows, no date window |
| `next if ($cust eq "")` | `AND cust_id <> ''` |
| `$key = "$ccy\|$rt"; $tot{$key} += $amt; $cnt{$key}++` | `GROUP BY currency, rec_type` with `count(*)`, `CAST(sum(bill_amt) AS DECIMAL(18,2))` |
| `($rt eq "01") ? "INVOICE" : ($rt eq "02") ? "CREDIT" : "UNKNOWN($rt)"` | `CASE rec_type WHEN '01' THEN 'INVOICE' WHEN '02' THEN 'CREDIT' ELSE concat('UNKNOWN(', rec_type, ')') END` |
| `foreach $key (sort keys %tot)` | `ORDER BY currency, rec_type` — equivalent because `currency` is 3 fixed chars and the `\|` separator sorts identically for equal-length prefixes; the recon asserts row order against the legacy CSV rather than trusting this |
| `printf OUT "%s,%s,%d,%.2f\n"` | Python: `f"{ccy},{rt},{n},{Decimal(total):.2f}\n"`; header `Currency,RecordType,RecordCount,TotalAmount\n`; write bytes with `open(path,"wb")`, `\n` endings, no BOM |
| `$stamp = strftime %Y%m%d (localtime)` | `report_date` parameter (ISO) → `stamp = report_date.replace("-", "")`; default `datetime.now(timezone.utc).date()`. The parent's legacy baseline is generated with `TP_FAKETIME='2026-09-01 02:10:00'`, so pass `report_date=2026-09-01` for parity runs |
| `system("cp $csv $xls")` | `openpyxl` workbook, sheet `finance_billing`, header + rows, amounts as `float(Decimal)` with `number_format = '0.00'` → `reports/finance_billing_<stamp>.xlsx`. (`openpyxl` is available on serverless base environments; if not, `%pip install openpyxl==3.1.5` at the top of the notebook.) |
| `open(MAIL, "\|/usr/sbin/sendmail -t")` | nothing in the notebook; job-level `email_notifications.on_failure` (Terraform var `finance_recipients`) |

Gold load: `INSERT OVERWRITE ow_tp.gold.finance_billing REPLACE WHERE ns = :ns SELECT ...`
with `report_date` and `current_timestamp()` as `generated_at`. Float accumulation is
gone by construction — never `sum(CAST(bill_amt AS DOUBLE))`.

## 4. bash `run_all.sh` → job `ow_tp_custbill`

Already declared by the parent in `infrastructure/terraform-databricks/main.tf`. The
workflow unit edits **only** `job_custbill.tf`-scoped settings (task retries, trigger,
notifications) — never the catalog/tables — and captures run evidence for U9-c with the
Jobs API (`runs/get` → `state.result_state`, per-task `state.life_cycle_state`).

`sleep 600` → `depends_on`. Cron overlap → `max_concurrent_runs = 1`. `|| true` →
default failure propagation. Sunday `run_all` → `Run now` on the same job.

## 5. Things that look right and are wrong

- `trim()` instead of `rtrim()` — leading spaces in CUST-NAME are data.
- `CAST(x AS DOUBLE)` anywhere near money.
- `to_date` with ANSI mode on: it throws on `20230231` instead of yielding NULL; either
  use `try_to_date` or catch and quarantine — never let the task die on a planted row.
- `saveAsTable` with `mode("overwrite")` — that rewrites *every* namespace. Use
  `REPLACE WHERE ns = :ns` or DELETE+append.
- `dbutils.fs.rm` before the archive hash check.
- Writing to `ns = 'demo'` from a child session. Your slice is `<unit>-w<wave>`.
- Copying numbers from `CUSTBILL_analysis.md` into a recon report. Baselines are
  regenerated with `scripts/tp-run-deterministic.sh` every time.
