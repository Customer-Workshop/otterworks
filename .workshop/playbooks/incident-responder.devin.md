# Playbook: Answer a production alert as the first responder

> **Facilitator / author:** this file is the source for a **Devin Playbook**.
> Copy its contents into your Devin organization (Settings → Playbooks → *Create
> a new Playbook*) so sessions can invoke it as `!incident-responder`, and point
> the alert Automation's prompt at that macro. See
> [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks)
> and [Automations](https://docs.devin.ai/product-guides/automations).

## Overview

Use this playbook when a **production alert pages you**: a latency SLO burning,
a disk filling, memory climbing toward a restart, a job double-counting. You are
the first responder. Nobody is going to type a follow-up prompt — the page is the
whole brief. Your job is to get the on-call engineer from "it's slow" to "here is
why, here is the proof, here is the fix" faster than a human rotation could open
a laptop.

The guiding principle: **telemetry first, then reproduce, then code — and a fix
is proven by the alert clearing under the same load that fired it.** Reading the
code first produces plausible theories; reading the trace first produces the
right one. A diff that "looks like it would help" is not a fix. The number that
paged (p95, disk ratio, RSS, duplicate windows) going back under its threshold
while the same load is running is.

## Required from user

None interactively — this playbook is designed to be started by an Automation.
Everything you need is in the page:

- **The alert payload** — the alert name, labels (`service`, `scenario`,
  `severity`), annotations (`summary`, `description`, `dashboard_url`,
  `traces_url`, `runbook_url`) and `startsAt`. If you were started from a Slack
  message, the `channel` and message `ts` of that alert are where the RCA goes.
- **The repository** that owns the paging service. Its Skill tells you how to
  bring the service up locally, reproduce the alert and run the gate.
- **A telemetry source** — a Prometheus/Grafana/Jaeger stack (local or a tenant),
  or an observability MCP connector. If none is reachable, say so in the RCA and
  work from the payload's annotations and the local reproduction alone.

If you were started by a human instead, ask only for the alert payload (or the
alert name and the time it fired); do not ask what to do next.

## Procedure

1. **Acknowledge and read the page.** Extract the alert name, service, the
   metric and threshold in the summary, and when it started. Post a one-line
   acknowledgement in the alert's thread ("Investigating `<alert>` on
   `<service>`; reading traces now") so the on-call engineer knows the page was
   picked up. Nothing else goes in the thread until you have a root cause.
2. **Read telemetry before code.** Open the dashboard and the trace search from
   the annotations. Establish three facts and write them down with numbers:
   what the user-facing symptom is (p95, error ratio, restarts), what is *not*
   changing (request volume flat, deploy unchanged), and what the traces say
   the time or resource is spent on (one request fanning into N SQL statements,
   one file growing, one map never shrinking, two instances doing the same
   work). A trace waterfall that shows a hundred child spans under one request
   is the finding; the code is where it comes from.
3. **Reproduce on your own machine.** Bring the service up from the repository
   (the Skill has the exact command), arm the same conditions, and run the
   gate in its *before* mode until it confirms the alert fires and the numbers
   match what you saw in production. If it will not reproduce, stop and report
   that — it means the cause is environmental (data shape, a flag, a replica
   count) and the fix belongs somewhere else.
4. **Find the cause in code, guided by the trace.** Follow the span names and
   SQL text back to the function that emits them. Check `git log -S` on that
   file for when the behavior arrived and whether it was known (a deferred
   TODO, a ticket reference). Name the exact function and line in the RCA.
5. **Make the smallest fix that removes the cause.** One query change, one
   migration, one test that pins the property the alert was measuring (query
   count per page, bytes on disk, entries in the cache, rows per window). Do
   not refactor around it, do not fix neighboring smells, do not touch other
   services. Run the service's lint and the focused tests.
6. **Prove it with the same load.** Rebuild the service, run the gate in its
   *after* mode — the same load profile that fired the alert — and record the
   alert clearing and the after-thresholds. Capture the before and after
   numbers side by side (for example p95 2.4 s → 0.09 s, 104 → 3 SQL
   statements per request). A gate that refuses to run because the source is
   unchanged is telling you that you have not deployed your fix yet.
7. **Post the RCA in the alert's thread.** One message, in this order: what
   users saw, what the telemetry showed, the root cause with file and function,
   the fix in one sentence, the before/after numbers, and the PR link. Reply in
   the thread of the alert message — not a new message, not a DM.
8. **Open the PR.** Title it after the alert. The body carries the RCA, the
   two gate summary lines (before red → after green) and the report file names,
   and states plainly that the load profile and thresholds came from the
   repository's scenario catalog. Work on your own branch; never push to the
   branch that carries the reproducible before-state.
9. **Leave the estate as you found it.** Disarm the local reproduction. If you
   changed nothing but code and a test, say so. If a runtime flag or replica
   count was part of the cause, say what has to change in the deployment and do
   not change it yourself.

## Specifications (postconditions)

- The RCA in the thread names a specific function and file, quotes at least one
  telemetry number from *before* the fix, and one from *after* — measured, not
  estimated.
- The before gate was run and went green on the unfixed code (the reproduction
  exists), and the after gate went green on the fixed code under the same load
  profile. Both report files are named in the PR.
- The alert that paged is inactive under the load that fired it.
- The diff is small and reviewable: the causal change, a migration if the fix
  needs schema, and one regression test that fails on the old code. No unrelated
  changes.
- Lint passes for the service; the focused tests pass; any pre-existing failures
  on the base branch are reported as pre-existing, not fixed and not hidden.
- Nothing was merged, and nothing was pushed to the before-state branch.

## Advice and pointers

- The dashboard tells you *that*; the trace tells you *why*. Spend your first
  two minutes in the trace waterfall, not in the code.
- Flat request volume with rising latency is a per-request cost growing with
  data, almost always a fan-out. Rising volume with rising latency is capacity.
  Say which one you are looking at in the RCA.
- Reproducing is not optional. A fix you could not reproduce the failure for is
  a guess with a diff attached, and the on-call engineer cannot tell the
  difference until it pages again.
- Prefer a query the database can plan well over caching the bad one. Caching a
  fan-out hides it until the cache misses at the worst time.
- When the fix needs an index, ship it as a migration in the same PR, and say
  in the RCA which part of the improvement came from the query change and which
  from the index — the gate report on each build tells you.
- If the telemetry stack is unreachable, do not stall. Reproduce locally, get
  the numbers from the local Prometheus, and say in the RCA that production
  telemetry was unavailable.
- Keep the thread short. The RCA is one message; the PR is where the detail
  lives.

### Worked example: the gate caught a fix that did not fix it

A responder on the OtterWorks `n-plus-one` page changed the list query to
eager-load versions with `selectinload`, saw the unit tests pass, and ran the
after gate. It went red: `queries_per_request=4.000 <= 4` passed, but
`p95_seconds=1.310 <= 0.5` failed and `DocumentListLatencyHigh` never cleared.
The trace for the new build showed two SQL spans — but the second one, the
`IN (...)` over 100 document IDs against `document_versions`, took 1.2 s on its
own because nothing indexed `(document_id, version_number)`. The query change
had removed the fan-out; the latency was the missing index. Adding the migration
brought p95 to 0.09 s and the gate went green. The unit test could not have
caught this (SQLite, forty rows); the load against the seeded Postgres could.
That is why the after gate drives the same load, and why "fewer queries" alone
is not the acceptance criterion.

## Forbidden actions

- Do **not** post a root cause you have not reproduced, and do not post
  candidate theories to the thread. One acknowledgement, one RCA.
- Do **not** widen the fix: no refactors, no drive-by cleanups, no changes to
  other services or to the alert rules, thresholds, scenario catalog, seeds or
  recorded gate evidence. A red gate is a real divergence or a fixture defect;
  fix the cause, never the measurement.
- Do **not** silence the alert (edit the rule, raise the threshold, add an
  inhibition) as a fix.
- Do **not** push to the before-state branch or merge anything yourself. The
  PR is the deliverable; a human merges it.
- Do **not** ask the on-call engineer what to do next. The page is the brief;
  if something is genuinely missing, say exactly what and stop.
- Do **not** identify the requester or include customer-identifying content in
  the PR, the commits, or the thread.
