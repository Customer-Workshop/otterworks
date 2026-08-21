import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";

export type AcceptedRule = {
  /** Registry finding this suppression belongs to, e.g. "OW-UI-101". */
  finding: string;
  /** Substring the request URL (or console location) must contain. */
  url_pattern?: string;
  /** HTTP status the failed response must carry. */
  status?: number;
  /** Substring a console error message must contain. */
  message?: string;
};

export type Observation = {
  route: string;
  kind: "console" | "network";
  status?: number;
  url?: string;
  text: string;
};

export type SweepConfig = {
  routes: string[];
  accepted: AcceptedRule[];
};

const FALLBACK_ROUTES = [
  "/dashboard",
  "/files",
  "/documents",
  "/search",
  "/shared",
  "/trash",
  "/notifications",
  "/settings",
];

/**
 * Read the sweep config the harness writes (qa/reports/accepted-console.json).
 *
 * Absent config means nothing is suppressed: run standalone, the gate is
 * strict. Suppressions only ever come from findings the registry still lists
 * as `open`, so a remediated finding cannot be waved through.
 */
export function loadSweepConfig(): SweepConfig {
  const file = process.env.UI_ACCEPTED_CONSOLE;
  if (!file || !fs.existsSync(file)) {
    return { routes: FALLBACK_ROUTES, accepted: [] };
  }
  const raw = JSON.parse(fs.readFileSync(file, "utf8")) as Partial<SweepConfig>;
  return {
    routes: raw.routes?.length ? raw.routes : FALLBACK_ROUTES,
    accepted: raw.accepted ?? [],
  };
}

/**
 * Match an observation against the suppression rules.
 *
 * A failed request surfaces twice: as the response itself, which carries a
 * status, and as a browser console error, which does not. `status` is therefore
 * only applied to network observations — a console error is matched on its text
 * and location, so a rule must still name a `url_pattern` or a `message` to
 * suppress one. A rule with nothing but a status never suppresses console noise.
 */
export function isAccepted(obs: Observation, accepted: AcceptedRule[]): AcceptedRule | undefined {
  return accepted.find((rule) => {
    const haystack = `${obs.url ?? ""} ${obs.text}`;
    if (rule.url_pattern && !haystack.includes(rule.url_pattern)) return false;
    if (rule.message && !obs.text.includes(rule.message)) return false;
    if (obs.kind === "network") {
      if (rule.status !== undefined && rule.status !== obs.status) return false;
      return (
        rule.status !== undefined || Boolean(rule.url_pattern) || Boolean(rule.message)
      );
    }
    return Boolean(rule.url_pattern) || Boolean(rule.message);
  });
}

/**
 * Attach console-error and failed-response listeners to the page.
 *
 * The returned array is appended to for the page's lifetime; set `route`
 * between navigations so each observation is attributed to the route that
 * produced it.
 */
export function observe(page: Page, state: { route: string }): Observation[] {
  const seen: Observation[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    seen.push({ route: state.route, kind: "console", text: msg.text(), url: msg.location().url });
  });
  page.on("requestfailed", (req) => {
    seen.push({
      route: state.route,
      kind: "network",
      url: req.url(),
      text: `${req.method()} ${req.url()} failed: ${req.failure()?.errorText ?? "unknown"}`,
    });
  });
  page.on("response", (res) => {
    if (res.status() < 400) return;
    seen.push({
      route: state.route,
      kind: "network",
      status: res.status(),
      url: res.url(),
      text: `${res.status()} ${res.request().method()} ${res.url()}`,
    });
  });
  return seen;
}

/** Screenshot into qa/reports/screenshots/ so runs leave visual evidence. */
export async function captureRoute(page: Page, route: string): Promise<string> {
  const dir = path.resolve(__dirname, "../../../../qa/reports/screenshots");
  fs.mkdirSync(dir, { recursive: true });
  const name = `${route.replace(/^\//, "").replace(/\//g, "-") || "root"}.png`;
  const file = path.join(dir, name);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

export function describeObservations(items: Observation[]): string {
  return items
    .map((o) => `  [${o.route}] ${o.kind}: ${o.text}`)
    .join("\n");
}
