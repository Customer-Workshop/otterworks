# Billing extraction contract

Shared decisions for extracting the remaining legacy billing stored-procedure
modules (`rating`, `invoicing`, `dunning`) into `services/billing-service`.
`plans` is the worked reference. These decisions are fixed for every module so
that each extraction does not re-invent them; they are derived from what the
recorder captured and what the replay harness compares
(`procs/harness/record.py`, `procs/harness/replay.py`).

## 1. Numeric and decimal handling

- Money and rate arithmetic uses `decimal.Decimal` end to end. Never `float`.
- A contract field typed `decimal` is compared as a string quantized to two
  places with `ROUND_HALF_UP` on both sides. Emit money as a JSON string with
  exactly two decimals (`f"{value:.2f}"`), as `plans` does for `monthly_fee`.
- Rates that the legacy schema stores at higher precision (`overage_rate`,
  `numeric(12,6)`) are emitted at their stored precision (`f"{value:.6f}"`).
- Intermediate rounding must reproduce the procedure step by step. Where the
  SQL calls `round(...)` mid-computation, round at that same point with
  `ROUND_HALF_UP`; do not defer rounding to the response layer. Where the SQL
  does not round, do not round.
- Integer-typed fields are compared as JSON integers, not strings. Integer
  division/truncation in the procedure (`::integer` casts, `round(...)::integer`)
  must be reproduced explicitly, including PostgreSQL's half-up behaviour for
  `round()` on `numeric`.

## 2. Date and timezone handling

- All dates are `datetime.date` and serialize as ISO-8601 `YYYY-MM-DD`.
- Timestamps serialize as UTC ISO-8601 to seconds precision with a trailing
  `Z`, matching the recorder's normalization. Naive timestamps serialize
  without an offset. Never emit microseconds.
- The service has no clock of its own for graded behavior: every date used in
  a computation comes from request input or from stored data. No `date.today()`,
  no `now()`, no ambient timezone. The process runs as UTC.
- Date arithmetic is calendar-day arithmetic on `date` objects
  (`timedelta(days=n)`), inclusive/exclusive exactly as the procedure writes
  it (for example `p_period_end - v_sub.suspended_on + 1` is an inclusive
  day count).
- A `timestamptz` compared against a `date` in SQL (`issued_at::date`) is
  compared as its UTC calendar date.

## 3. Row ordering

- Row order is part of the contract. Any collected field (`collect: true`) or
  `rows` field is compared as an ordered list; a correct set in the wrong order
  is a parity failure.
- Reproduce the procedure's `ORDER BY` exactly, including its tiebreakers, and
  keep the ordering deterministic when the SQL's ordering is not total. Where
  the legacy statement has no `ORDER BY` but the transcript shows a stable
  order, order explicitly by the same keys the transcript exhibits, and record
  that choice as a rule in the module ledger.
- Ordering is applied in the domain layer (as `plans.catalog` does), not left
  to the database's physical row order.

## 4. NULL attribution

- SQL `NULL` maps to JSON `null`, never to `0`, `""`, or an omitted key. A
  field the transcript records as `null` must be present and `null` in the
  response.
- Distinguish "no row" from "row with NULL column". `SELECT ... INTO` in
  PL/pgSQL leaves the target record NULL when no row matched and the procedure
  then computes on NULLs; where the legacy behavior propagates NULL, the
  extraction propagates `None` rather than substituting a default.
- Reproduce `COALESCE`/`GREATEST`/`LEAST` semantics literally, including
  PostgreSQL's rule that `GREATEST`/`LEAST` ignore NULL arguments while most
  arithmetic with NULL yields NULL.
- Aggregates over zero rows return NULL in SQL; only the `COALESCE` the
  procedure actually writes turns that into `0`.

## 5. Empty-result semantics

- A function-backed read that legitimately returns zero rows returns HTTP 200
  with an empty JSON list, not 404 and not `null`.
- A single-object read with no matching row returns HTTP 404 (as `plans`
  entitlement does). Do not invent an empty object.
- A procedure-backed mutation that matches no rows is a successful no-op: HTTP
  200 with the same response shape and the unchanged state in its mutation
  probes.
- Only HTTP 200 is graded as a pass by the harness; any other status on a
  scenario the transcript recorded is a parity failure.

## 6. Mutation probe conventions

- Every procedure entrypoint returns, in its own response, the state the
  transcript's probes observed. Probes are graded by reading JSON paths out of
  the mutation response — the harness never queries the target database.
- For each probe in the module's scenarios, map a `probes:` entry in
  `procs/routes.yaml` to a JSON path in the mutation response, and expose the
  same rows the probe SQL selects, in the probe's `ORDER BY` order, with the
  same column names and the same normalization rules as above.
- Probe row objects carry exactly the columns the probe query selects. Extra
  keys inside a probed row change the compared value and fail parity; extra
  top-level response fields not referenced by the contract are allowed.
- The harness calls `POST /internal/reset` before every scenario, so each
  mutation starts from the seeded target state and must be idempotent with
  respect to that reset. Reproduce the procedure's own idempotency
  (`ON CONFLICT DO NOTHING`, `DO UPDATE`, `WHERE NOT EXISTS`) rather than
  relying on the reset.
- Deterministic identifiers the procedures derive (`md5(...)::uuid`,
  `uuid5(...)`) must be derived the same way, because probes and later
  scenarios select on them.

## 7. Transcripts are immutable

- `procs/transcripts/**` is the recorded legacy behavior and is never
  re-recorded during an extraction. Do not run `make procs-record`, and never
  pass `ALLOW_RERECORD=1`, `--allow-rerecord`, `--rerecord-reason
  harness-change`, or `--rerecord-reason scenario-redesign`.
- `services/legacy-billing/db/procs/*.sql`, `services/legacy-billing/db/schema.sql`,
  and `services/legacy-billing/db/seed.sql` are frozen. They feed `SOURCE_SHA`
  and `FIXTURE_SHA`; editing them invalidates every transcript and the replay
  fails with exit code 7 before grading.
- Scenarios under `procs/scenarios/**` are frozen too: they are the recorded
  contract's inputs. Do not weaken, retype, delete, or narrow a scenario, and
  do not add scenarios (a new scenario would require a recording).
- If a transcript looks wrong, that is a finding to report, not a transcript
  to change. Parity is achieved by changing the extracted service, never by
  changing the evidence.

## Target fixture (already shared)

`services/billing-service/db/migrations/001_initial.sql` already mirrors every
legacy table into `billing_svc`, `db/seed.sql` is generated from the legacy
seed by `scripts/generate_seed.py` for all of them, and `POST /internal/reset`
truncates the whole `billing_svc` schema before reseeding. Module extractions
consume this fixture; they do not need to extend it.
