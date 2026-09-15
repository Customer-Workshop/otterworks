"""SQL for the per-tenant usage meter (bronze -> silver -> gold).

Every statement is built here so the pipeline scripts, the tests and the recon
harness run exactly the same SQL. Table names are parameters (`Namespace`) so the
tests can run the real statements against throwaway tables inside `ow_tp` instead
of a re-implementation of the logic.

Semantics that matter:

* A meter period is a calendar month. Legacy rating windows (`RATING_PERIODS`) are
  calendar months and rating counts an event when
  `TO_CHAR(occurred_at,'YYYYMMDD')` falls between period start and end inclusive,
  so a calendar-month bucket on the event's own wall-clock date reproduces the
  rating window exactly.
* `occurred_at` is TIMESTAMP_NTZ. The Oracle source is zoneless and Oracle DATE
  carries a time part, so no zone conversion is applied anywhere.
* Dedupe is on event id, first arrival wins. A replayed file therefore cannot
  change a metered figure.
* Late arrivals are kept in the period they happened in, not the period they
  arrived in, which is why gold recomputes every period touched by new rows
  instead of only the newest one.
"""

from __future__ import annotations

from dataclasses import dataclass

# An event that shows up more than this long after it happened is flagged late.
LATE_THRESHOLD_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class Namespace:
    """Fully qualified names for one instance of the meter."""

    raw: str = "ow_tp.bronze.usage_meter_events_raw"
    events: str = "ow_tp.silver.usage_meter_events"
    rejects: str = "ow_tp.silver.usage_meter_rejects"
    meter: str = "ow_tp.gold.usage_meter_period"
    watermark: str = "ow_tp.gold.usage_meter_watermark"
    landing: str = "/Volumes/ow_tp/bronze/usage_meter_landing"

    def all_tables(self) -> list[str]:
        return [self.raw, self.events, self.rejects, self.meter, self.watermark]


PRODUCTION = Namespace()


def volume_ddl(ns: Namespace = PRODUCTION) -> str:
    _, _, catalog, schema, volume = ns.landing.split("/")[:5]
    return (f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume} "
            f"COMMENT 'Landing area for usage event batches consumed by the ow_tp usage meter.'")


def ddl(ns: Namespace = PRODUCTION) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS {ns.raw} (
  event_id STRING COMMENT 'event id as it arrived, untyped',
  tenant_id STRING COMMENT 'tenant id as it arrived, untyped',
  occurred_at STRING COMMENT 'event wall-clock time as it arrived, untyped; no zone',
  units STRING COMMENT 'metered units as they arrived, untyped',
  kind_cd STRING COMMENT 'usage kind code as it arrived, untyped; CODES(USAGE_KIND)',
  source_file STRING COMMENT 'file the row was read from',
  ingested_at TIMESTAMP_NTZ COMMENT 'when this pipeline read the file'
)
USING DELTA
COMMENT 'Append-only landing of usage event batches. Nothing is rejected here; typing and validation happen in silver.'""",
        f"""CREATE TABLE IF NOT EXISTS {ns.events} (
  event_id STRING NOT NULL COMMENT 'unique event id; the dedupe key',
  tenant_id STRING NOT NULL COMMENT 'tenant the usage belongs to',
  occurred_at TIMESTAMP_NTZ NOT NULL COMMENT 'when the usage happened; zoneless, as in the source',
  event_date DATE NOT NULL COMMENT 'date part of occurred_at; the field rating compares on',
  period_start DATE NOT NULL COMMENT 'first day of the calendar month the event falls in',
  period_end DATE NOT NULL COMMENT 'last day of that month, inclusive',
  kind_cd SMALLINT NOT NULL COMMENT 'usage kind code',
  metric STRING NOT NULL COMMENT 'usage kind name from ow_tp.bronze.codes',
  units BIGINT NOT NULL COMMENT 'metered units; always > 0',
  first_seen_at TIMESTAMP_NTZ NOT NULL COMMENT 'ingest time of the first copy of this event',
  last_seen_at TIMESTAMP_NTZ NOT NULL COMMENT 'ingest time of the most recent copy; the gold watermark reads this',
  seen_count BIGINT NOT NULL COMMENT 'how many copies of this event id arrived',
  arrival_lag_seconds BIGINT NOT NULL COMMENT 'first_seen_at - occurred_at',
  is_late BOOLEAN NOT NULL COMMENT 'arrival_lag_seconds > 86400',
  source_file STRING COMMENT 'file the first copy came from'
)
USING DELTA
COMMENT 'Normalised, deduplicated usage events. One row per event id, first arrival wins.'""",
        f"""CREATE TABLE IF NOT EXISTS {ns.rejects} (
  event_id STRING COMMENT 'event id as it arrived; may be null',
  tenant_id STRING COMMENT 'tenant id as it arrived; may be null',
  occurred_at STRING COMMENT 'raw event time',
  units STRING COMMENT 'raw units',
  kind_cd STRING COMMENT 'raw usage kind code',
  reject_reason STRING NOT NULL COMMENT 'why the row is not metered',
  source_file STRING COMMENT 'file the row came from',
  ingested_at TIMESTAMP_NTZ COMMENT 'when this pipeline read the file',
  rejected_at TIMESTAMP_NTZ NOT NULL COMMENT 'when this pipeline rejected the row'
)
USING DELTA
COMMENT 'Quarantine for usage rows that cannot be metered safely: missing attribution, non-positive units, unknown usage kind, unparseable time.'""",
        f"""CREATE TABLE IF NOT EXISTS {ns.meter} (
  tenant_id STRING NOT NULL COMMENT 'tenant the usage belongs to',
  metric STRING NOT NULL COMMENT 'usage kind name',
  kind_cd SMALLINT NOT NULL COMMENT 'usage kind code',
  period_start DATE NOT NULL COMMENT 'first day of the metered month',
  period_end DATE NOT NULL COMMENT 'last day of the metered month, inclusive',
  event_count BIGINT NOT NULL COMMENT 'distinct events metered in the period',
  units_total BIGINT NOT NULL COMMENT 'sum of units; the figure rating consumes',
  late_event_count BIGINT NOT NULL COMMENT 'how many of those events arrived late',
  avg_units_per_event DOUBLE NOT NULL COMMENT 'units_total / event_count',
  first_event_at TIMESTAMP_NTZ NOT NULL COMMENT 'earliest occurred_at in the period',
  last_event_at TIMESTAMP_NTZ NOT NULL COMMENT 'latest occurred_at in the period',
  source_watermark TIMESTAMP_NTZ NOT NULL COMMENT 'silver last_seen_at high-water mark of the run that last wrote this row',
  computed_at TIMESTAMP_NTZ NOT NULL COMMENT 'when the row was last recomputed'
)
USING DELTA
COMMENT 'Per-tenant, per-metric, per-month usage meter. Recomputed only for periods touched since the last watermark.'""",
        f"""CREATE TABLE IF NOT EXISTS {ns.watermark} (
  stream STRING NOT NULL COMMENT 'pipeline stage the watermark belongs to',
  watermark TIMESTAMP_NTZ NOT NULL COMMENT 'highest source timestamp already folded into the stage output',
  last_run_at TIMESTAMP_NTZ NOT NULL COMMENT 'when the stage last ran',
  rows_in BIGINT NOT NULL COMMENT 'rows the stage read on that run',
  run_id STRING COMMENT 'job run id or a local run marker'
)
USING DELTA
COMMENT 'Watermark state for the usage meter. One row per stage.'""",
    ]


def constraints(ns: Namespace = PRODUCTION) -> list[str]:
    """Structural checks on the meter output, applied after the tables exist."""
    return [
        f"ALTER TABLE {ns.events} ADD CONSTRAINT usage_meter_units_positive CHECK (units > 0)",
        f"ALTER TABLE {ns.events} ADD CONSTRAINT usage_meter_period_bounds CHECK (event_date BETWEEN period_start AND period_end)",
        f"ALTER TABLE {ns.meter} ADD CONSTRAINT usage_meter_counts_positive CHECK (event_count > 0 AND units_total > 0)",
    ]


def copy_into_bronze(ns: Namespace = PRODUCTION, subdir: str = "") -> str:
    """COPY INTO skips files it has already loaded, so a rerun lands nothing twice."""
    path = ns.landing + (f"/{subdir}" if subdir else "")
    return f"""COPY INTO {ns.raw}
FROM (
  SELECT CAST(event_id AS STRING) AS event_id,
         CAST(tenant_id AS STRING) AS tenant_id,
         CAST(occurred_at AS STRING) AS occurred_at,
         CAST(units AS STRING) AS units,
         CAST(kind_cd AS STRING) AS kind_cd,
         _metadata.file_path AS source_file,
         CAST(current_timestamp() AS TIMESTAMP_NTZ) AS ingested_at
  FROM '{path}'
)
FILEFORMAT = JSON
FORMAT_OPTIONS ('inferSchema' = 'false', 'schema' = 'event_id STRING, tenant_id STRING, occurred_at STRING, units STRING, kind_cd STRING')
COPY_OPTIONS ('mergeSchema' = 'false')"""


def read_watermark(ns: Namespace, stream: str) -> str:
    return (f"SELECT COALESCE(MAX(watermark), TIMESTAMP_NTZ'1900-01-01 00:00:00') AS wm "
            f"FROM {ns.watermark} WHERE stream = '{stream}'")


def write_watermark(ns: Namespace, stream: str, watermark: str, rows_in: int, run_id: str) -> str:
    return f"""MERGE INTO {ns.watermark} t
USING (SELECT '{stream}' AS stream,
              CAST('{watermark}' AS TIMESTAMP_NTZ) AS watermark,
              CAST(current_timestamp() AS TIMESTAMP_NTZ) AS last_run_at,
              CAST({rows_in} AS BIGINT) AS rows_in,
              '{run_id}' AS run_id) s
ON t.stream = s.stream
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *"""


# Rows arriving from bronze since the silver watermark, typed once and reused by the
# reject and the merge statements.
def _typed_batch(ns: Namespace, watermark: str, high: str) -> str:
    return f"""SELECT r.event_id,
       r.tenant_id,
       TRY_CAST(r.occurred_at AS TIMESTAMP_NTZ) AS occurred_at,
       TRY_CAST(r.units AS BIGINT) AS units,
       TRY_CAST(r.kind_cd AS SMALLINT) AS kind_cd,
       c.code_name AS metric,
       r.source_file,
       r.ingested_at,
       r.occurred_at AS occurred_at_raw,
       r.units AS units_raw,
       r.kind_cd AS kind_cd_raw
FROM {ns.raw} r
LEFT JOIN (SELECT CAST(code_val AS SMALLINT) AS code_val, code_desc AS code_name
           FROM ow_tp.bronze.codes WHERE code_type = 'USAGE_KIND') c
  ON TRY_CAST(r.kind_cd AS SMALLINT) = c.code_val
WHERE r.ingested_at > CAST('{watermark}' AS TIMESTAMP_NTZ)
  AND r.ingested_at <= CAST('{high}' AS TIMESTAMP_NTZ)"""


_REJECT_REASON = """CASE
  WHEN event_id IS NULL OR TRIM(event_id) = '' THEN 'missing event id'
  WHEN tenant_id IS NULL OR TRIM(tenant_id) = '' THEN 'missing tenant attribution'
  WHEN occurred_at IS NULL THEN 'unparseable occurred_at'
  WHEN units IS NULL THEN 'unparseable units'
  WHEN units <= 0 THEN 'units must be > 0'
  WHEN kind_cd IS NULL THEN 'unparseable usage kind'
  WHEN metric IS NULL THEN 'unknown usage kind'
END"""


def quarantine_rejects(ns: Namespace, watermark: str, high: str) -> str:
    """Nothing missing or unattributable reaches the meter; it lands here instead.

    Merged rather than inserted: a stage that fails after this statement and is
    retried replays the same bronze rows, and a reject row must not double.
    """
    return f"""MERGE INTO {ns.rejects} t
USING (
  SELECT event_id, tenant_id, occurred_at_raw, units_raw, kind_cd_raw,
         {_REJECT_REASON} AS reject_reason,
         source_file, ingested_at
  FROM ({_typed_batch(ns, watermark, high)})
  WHERE {_REJECT_REASON} IS NOT NULL
) s
ON t.event_id <=> s.event_id AND t.source_file <=> s.source_file
   AND t.ingested_at <=> s.ingested_at AND t.reject_reason = s.reject_reason
WHEN NOT MATCHED THEN INSERT (
  event_id, tenant_id, occurred_at, units, kind_cd, reject_reason,
  source_file, ingested_at, rejected_at
) VALUES (
  s.event_id, s.tenant_id, s.occurred_at_raw, s.units_raw, s.kind_cd_raw, s.reject_reason,
  s.source_file, s.ingested_at, CAST(current_timestamp() AS TIMESTAMP_NTZ)
)"""


def merge_silver(ns: Namespace, watermark: str, high: str) -> str:
    """Dedupe on event id, first arrival wins; a later copy only bumps the counters.

    Two properties the obvious version does not have:

    * `COPY INTO` stamps every row of one load with the same `ingested_at`, so
      ordering on it alone cannot separate two copies that landed together. One
      whole row is picked by `ROW_NUMBER` over a total order, instead of taking
      each column independently, so a silver row is always one real event.
    * `seen_count` and `last_seen_at` are counted over every copy in bronze, not
      added to what is already in silver, so a retried stage converges on the
      same numbers instead of inventing arrivals.
    """
    return f"""MERGE INTO {ns.events} t
USING (
  WITH batch AS (
    SELECT *, {_REJECT_REASON} AS reject_reason
    FROM ({_typed_batch(ns, watermark, high)})
  ),
  valid AS (SELECT * FROM batch WHERE reject_reason IS NULL),
  arrivals AS (
    SELECT r.event_id,
           COUNT(*) AS seen_count,
           MIN(r.ingested_at) AS first_seen_at,
           MAX(r.ingested_at) AS last_seen_at
    FROM {ns.raw} r
    WHERE r.event_id IN (SELECT event_id FROM valid)
    GROUP BY r.event_id
  ),
  ranked AS (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY ingested_at, source_file, occurred_at, units, kind_cd, tenant_id) AS rn
    FROM valid
  )
  SELECT v.event_id, v.tenant_id, v.occurred_at, v.units, v.kind_cd, v.metric, v.source_file,
         a.first_seen_at, a.last_seen_at, a.seen_count
  FROM ranked v
  JOIN arrivals a ON a.event_id = v.event_id
  WHERE v.rn = 1
) s
ON t.event_id = s.event_id
WHEN MATCHED THEN UPDATE SET
  t.last_seen_at = GREATEST(t.last_seen_at, s.last_seen_at),
  t.seen_count = s.seen_count
WHEN NOT MATCHED THEN INSERT (
  event_id, tenant_id, occurred_at, event_date, period_start, period_end,
  kind_cd, metric, units, first_seen_at, last_seen_at, seen_count,
  arrival_lag_seconds, is_late, source_file
) VALUES (
  s.event_id, s.tenant_id, s.occurred_at, CAST(s.occurred_at AS DATE),
  TRUNC(CAST(s.occurred_at AS DATE), 'MM'), LAST_DAY(CAST(s.occurred_at AS DATE)),
  s.kind_cd, s.metric, s.units, s.first_seen_at, s.last_seen_at, s.seen_count,
  CAST(UNIX_TIMESTAMP(s.first_seen_at) - UNIX_TIMESTAMP(s.occurred_at) AS BIGINT),
  (UNIX_TIMESTAMP(s.first_seen_at) - UNIX_TIMESTAMP(s.occurred_at)) > {LATE_THRESHOLD_SECONDS},
  s.source_file
)"""


def bronze_high_watermark(ns: Namespace, watermark: str) -> str:
    return (f"SELECT MAX(ingested_at) AS hi, COUNT(*) AS n FROM {ns.raw} "
            f"WHERE ingested_at > CAST('{watermark}' AS TIMESTAMP_NTZ)")


def silver_high_watermark(ns: Namespace, watermark: str) -> str:
    return (f"SELECT MAX(last_seen_at) AS hi, COUNT(*) AS n FROM {ns.events} "
            f"WHERE last_seen_at > CAST('{watermark}' AS TIMESTAMP_NTZ)")


def merge_gold(ns: Namespace, watermark: str, high: str) -> str:
    """Recompute only the (tenant, metric, period) cells touched since the watermark.

    A late event lands in an old period, so the cell set is derived from the changed
    rows and the aggregate is then taken over all silver rows in those cells.
    """
    return f"""MERGE INTO {ns.meter} t
USING (
  WITH touched AS (
    SELECT DISTINCT tenant_id, kind_cd, period_start
    FROM {ns.events}
    WHERE last_seen_at > CAST('{watermark}' AS TIMESTAMP_NTZ)
      AND last_seen_at <= CAST('{high}' AS TIMESTAMP_NTZ)
  )
  SELECT e.tenant_id,
         e.metric,
         e.kind_cd,
         e.period_start,
         e.period_end,
         COUNT(*) AS event_count,
         SUM(e.units) AS units_total,
         SUM(CASE WHEN e.is_late THEN 1 ELSE 0 END) AS late_event_count,
         CAST(SUM(e.units) AS DOUBLE) / CAST(COUNT(*) AS DOUBLE) AS avg_units_per_event,
         MIN(e.occurred_at) AS first_event_at,
         MAX(e.occurred_at) AS last_event_at,
         CAST('{high}' AS TIMESTAMP_NTZ) AS source_watermark,
         CAST(current_timestamp() AS TIMESTAMP_NTZ) AS computed_at
  FROM {ns.events} e
  JOIN touched USING (tenant_id, kind_cd, period_start)
  GROUP BY e.tenant_id, e.metric, e.kind_cd, e.period_start, e.period_end
) s
ON t.tenant_id = s.tenant_id AND t.kind_cd = s.kind_cd AND t.period_start = s.period_start
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *"""


def current_period(ns: Namespace) -> str:
    """The period the billing application is about to invoice.

    The month containing today when the meter has it, otherwise the newest metered
    month; the fixture estate's events are historical, so the fallback is the
    normal path here.
    """
    return f"""SELECT COALESCE(
  MAX(CASE WHEN period_start = TRUNC(CURRENT_DATE(), 'MM') THEN period_start END),
  MAX(period_start)) AS period_start
FROM {ns.meter}"""


def current_period_rows(ns: Namespace, period_start: str) -> str:
    return f"""SELECT tenant_id, metric, kind_cd, period_start, period_end,
       event_count, units_total, late_event_count, avg_units_per_event,
       first_event_at, last_event_at, computed_at
FROM {ns.meter}
WHERE period_start = DATE'{period_start}'
ORDER BY tenant_id, metric"""


# --- correctness comparison -------------------------------------------------
#
# The direct aggregate deliberately does not read the meter's own silver columns
# (period_start / period_end / metric). It rebuilds the rating window from
# occurred_at the way pkg_rating does -- an inclusive YYYYMMDD comparison against
# the calendar month -- so agreement is evidence, not a tautology.

def direct_aggregate(ns: Namespace, period_start: str, period_end: str) -> str:
    return f"""SELECT e.tenant_id,
       c.code_name AS metric,
       COUNT(*) AS event_count,
       SUM(e.units) AS units_total,
       CAST(SUM(e.units) AS DOUBLE) / CAST(COUNT(*) AS DOUBLE) AS avg_units_per_event
FROM {ns.events} e
JOIN (SELECT CAST(code_val AS SMALLINT) AS code_val, code_desc AS code_name
      FROM ow_tp.bronze.codes WHERE code_type = 'USAGE_KIND') c
  ON e.kind_cd = c.code_val
WHERE DATE_FORMAT(e.occurred_at, 'yyyyMMdd') >= DATE_FORMAT(DATE'{period_start}', 'yyyyMMdd')
  AND DATE_FORMAT(e.occurred_at, 'yyyyMMdd') <= DATE_FORMAT(DATE'{period_end}', 'yyyyMMdd')
GROUP BY e.tenant_id, c.code_name
ORDER BY e.tenant_id, c.code_name"""


def meter_rows_for_period(ns: Namespace, period_start: str) -> str:
    return f"""SELECT tenant_id, metric, event_count, units_total, avg_units_per_event
FROM {ns.meter}
WHERE period_start = DATE'{period_start}'
ORDER BY tenant_id, metric"""


def source_snapshot_aggregate(period_start: str, period_end: str) -> str:
    """The same aggregate straight off the migrated Pipeline 1 snapshot table.

    `ow_tp.silver.usage_events` is not part of this pipeline; comparing against it
    shows the meter did not lose or invent events on the way through bronze.
    """
    return f"""SELECT u.tenant_id,
       c.code_name AS metric,
       COUNT(*) AS event_count,
       SUM(u.units) AS units_total,
       CAST(SUM(u.units) AS DOUBLE) / CAST(COUNT(*) AS DOUBLE) AS avg_units_per_event
FROM ow_tp.silver.usage_events u
JOIN (SELECT CAST(code_val AS SMALLINT) AS code_val, code_desc AS code_name
      FROM ow_tp.bronze.codes WHERE code_type = 'USAGE_KIND') c
  ON u.kind_cd = c.code_val
WHERE DATE_FORMAT(u.occurred_at, 'yyyyMMdd') >= DATE_FORMAT(DATE'{period_start}', 'yyyyMMdd')
  AND DATE_FORMAT(u.occurred_at, 'yyyyMMdd') <= DATE_FORMAT(DATE'{period_end}', 'yyyyMMdd')
GROUP BY u.tenant_id, c.code_name
ORDER BY u.tenant_id, c.code_name"""
