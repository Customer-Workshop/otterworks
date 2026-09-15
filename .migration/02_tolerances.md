# 02 Tolerances — the correctness contract

Version `1`. Set at STOP A. A tolerance changes only by an explicit approval recorded as a
new dated row in `05_decisions.md`, with the old row kept, a new `version` in both this file
and `02_tolerances.json`, and the list of merged units to re-verify.

Exception (pre-approved at STOP A): grading-only fixes — a canonicalization rule or a
harness bug, with no data change and no tolerance value change. Apply, log, mention at wave
close.

## Per-type rules

| Source pattern | Rule |
|---|---|
| `NUMBER(p,0)`, p ≤ 18 | exact (long; int where p ≤ 9 and the app expects 32-bit) |
| `NUMBER(p,s)`, s > 0 or p > 18 | Decimal128 at source scale; exact per value; sums, min and max match to 0.01 |
| Money (`NUMBER(14,2)`, `NUMBER(12,6)`, `NUMBER(14,4)`) | exact per value; aggregate sums to 0.01 |
| `VARCHAR2` / `NVARCHAR2` | exact after canonicalization |
| `CHAR(n)` | exact after `rstrip_spaces` |
| `DATE` / `TIMESTAMP` | exact after UTC normalization, truncated to ms |
| `'DD-MON-YY'` text that parses | exact as BSON Date |
| Date text that does not parse | field `null` + raw in `legacy.<field>Raw`; count of raw must equal the profiled bad-date count exactly |
| CSV list that parses | array; element count equals source token count exactly |
| Malformed CSV | `[]` + raw in `legacy.<field>Raw`; count of raw must equal the profiled bad-list count exactly |
| `CHAR(1)` `Y`/`N` | boolean; any other value `null` + raw; true/false/null counts match exactly |
| Integer code with a `CODES` row | decoded string; distinct-value counts match |
| Integer code with no `CODES` row | integer unchanged; listed in the dependency register |
| Empty string | Oracle `''` **is** NULL. Target policy: `null`. |
| NULL vs missing field | `null_missing_equiv: true` |

## Run settings

| Setting | Value |
|---|---|
| Recon mode | LIVE — the parent can query the source. Children run `fixture` mode; only the parent's live run is proof. |
| Row-diff threshold | 100,000 rows. Above it: keyed sampling plus full aggregates. |
| Sample size | 10,000 |
| Source query concurrency cap | 2 |
| Re-run cap | a child may re-run the full pipeline 3 times, then must escalate (AGENTS.md rule 7) |
| Circuit breaker | 3 same-class failures halts the wave |

## Anomaly budget — frozen

The seed manifest `testdata/legacy/manifests/demo.json` (namespace `demo`, seed 714559852)
is the expected set, compared as a set and not just a count:

| Anomaly | Expected | Target |
|---|---|---|
| orphaned invoice lines | 37 | `OW_BILLING.INVOICE_LINE` → `invoice_lines_orphaned` |
| dirty `SIGNUP_DT` values | 50 | `CUSTOMER_MASTER.SIGNUP_DT` → `legacy.signupDtRaw` |
| malformed CSV lists | 31 | `CUSTOMER_MASTER.RELATED_ACCT_IDS` → `legacy.relatedAcctIdsRaw` |

Finding more or fewer is a **finding** for the data owner and a recon FAIL. It is never
grounds for widening a tolerance.
