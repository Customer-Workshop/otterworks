# Demo-Day Runbook — AWS Portal Showcase (night-before staging, one live beat)

Companion to the per-run run-of-show
(`docs/tech-partnerships/runbook-aws-portal-showcase.md`, written by each
`tp-run/aws-*` run). That file carries the run's URLs and observed numbers;
this one is the presenter's script: stage everything the night before, run
exactly ONE beat live — the alarm→Devin incident loop — and keep every act
visual enough for a non-technical audience.

## Why one live beat, and its timing budget

Measured on a full rehearsal of this estate:

| Segment | Duration |
|---|---|
| Stage the fault (CHAOS_FAULT canary publish + warm + traffic + 60s alarm evaluation) | ~3–4 min |
| Alarm → EventBridge → webhook → Devin session investigates, repoints the alias, verifies 200s, opens the audit PR | ~6–7 min |
| Audit PR CI green | +2–3 min |

**Total live loop ≈ 10–12 min.** Trigger it in the first 30 seconds of the
demo and let it cook underneath the before/after acts; it becomes the finale.

## Night-before checklist (everything except the live beat)

1. Namespace green: `canary.py status` per context (alias `live` at the
   healthy version, 100%, no extra weights), every alarm OK, DLQ and
   quarantine empty, no `CHAOS_FAULT` on any function's `$LATEST`,
   `terraform plan` clean.
2. Fresh evidence, recomputed from the estate: golden-transcript replay
   (expect 20/20 twice, with credentials) and async recon; run
   `make tp-validate-recon` on the artifacts.
3. Render the visuals from those artifacts (see below): parity scorecard,
   load/cost comparison page.
4. **Fire one complete test incident** (same CHAOS_FAULT staging as the live
   beat) and keep its artifacts — alarm-history entry, spawned Devin session
   URL, merged audit PR. This is both the webhook smoke test and the fallback
   narrative if the live loop misbehaves on stage.
5. Verify the Devin automation webhook is applied and its EventBridge rule
   has a target (`aws events list-targets-by-rule --rule
   ow-tp-portal-<ns>-alarm-to-devin`) — without it the live beat silently
   never fires.
6. Reset to clean green afterwards (alias restored, alarms OK, DLQ empty),
   and reset the demo page's localStorage (base URL + token).
7. Preload browser tabs in act order: demo page → parity scorecard →
   load/cost page → CloudWatch dashboard → Devin sessions list → GitHub PRs
   on the run branch.

## Rendering the visuals

Both renderers are stdlib-only and emit self-contained HTML (openable from
`file://` or dropped onto the hosted demo site). Rehearse offline against
`scripts/tp_portal/samples/` (hand-written samples, never evidence — the
parity sample includes one planted failure so you can show what a caught
conversion mistake looks like).

```bash
# Parity scorecard: every golden-transcript step as a green/red row,
# failing steps rendered as an expected-vs-actual diff
python3 scripts/tp_portal/render_scorecard.py \
  docs/tech-partnerships/recon/<parity>.recon.json --out parity-scorecard.html

# Before/after load + cost page (curve chart appears when the load reports
# carry a per-second "timeseries"; see the load-test tooling)
python3 scripts/tp_portal/render_load_charts.py \
  --before load-monolith.json --after load-aws.json \
  --before-label "Legacy monolith (one VM)" --after-label "Serverless estate" \
  --vm-monthly-usd <vm_cost> --out load-comparison.html
```

## Run-of-show (~15 min)

**Act 0 — light the fuse (0:00, 30s, on screen).** Stage the live incident
with the run's one-command target (`make demo-incident NS=<ns>` where the run
provides it, otherwise the CHAOS_FAULT canary + traffic commands from the
run's runbook). Narrate: "I just shipped a broken release of the converted
code — we'll come back to see who notices."

**Act 1 — BEFORE (2–3 min).** Demo page pointed at the legacy monolith:
three capability panels, one process, one blast radius. Kill the process —
the whole page reds out at once. Restart it.

**Act 2 — the contract (2 min).** Parity scorecard page: 20 green rows =
"every recorded behavior of the old system, replayed identically against the
new one." Flip to the sample scorecard with the planted failure: "and this is
what a conversion mistake looks like when the contract catches it — a red
row with the exact divergence."

**Act 3 — AFTER (3–4 min).** Flip the demo page's base URL to the live
gateway (the cutover moment: same page, same panels, now serverless). Then
the load/cost page: the monolith's latency curve climbing and erroring while
the estate stays flat, and the idle-cost card ($X/month VM vs ≈$0).

**Act 4 — CATCH, live (5–7 min).** By now the alarm has fired. Status strip /
dashboard goes red → the spawned Devin session, open in a tab, investigating.
While it works, walk last night's completed incident (session + merged audit
PR): "here's the full arc." Then the live one lands: alias repointed to the
known-good version, endpoints green, alarm back to OK, audit PR on GitHub.
Nobody touched a keyboard to fix it.

**Act 5 — close (1 min).** Hand-off picture: alarms OK, DLQ empty,
`terraform plan` clean — and the run's rollup table (unit × behavior replaced
× live verification × PR).

## Presenter guardrails

- Never run live: WAF burst shed, Step Functions triage walkthrough, load
  tests — rate-rule lag and stage throttling make them slow and
  anticlimactic. Show their night-before artifacts instead.
- Do not remediate the live incident yourself — the spawned session fixing
  it IS the beat. If it stalls past the budget, pivot to the night-before
  incident's artifacts and let the live one land during Q&A.
- The demo token is a sensitive Terraform output: paste it into the page's
  header field, never echo it into a visible terminal.
- The credential and namespace are shared: if anything looks off at the
  start (alarm already firing, plan not clean), another session may be
  driving the namespace — fall back to night-before artifacts rather than
  debugging on stage.
