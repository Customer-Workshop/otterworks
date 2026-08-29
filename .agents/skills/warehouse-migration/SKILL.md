---
name: warehouse-migration
description: Mechanics for the legacy warehouse estate under dw/ — bringing up the Redshift stand-in in k8s, running the estate DAG, recording legacy manifests, converting an asset to Spark/Delta, and running the equivalence gate. Use when working on anything under dw/, or when asked to convert, verify, or reset a warehouse asset.
---

# Warehouse migration mechanics (`dw/`)

The estate under `dw/` is a Redshift-style legacy warehouse that really runs, plus
the gate a converted asset has to clear. The general procedure lives in the
`warehouse-migration-equivalence-gate` playbook; this file is the repo-specific
half: exact commands, paths, and the things that will bite you.

## Layout

| Path | What it is |
|---|---|
| `dw/k8s/` | Postgres 15 StatefulSet standing in for Redshift (`legacy-dw` / `analytics_dw`) |
| `dw/legacy-estate/ddl/` | Redshift-dialect DDL (`DISTKEY`/`SORTKEY`/`ENCODE`), by schema |
| `dw/legacy-estate/ddl/compat/` | Redshift→Postgres translator + `shims.sql`; **the only reason the dialect runs** |
| `dw/legacy-estate/elt/` | one ELT script per core/mart asset — the source of truth for semantics |
| `dw/legacy-estate/procs/`, `python/`, `jobs/` | stored procs, psycopg2 glue, the DAG/cron definitions |
| `dw/legacy-estate/seed/seed.sql` | deterministic generator; a reseed is byte-identical |
| `dw/harness/` | manifests, digests, fingerprints, `compare.py` (the gate) |
| `dw/harness/snapshots/legacy/` | the frozen legacy manifests — committed evidence |
| `dw/discovery/scan.py` | the inventory/lineage/dead-asset/DQ pass |
| `dw/databricks-migration/` | the target: Asset Bundle, notebooks, extract glue |

## Bring the source up

```bash
kubectl apply -f dw/k8s/
PYTHON_BIN=/home/ubuntu/dwdemo/.venv/bin/python dw/scripts/bootstrap-estate.sh
```

`bootstrap-estate.sh` goes from an empty PVC to the committed manifest state:
waits for the pod, creates schemas, checks and applies the translated DDL, installs
shims and procs, seeds, then runs the DAG in dependency order. It fails hard on any
step and is idempotent. Reset with:

```bash
dw/scripts/bootstrap-estate.sh --reset   # drops and recreates staging/core/mart
```

Connection (loopback only, NodePort 30032 → host 15432):

```bash
export DW_POSTGRES_DSN="host=127.0.0.1 port=15432 dbname=analytics_dw user=dw_admin password=dw_local_dev sslmode=disable"
```

The `dw_admin` credential is committed on purpose: this is a disposable
loopback-bound fixture holding only synthetic data, destroyed and recreated by the
reset command. A real extraction adds per-environment managed credentials, network
policy and least-privilege reader roles at the edge — say so when a reviewer flags
it rather than pretending the fixture is production-shaped.

## Expected state after bootstrap

26 tables, 7,519,321 rows. Sanity checks:

```bash
psql "$DW_POSTGRES_DSN" -c "SELECT COUNT(*) FROM core.fct_web_events"     # 2000000
psql "$DW_POSTGRES_DSN" -c "SELECT COUNT(*) FROM staging.stg_orders_raw"  # 401202
psql "$DW_POSTGRES_DSN" -c "SELECT COUNT(*) FROM core.fct_orders"         # 400000
```

The 1,202-row difference between those last two is the planted duplicate-delivery
wart, deduped in the pipeline rather than the DDL. Do not "fix" it.

## Discovery

```bash
python dw/discovery/scan.py --estate dw/legacy-estate --dsn "$DW_POSTGRES_DSN" \
  --out inventory.json --summary INVENTORY.md
```

With a `--dsn` the catalog is authoritative; without one it is a code-only scan and
the table set is inferred. Current output: 55 assets, 49 migratable, 26 tables,
2 dead, 0 unparsed. `inventory.json` / `INVENTORY.md` are generated — CI artifacts,
not committed files; paste the summary into the PR body as the evidence.

## Record the legacy reference

```bash
python dw/harness/snapshot.py --engine postgres --out dw/harness/snapshots/legacy \
  --tables mart.returns_rate_by_category
```

Postgres is the reference engine. DuckDB is supported for local iteration but
diverges on integer division and DECIMAL handling, so never record a baseline from
it. Re-recording is only legitimate when the estate source actually changed — the
manifest fingerprint covers the asset's ELT, every transitive upstream asset's ELT
and DDL, the staging DDL and the seed, so a re-record that was not caused by a real
source change will simply reappear as a mismatch somewhere else.

## Convert an asset and run the gate

The reference conversion is `mart.returns_rate_by_category`; copy its shape.

```bash
python dw/databricks-migration/src/extract_legacy.py --table core.fct_order_items
python dw/databricks-migration/src/extract_legacy.py --table core.fct_returns
python dw/databricks-migration/src/notebooks/returns_rate_by_category.py
python dw/harness/spark_snapshot.py \
  --path "$DW_LAKEHOUSE_ROOT/mart__returns_rate_by_category" \
  --table mart.returns_rate_by_category \
  --out /tmp/converted/returns_rate_by_category.json
python dw/harness/compare.py \
  --legacy dw/harness/snapshots/legacy/mart__returns_rate_by_category.json \
  --converted /tmp/converted/returns_rate_by_category.json \
  --report /tmp/reports/returns_rate_by_category.json
```

Environment the Spark side needs:

```bash
export SPARK_LOCAL_IP=127.0.0.1              # Spark hangs resolving the box hostname without this
export DW_LAKEHOUSE_ROOT=/home/ubuntu/dwdemo/lakehouse
/home/ubuntu/dwdemo/.venv/bin/python ...     # pyspark 3.5.6 + delta-spark 3.2.0, Java 11
```

`compare.py` exits 0 only on `pass`; `fail` and `blocked` exit 1 and both write the
report JSON. `blocked` means the fingerprints disagree — the recorded evidence
describes a different estate, so fix the inputs rather than the comparison. An
override needs `--rerecord-reason "<why>"`, which lands in the report.

## Target mode

Local Spark 3.5.6 + Delta 3.2.0. A `DATABRICKS_TOKEN` exists on the box but no
workspace host, so nothing runs in a workspace. The target code is nonetheless
Asset-Bundle-shaped (`dw/databricks-migration/databricks.yml`,
`resources/*.job.yml`, notebook-per-asset) so it drops into a real workspace
unchanged. State this mode explicitly in any PR or narration — do not imply a
workspace run.

## Checks to run before pushing

```bash
ruff check dw
PYTHONPATH=dw/harness pytest -q dw/harness/tests
```

`.github/workflows/dw-conversion-gate.yml` rebuilds the whole estate from scratch on
any `dw/**` change and re-runs the gate there, which is the run that counts: a gate
that only passes on the machine that recorded the baseline proves nothing.

## Where conversions actually diverge in this estate

Five planted traps, in rough order of how often they catch a conversion:

1. `mart.daily_revenue_usd` — FX conversion stays `NUMERIC` and rounds to cents per
   day; aggregating in double and rounding at the end differs by pennies on some rows.
2. `mart.session_funnel_daily` — timestamps are bucketed in `America/Los_Angeles`,
   not UTC, so a UTC conversion moves rows across day boundaries.
3. `core.fct_orders` — the duplicate deliveries above are deduped in the ELT.
4. `mart.customer_ltv` / segment grouping — segments are normalised with `UPPER(...)`;
   grouping on the raw value silently splits groups (2 case-variant segments exist).
5. `core.dim_customer_scd2` — version chains are sequence-sensitive, which is why this
   asset is compared with an **ordered** digest. Never canonicalise it to unordered.
