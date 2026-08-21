# Playbook: Close a user-facing defect you can only see in a browser

## Overview

Use this for defects that exist **in front of the user**, not in a stack trace:
a page that renders its empty state while its own data calls fail, a form that
posts to a route that does not exist, a destructive action with no confirmation,
a preview that never previews. Static analysis and unit tests pass on all of
them, which is exactly why they survive in a mature codebase.

The procedure is a browser feedback loop with a programmatic gate at both ends.
You open the app, watch it fail, write an executable reproduction that fails for
the same reason, fix the code, and then prove the fix by making that spec pass
*and* by removing the suppression that let the whole suite stay green while the
defect was open. The screenshots are evidence for a human reviewer; the specs and
the gate are what actually decide whether the work is done.

## The one principle: see it, then encode it

Every step is anchored to what the application does when a real session drives
it. A defect you have only reasoned about is not reproduced, and a fix you have
only reasoned about is not verified.

Two consequences worth internalizing:

- **The reproduction spec must fail before it passes.** A spec written after the
  fix, that has never failed, proves nothing — it may be asserting behavior the
  app always had. Run it against the unfixed app and require a red result first.
- **A defect stays visible until the gate enforces it.** The route sweep
  suppresses the errors belonging to defects that are still open, so the suite
  stays usable while a backlog burns down. Fixing a defect means deleting its
  suppression in the same change; otherwise the gate keeps lying on its behalf
  forever.

## Required from user

- **The finding** — an id from the defect registry, or a description of what
  looked wrong in the browser. If the registry has no entry, add one first: id,
  symptom, expected behavior, the routes it appears on, severity.
- **A running target** — a local stack or an isolated per-attendee deployment.
  Never a target someone else is presenting from: this procedure registers
  accounts, uploads files, and deletes things.
- **The scope of the fix** — which surface owns the behavior (frontend, the
  service behind it, or the contract between them). If the registry entry does
  not say, decide it from the evidence and state the decision in the PR.

## Procedure

1. **Read the registry and the report it came from.** Understand the claimed
   symptom and, more importantly, the *expected* behavior — the fix is graded
   against the expectation, not against the symptom disappearing. Confirm the
   finding is still `open` and see whether it already carries a spec.
2. **Reproduce it in a browser with your own eyes.** Start the app, sign in,
   navigate to the affected route, and watch the network and console panels
   while the page loads. Capture a screenshot of the failing state and the exact
   request/response that misbehaves (method, path, status, body). Attribute the
   failure to a specific caller in the code — a component, hook, or handler —
   before writing anything.
3. **Encode the expectation as a spec, and require it to fail.** Write the
   browser test to assert the *expected* behavior from the registry, then run it
   against the unfixed app. It must fail, and it must fail for the reason you
   observed — not on a selector typo or a login timeout. Read the failure output
   and confirm the two match.
4. **Fix it at the layer that owns the behavior.** Trace the failing call to its
   contract: a missing header the caller never sends, an endpoint the backend
   never exposed, a state the component never renders. Prefer the smallest change
   that makes the contract true on both sides. If the honest fix is "this surface
   has no backend", make the UI tell the truth (disable the control, show the
   real state) rather than faking success.
5. **Verify, and drop the suppression.** Make the spec pass, flip the registry
   entry to remediated, delete its accepted-error suppression, and run the full
   gate: the route sweep plus every remediated finding's spec. The sweep now
   fails on any error belonging to the finding you just closed. Capture the
   after-screenshot from the same route and viewport as the before.
6. **Look for the neighbors while you are in there.** A browser pass over the
   whole authenticated surface costs one session and routinely finds defects
   nobody filed. Register what you find — do not fix it in the same change.
   Unregistered errors fail the gate by design, so a new one you leave behind
   blocks the next run until someone accounts for it.
7. **Land it with the evidence.** One finding per branch and per pull request.
   Put the before/after screenshots, the failing-then-passing spec output, and
   the gate summary in the PR body; the report directory is generated output and
   is not committed. State plainly which registry entries you changed and which
   new findings you registered.
8. **Fan out the rest.** When more than one finding is ready, run one session per
   finding rather than one session for the batch: each gets its own branch, its
   own reproduction, and its own reviewable PR, and a failure in one does not
   strand the others.

## Specifications (postconditions)

- The finding's spec exists, failed against the unfixed app, and passes against
  the fix. Both results were observed in this run, not assumed.
- The registry entry is `remediated` and carries no accepted-error suppression.
- The full gate passes: no unregistered console error or 4xx/5xx response on any
  swept authenticated route.
- Before and after screenshots exist for the affected route, from the same
  viewport, and are attached to the PR.
- Any new defect noticed during the pass is registered as `open` with a symptom,
  an expectation, and its routes — and is not fixed in the same PR.
- The change is on its own branch. Nothing is committed to the before-state
  branch, and no generated report or screenshot is committed.

## Advice and pointers

- Read the failing request before reading the code. A 400 with a message naming a
  missing parameter tells you which side of the contract broke in one line; the
  component that made the call is usually three files from where you would have
  started guessing.
- Suspect the identity plumbing first for "works in tests, fails in the app"
  defects. Test doubles supply headers and tokens that the real edge is supposed
  to attach, so a backend that requires a caller header and a frontend that never
  sends it pass their own suites separately and fail together.
- Distinguish "empty" from "broken" in the UI, always. A page that renders its
  empty state on a failed request is worse than one that shows an error: it makes
  a broken system look healthy, and it hides the defect from everyone including
  the next agent.
- Keep the reproduction on the shortest path. Register a fresh user, do the
  minimum to reach the state, assert one thing. Long setup chains fail for
  unrelated reasons and get muted.
- Do not widen a suppression to get to green. If the gate flags something you did
  not expect, it is either a real defect (register it) or your fix leaked (fix
  it). A broadened pattern silently covers future regressions too.
- Worked example, from the run that produced this playbook: every authenticated
  route was quietly firing `400` on the notification calls. The backend requires
  the caller's identity as a header; the browser client called the gateway
  without it, and the notifications page rendered "no notifications" on the
  failure — so the UI looked healthy on every screen. Unit tests passed on both
  sides, because each side's tests supplied what the other was missing. The
  browser sweep found it in the first minute, and the gate would not go green
  until the contract was true end to end.

## Forbidden actions

- Do **not** write the spec after the fix and skip the red run. A reproduction
  that has never failed is not a reproduction.
- Do **not** mark a finding remediated while keeping its suppression, and do not
  add a suppression for a defect you introduced.
- Do **not** weaken the assertion, extend a timeout, or mute a route to reach
  green. A red gate is a real divergence or a broken fixture; both are fixed at
  the root.
- Do **not** fix more than one registered finding per pull request, and do not
  mix newly registered findings with a fix.
- Do **not** commit generated reports or screenshots, and do not push to the
  before-state branch.
- Do **not** run against a shared or someone else's target — the loop writes and
  deletes real data.
