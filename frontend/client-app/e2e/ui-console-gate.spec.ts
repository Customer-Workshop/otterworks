import { test, expect } from "@playwright/test";
import { registerUser, expectDashboard } from "./fixtures/test-helpers";
import {
  captureRoute,
  describeObservations,
  isAccepted,
  loadSweepConfig,
  observe,
  type AcceptedRule,
  type Observation,
} from "./fixtures/ui-observer";

/**
 * Sweep every authenticated route in one session and fail on any console error
 * or 4xx/5xx response that is not suppressed by an open registry finding.
 *
 * Suppressions come from qa/registry.yaml via the harness
 * (`python3 qa/harness/ui_gate.py gate`); running this spec directly suppresses
 * nothing. Screenshots for each route land in qa/reports/screenshots/.
 *
 * A suppression that matches nothing fails the sweep too: the defect it covers
 * no longer reproduces, and left in place it would mask the next regression on
 * that route.
 */
const { routes, accepted } = loadSweepConfig();

test.describe("authenticated route sweep", () => {
  test("no unregistered console or network errors", async ({ page }) => {
    const state = { route: "/register" };
    const observations = observe(page, state);

    await registerUser(page);
    await expectDashboard(page);

    const unexpected: Observation[] = [];
    const suppressed: Observation[] = [];
    const used = new Set<AcceptedRule>();

    for (const route of routes) {
      state.route = route;
      const before = observations.length;
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      await captureRoute(page, route);

      for (const obs of observations.slice(before)) {
        const matching = accepted.filter((rule) => isAccepted(obs, [rule]));
        for (const rule of matching) used.add(rule);
        (matching.length > 0 ? suppressed : unexpected).push(obs);
      }
    }

    if (suppressed.length > 0) {
      console.log(
        `known open findings still firing (suppressed):\n${describeObservations(suppressed)}`
      );
    }

    expect(
      unexpected,
      `unregistered UI errors — either fix them or register them in qa/registry.yaml:\n${describeObservations(
        unexpected
      )}`
    ).toEqual([]);

    const stale = accepted.filter((rule) => !used.has(rule));
    expect(
      stale.map(
        (r) =>
          `[${r.finding}] url_pattern=${r.url_pattern ?? "-"} status=${
            r.status ?? "-"
          } message=${r.message ?? "-"}`
      ),
      "stale suppressions — these accepted_console_errors matched nothing on the " +
        "sweep, so the defect no longer reproduces as recorded. Reconcile the " +
        "registry (verify and remediate the finding, or re-triage its symptom) " +
        "rather than leaving a suppression that would mask the next regression"
    ).toEqual([]);
  });
});
