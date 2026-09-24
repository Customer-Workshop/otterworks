# seed - deterministic Db2 seed for the legacy-data-migration demo

Owned by the **source** unit. `SEED-SPEC.md` is binding: this package is its executable form.

## Generate (Python 3.12, standard library only)

```bash
cd migration/source
python3.12 -m seed --out /tmp/seed                 # full scale: 40 / 1,200,000 / 4,100,000 rows
python3.12 -m seed --out /tmp/seed --scale 0.01    # smoke test: 40 / 12,042 / 41,005 rows
python3.12 -m seed --out /tmp/seed --tables DOCARCH,FILEAUD
python3.12 -m seed --fixture-out seed/fixtures/mig06_prior_run.sql   # re-render the MIG-06 fixture
python3.12 -m unittest seed.test_seed -v
```

Output: `RETNPLCY.asc` (LRECL 128), `DOCARCH.asc` (256), `FILEAUD.asc` (160) - exact copybook
records, no line terminators, `PIC X` in ASCII padded `X'20'`, `FOR BIT DATA` in CP037 padded
`X'40'`, `COMP` big-endian, `COMP-3` packed - plus `seed-summary.json` (rows, SHA-256, selected
counts overall / by class, `STORAGE_CHARGE` totals by class with the MIG-07 retired codes resolved).
Every run with the same seed constant and scale is byte-identical. Full scale takes ~75 s on 2 CPUs
(~960 MB).

The planted MIG-01..07 rows are always present, at every scale; `--scale` shrinks only the bulk
cohorts (the summary asserts the selected counts, 180,000 / 620,000 at scale 1).

## Load into Db2 (`load.sh`)

```bash
DB2_DATABASE=D24A LDM_DDL_DIR=migration/source/db2/ddl migration/source/seed/load.sh /tmp/seed
```

Runs as the instance owner inside the `db2-archive` pod (the Helm post-install hook does this).
Applies the DDL in filename order if `ARCHIVE.FILEAUD` does not exist, then `LOAD FROM ... OF ASC
MODIFIED BY binarynumerics packeddecimal METHOD L (...)` per table in dependency order, `SET
INTEGRITY`, `RUNSTATS`, and verifies the row counts against `seed-summary.json`. Idempotent: skips
when `ARCHIVE.DOCARCH` already holds the expected count, refuses (exit 12) on any other non-empty
state. Db2 errors exit 8 with the `SQLCODE`/`SQLSTATE` line on stderr. Measured full-scale load on
the `icr.io/db2_community/db2:11.5.9.0` image: 24 s (DDL + 3 LOADs + integrity + RUNSTATS).

## MIG-06 - duplicate key from a partially completed prior run

Db2 cannot hold a duplicate `ARCH_KEY` (primary key), so the source rows `MIG06-0000000001..5` are
unique and ordinary. The "prior run" lives on the **target**: `fixtures/mig06_prior_run.sql`
(rendered by `seed/fixture.py`) inserts, under `SESSION_CONTEXT(N'ldm.namespace')`, an abandoned
`mig.runs` row, a stale `mig.key_ranges` row covering the five keys, and the five keys into
`stg.DOCARCH`, all guarded so it is idempotent. `plant-partial-run.sh <token>` applies it (via the job's
`ldm` module when present, else `sqlcmd`) and refuses any token that is not `*-after`; the migration job's pre-run hook calls it
so the LOAD stage hits `DUPLICATE_SOURCE_KEY` (SQLSTATE 23000) on exactly those five keys.
