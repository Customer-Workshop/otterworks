# Seed specification (binding for the source unit)

The seed generator produces the Db2 source data for **both** `d24-before` and `d24-after`; the two
databases must be byte-identical after seeding (same file SHA-256s, see §7). Nothing here is
random at run time: every value is a pure function of `(SEED, stream, row index, field number)`.

## 1. Generator interface

```
cd migration/source && python3.12 -m seed --out <dir> [--tables DOCARCH,FILEAUD,RETNPLCY]
```

- Package: `migration/source/seed/` (`__init__.py`, `__main__.py`); standard library only.
- Outputs in `<dir>`:
  - `RETNPLCY.asc` (LRECL 128), `DOCARCH.asc` (LRECL 256), `FILEAUD.asc` (LRECL 160): fixed-width,
    RECFM=F, no line terminators, byte-exact to the copybooks (`../copybooks/FIELD-DERIVATION.md`).
  - `seed-summary.json`: `{ "seed": "0x4F54544552574B53", "files": {"<TABLE>.asc": {"rows": n, "sha256": hex}},
    "selected": {"<TABLE>": n}, "selected_by_class": {"<TABLE>": {"<CODE>": n}},
    "selected_charge_by_class": {"DOCARCH": {"<CODE>": "<decimal 8dp>"}} }` where the by-class
    figures use the **system-of-record** class (§5, MIG-07).
- Load into Db2 with `migration/source/seed/load.sh <dir>` (source unit), which runs, per table in
  the order RETNPLCY, DOCARCH, FILEAUD:

```
db2 "LOAD FROM <dir>/DOCARCH.asc OF ASC
     MODIFIED BY reclen=256 binarynumerics packeddecimal
                 timestampformat=\"YYYY-MM-DD-HH.MM.SS.UUUUUUUUUUUU\"
     METHOD L (1 16, 17 52, 53 54, 55 58, 59 90, 91 106, 107 122,
               123 162, 163 170, 171 171, 172 179, 180 243, 244 251, 252 254)
     INSERT INTO ARCHIVE.DOCARCH"
```

  (positions for the other tables come from the offset tables in `FIELD-DERIVATION.md`), then
  `SET INTEGRITY FOR ARCHIVE.DOCARCH, ARCHIVE.FILEAUD IMMEDIATE CHECKED` and `RUNSTATS` on all three.

## 2. PRNG

SplitMix64, counter-based (no state carried between rows, so any row can be regenerated alone):

```python
M64 = (1 << 64) - 1
SEED = 0x4F54544552574B53            # "OTTERWKS"
STREAM = {"RETNPLCY": 1, "DOCARCH": 2, "FILEAUD": 3, "PLANTED": 4}

def splitmix64(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
    return x ^ (x >> 31)

def h(stream: str, index: int, field: int) -> int:
    """Uniform 64-bit value for (stream, 0-based row index, field number)."""
    return splitmix64(splitmix64(SEED ^ STREAM[stream]) ^ ((index << 6) | field))

def pick(stream, index, field, n):   # uniform-enough integer in [0, n)
    return h(stream, index, field) % n
```

Field numbers are the copybook ordinal (1-based, §2 of `FIELD-DERIVATION.md`); cohort/parent
choices use field numbers 40-63.

## 3. Row counts

| Table | Generated | Planted | **Total** | Selected generated | Selected planted | **Selected** |
|---|---:|---:|---:|---:|---:|---:|
| RETNPLCY | 40 (fixed list §4) | 0 | **40** | 40 | 0 | **40** |
| DOCARCH | 1,199,958 | 42 | **1,200,000** | 179,963 | 37 | **180,000** |
| FILEAUD | 4,099,995 | 5 | **4,100,000** | 619,995 | 5 | **620,000** |

Selection is evaluated with the d24 manifest (`migration/manifest.yaml`):
`RETENTION_CLASS IN closed-7y = {FIN7, LGL7, HRS7, TAX7, AUD7, F07R, L07R}` and
`LAST_ACCESS_TS < '2019-01-01-00.00.00.000000000000'` (DOCARCH) / `EVENT_TS < <same cutoff>`
(FILEAUD). RETNPLCY is selected in full.

Expected run outcome on `d24-after` (the report must show exactly this, §6 of `CONTRACTS.md`):

| Table | extracted | loaded | rejected (LOAD) | validated | failed (VALIDATE) | purged |
|---|---:|---:|---:|---:|---:|---:|
| RETNPLCY | 40 | 40 | 0 | 40 | 0 | 0 (reference table, never purged) |
| DOCARCH | 180,000 | 179,980 | 20 (MIG-01/02/03/06) | 179,963 | 17 (MIG-04 x5, MIG-07 x12) | 179,963 |
| FILEAUD | 620,000 | 620,000 | 0 | 619,995 | 5 (MIG-05) | 619,995 |

`failed` in the report = rejected (LOAD) + failed (VALIDATE): DOCARCH 37, FILEAUD 5.

## 4. RETNPLCY (40 fixed rows)

All rows: `EFFECTIVE_TS = 2010-01-01-00.00.00.000000000000`. `SUCCESSOR_CODE` blank (4 spaces)
means "active, no successor". `DISPOSITION_ACTION`: `PERM` for `PERM`, `REVW` when years = 9,
otherwise `DEST`. `POLICY_DESC` is the text below, right-padded to 60.

| POLICY_CODE | POLICY_DESC | YEARS | SUCCESSOR | ACTIVE |
|---|---|---:|---|---|
| FIN7 | Financial records | 7 | | Y |
| LGL7 | Legal correspondence | 7 | | Y |
| HRS7 | Personnel files | 7 | | Y |
| TAX7 | Tax filings | 7 | | Y |
| AUD7 | Internal audit workpapers | 7 | | Y |
| F07R | Financial records (retired code) | 7 | FIN7 | N |
| L07R | Legal correspondence (retired code) | 7 | LGL7 | N |
| H07R | Personnel files (retired code) | 7 | HRS7 | N |
| OPS1 / OPS3 / OPS5 | Operations records | 1 / 3 / 5 | | Y |
| MKT1 / MKT2 / MKT3 | Marketing material | 1 / 2 / 3 | | Y |
| ENG3 / ENG5 / ENG9 | Engineering documents | 3 / 5 / 9 | | Y |
| SLS3 / SLS5 | Sales records | 3 / 5 | | Y |
| SUP1 / SUP2 / SUP3 | Support tickets | 1 / 2 / 3 | | Y |
| PRJ3 / PRJ5 / PRJ9 | Project files | 3 / 5 / 9 | | Y |
| CMP5 / CMP9 | Compliance evidence | 5 / 9 | | Y |
| SEC3 / SEC7 | Security logs | 3 / 7 | | Y |
| INS9 | Insurance policies | 9 | | Y |
| PHI9 | Health information | 9 | | Y |
| PERM | Permanent records | 99 | | Y |
| TMP0 / TMP1 | Temporary working files | 0 / 1 | | Y |
| EML2 / EML5 | Email archives | 2 / 5 | | Y |
| CHT1 / CHT2 | Chat transcripts | 1 / 2 | | Y |
| BRD9 | Board minutes | 9 | | Y |
| GOV9 | Governance records | 9 | | Y |

`SET_ACTIVE = [FIN7, LGL7, HRS7, TAX7, AUD7]`; `OTHER_ACTIVE` = the 32 active codes not in
`closed-7y`, in the table order above (OPS1 ... GOV9). `F07R`, `L07R`, `H07R` are never used by
generated rows.

## 5. DOCARCH generated rows

Index `g` in `[0, 1_199_958)`. Key `ARCH_KEY = "DA" + f"{g + 1:014d}"` (16 chars, no padding).

Cohort by affine permutation `p = (1_000_003 * g + 424_242) % 1_199_958` (bijective; gcd = 1):

| Cohort | Condition | Rows | RETENTION_CLASS | LAST_ACCESS_TS range (half-open) |
|---|---|---:|---|---|
| S (selected) | `p < 179_963` | 179,963 | `SET_ACTIVE[pick(g,4,5)]` | `[2012-01-01, 2019-01-01)` |
| R (recent) | `179_963 <= p < 479_963` | 300,000 | `SET_ACTIVE[pick(g,4,5)]` | `[2019-01-01, 2026-07-01)` |
| O (other class) | `p >= 479_963` | 719,995 | `OTHER_ACTIVE[pick(g,4,32)]` | `[2012-01-01, 2026-07-01)` |

Field rules (stream `DOCARCH`, index `g`):

| Column | Rule |
|---|---|
| `DOC_ID` | lowercase UUID text from `h(g,2)` (high 64 bits) and `h(g,41)` (low 64 bits), version nibble forced to `4`, variant bits `10` |
| `VERSION_NO` | `1 + pick(g,3,9)` |
| `LAST_ACCESS_TS` | `lo + pick(g,5,span_seconds)` seconds, fraction `pick(g,42,10**12)` rendered as 12 digits |
| `BYTE_SIZE` | `1024 + pick(g,13,50_000_000)` |
| `UNIT_RATE` | `(1 + pick(g,7,99_999)) / 10**8` (0.00000001 .. 0.00099999) |
| `STORAGE_CHARGE` | `BYTE_SIZE * UNIT_RATE`, exact (8 dp) |
| `OWNER_NAME` | `SURNAMES[pick(g,8,16)] + ", " + chr(65 + pick(g,43,26)) + "."`, encoded **cp037**, right-padded with `X'40'` to 40 bytes |
| `DISPOSITION_DT` | date part of `LAST_ACCESS_TS` + `RETENTION_YEARS` of the row's class (Feb 29 -> Feb 28), `YYYYMMDD` encoded **cp037** (`X'F0'-X'F9'`) |
| `LEGAL_HOLD_FLAG` | `'Y'` iff cohort O and `pick(g,10,50) == 0`, else `'N'` |
| `CHECKSUM_ALG` | `'SHA256  '` |
| `CONTENT_SHA256` | `sha256(ARCH_KEY.encode("ascii")).hexdigest()` |
| `SOURCE_SYS` | `["OWD", "OWF", "IMP"][pick(g,14,3)]` |

`SURNAMES = [ADAMS, BROOKS, CHEN, DIAZ, EVANS, FOSTER, GARCIA, HUGHES, IBRAHIM, JONES, KOWALSKI, LOPEZ, MURPHY, NGUYEN, OKAFOR, PATEL]`.

Sequences `S_KEYS` and `NS_KEYS` = generated keys of cohort S, resp. cohorts R and O, each sorted
ascending by `ARCH_KEY` (179,963 and 1,019,995 entries).

## 6. FILEAUD generated rows

Index `m` in `[0, 4_099_995)`. Key `AUDIT_KEY = "FA" + f"{m + 1:018d}"`.
`q = (7_777_777 * m + 13) % 4_099_995` (bijective).

| Cohort | Condition | Rows | Parent `ARCH_KEY` | `EVENT_TS` |
|---|---|---:|---|---|
| selected child | `q < 619_995` | 619,995 | `S_KEYS[q % 179_963]` | `parent.LAST_ACCESS_TS - pick(m,44,3*365*86400)` s (keeps parent fraction) |
| other child | `q >= 619_995` | 3,480,000 | `NS_KEYS[(q - 619_995) % 1_019_995]` | parent cohort R: `2019-01-01 + pick(m,44, secs(parent.LAST_ACCESS_TS - 2019-01-01) + 1)` s; cohort O: as selected child |

Invariants the generator must assert before writing: every child of an S parent has
`EVENT_TS < cutoff`; every child of an R parent has `EVENT_TS >= cutoff`; `RETENTION_CLASS` equals
the parent's. Therefore exactly the 619,995 selected children (+5 orphans, §7) match the FILEAUD
predicate, and every child of a selected parent is itself selected.

Other fields: `EVENT_TYPE = ["VIEW","DNLD","HOLD","RLSE","DISP","XPRT"][pick(m,3,6)]`,
`ACTOR_ID = "U" + f"{pick(m,5,10**11):011d}"`, `DISPOSITION_CODE = "00"`,
`CLIENT_IP = f"10.{pick(m,45,256)}.{pick(m,46,256)}.{pick(m,47,254)+1}"` right-padded to 15,
`DETAIL_TEXT = f"{EVENT_TYPE} v{parent.VERSION_NO}"` right-padded to 40.

## 7. Planted rows (MIG-01 .. MIG-07)

Planted rows use the §5/§6 field rules with stream `PLANTED` and index = the planted ordinal
below, then apply the overrides listed. Derived columns (`STORAGE_CHARGE`, `DISPOSITION_DT`,
`CONTENT_SHA256`) are computed from the **pre-override** generated values unless the override names
them; `CONTENT_SHA256` always hashes the final `ARCH_KEY` as stored (including padding). Key ranges `MIGnn-*` are reserved for planted rows;
generated keys never start with `MIG`. Planted DOCARCH rows have **no** FILEAUD children except
the MIG-05 parents. `CUT` = `2019-01-01-00.00.00.000000000000`.

| Ordinal | Keys | Table | Overrides | Selected | Failure |
|---:|---|---|---|---|---|
| 0-4 | `MIG01-0000000001` .. `MIG01-0000000005` | DOCARCH | class `FIN7`; `LAST_ACCESS_TS = 2016-03-0<k>-10.15.30.123456789012`; `OWNER_NAME = cp037("LOPEZ") + X'3F' + cp037(", M.")` padded `X'40'` (unmappable byte at OWNER_NAME byte 6) | yes | MIG-01 |
| 5-9 | `MIG02-0000000001` .. `MIG02-0000000005` | DOCARCH | class `TAX7`; `LAST_ACCESS_TS = 2015-06-1<k>-08.00.00.000000000001`; `UNIT_RATE = 12345678901234.5678900<k>` (14 integer digits > target `DECIMAL(18,8)`) | yes | MIG-02 |
| 10-14 | `MIG03-0000000001` .. `MIG03-0000000005` | DOCARCH | class `LGL7`; `LAST_ACCESS_TS = 2014-11-2<k>-17.45.00.500000000000`; `DISPOSITION_DT = X'0000000000000000'` (low-values) | yes | MIG-03 |
| 15-19 | `MIG04-01` .. `MIG04-05` (8 chars, stored right-padded with 8 spaces to CHAR(16)) | DOCARCH | class `HRS7`; `LAST_ACCESS_TS = 2013-02-0<k>-09.30.00.000000000000` | yes | MIG-04 |
| 20-24 | `MIG05-0000000001` .. `MIG05-0000000005` | DOCARCH | class `FIN7`; `LAST_ACCESS_TS = 2025-02-0<k>-12.00.00.000000000000` (>= CUT, so **not** selected) | no | parent of MIG-05 |
| 0-4 | `MIG05-00000000000001` .. `MIG05-00000000000005` | FILEAUD | `ARCH_KEY = MIG05-000000000<k>`; class `FIN7`; `EVENT_TYPE = VIEW`; `EVENT_TS = 2017-05-0<k>-07.00.00.000000000000` (< CUT, so selected) | yes | MIG-05 |
| 25-29 | `MIG06-0000000001` .. `MIG06-0000000005` | DOCARCH | class `AUD7`; `LAST_ACCESS_TS = 2016-09-0<k>-11.11.11.111111111111`; Azure fixture §8 | yes | MIG-06 |
| 30-35 | `MIG07-0000000001` .. `MIG07-0000000006` | DOCARCH | class `F07R`; `LAST_ACCESS_TS = 2017-01-0<k>-00.00.00.000000000000`; `STORAGE_CHARGE` = 100, 200, 300, 400, 500, 1100.12345678 (sum **2600.12345678**) | yes | MIG-07 |
| 36-41 | `MIG07-0000000007` .. `MIG07-0000000012` | DOCARCH | class `L07R`; `LAST_ACCESS_TS = 2017-02-0<k>-00.00.00.000000000000`; `STORAGE_CHARGE` = 433, 433, 433, 433, 433, 435.12345679 (sum **2600.12345679**) | yes | MIG-07 |

`<k>` is 1..5 (1..6 for MIG-07 rows, restarting at 1 for keys 7-12). All decimals are exact 8 dp.

### Why each plant fails where it does

- **MIG-01** `X'3F'` decodes (cp037) to U+001A, a C0 control with no target mapping; LOAD rejects
  `OWNER_NAME` with rule `CCSID_UNMAPPABLE`, no SQLSTATE, error `CCSID037 byte X'3F' at offset 6`.
- **MIG-02** Source `DECIMAL(31,8)` holds the value; manifest `type_overrides` narrow `UNIT_RATE`
  to `DECIMAL(18,8)`; LOAD rejects with `DECIMAL_OVERFLOW`, SQLSTATE `22003`.
- **MIG-03** Low-values decode to eight U+0000; the value is handed to the target
  `CONVERT(DATE, ?, 112)`, which fails: `DATE_INVALID`, SQLSTATE `22007`.
- **MIG-04** Business hash keeps key padding (`CONTRACTS.md` §7); the target key column is
  `NVARCHAR(16)` and loses it, so hashes differ: `HASH_MISMATCH` at VALIDATE. (SQL Server `=`
  ignores trailing spaces, so the key still joins; only the hash exposes it.)
- **MIG-05** FILEAUD row selected, parent `MIG05-...` exists in Db2 but is outside the DOCARCH
  selection, so it has no target parent: `ORPHAN_PARENT_NOT_SELECTED` at VALIDATE.
- **MIG-06** A partially completed prior run (§8) left `stg.DOCARCH` rows for the same keys; the
  unique index on `stg.DOCARCH(source_key)` raises SQL Server error 2601, SQLSTATE `23000`:
  `DUPLICATE_SOURCE_KEY` at LOAD.
- **MIG-07** (headline) The manifest `value_map` for `RETENTION_CLASS` transposes the retired
  codes (`F07R -> LGL7`, `L07R -> FIN7`); the system of record says `F07R -> FIN7`,
  `L07R -> LGL7` (`RETNPLCY.SUCCESSOR_CODE`). Six rows move each way, so table total
  (5,200.24691357) and per-class **counts** agree, but per-class charge sums differ by
  `0.00000001` in FIN7 and LGL7. VALIDATE fails the 12 keys with `CLASS_TOTAL_MISMATCH`. A check
  of table totals alone passes, which is the point.

## 8. MIG-06 prior-run fixture (Azure SQL)

File `migration/source/seed/fixtures/mig06_prior_run.sql` (T-SQL, idempotent). Applied by ops
with `python -m ldm init --apply-sql migration/source/seed/fixtures/mig06_prior_run.sql` before
the first real run. It reads the namespace from `SESSION_CONTEXT(N'ldm.namespace')` and inserts:

1. `mig.runs`: `run_id = 'prior-partial'`, that namespace, `status = 'ABANDONED'`,
   `purge_enabled = 0`, `started_at = '2026-01-01T00:00:00'`, `finished_at = NULL`.
2. `mig.key_ranges`: one row, `run_id = 'prior-partial'`, `table_name = 'DOCARCH'`,
   `range_seq = 1`, `key_from = 'MIG06-0000000001'`, `key_to = 'MIG06-0000000005'`,
   `extract_status = 'DONE'`, `load_status = 'RUNNING'`, `rows = 5`.
3. `stg.DOCARCH`: 5 rows for keys `MIG06-0000000001..05`, `run_id = 'prior-partial'`,
   `range_seq = 1`, `batch_id = 1`, `raw_bytes` = the 256-byte record the generator produces
   for that key, converted columns equal to what LOAD would produce, `row_hash = NULL`.

No other fixture exists; the before namespace has no Azure side and gets none.

## 9. complexity-manifest.json

`demos/app/complexity-manifest.json` (created with this spec) registers the seven classes. Field
semantics: `planted_keys` are RTRIMmed key values (match reported `source_key` after RTRIM);
`expected_stage` in `{LOAD, VALIDATE}`; `expected_rule` is the exact `rule` string the job writes;
`expected_sqlstate` is null when the failure is a conversion error raised by the job. The file is
demo metadata: the job may read it only through manifest `report.issue_register` to annotate
report rows (`CONTRACTS.md` §10.3); application code never reads it.
