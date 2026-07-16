---
name: playwright-test-planner
description: >
  Explore a running web app with the Playwright test MCP and produce a
  human-readable Markdown test plan under specs/. This is the "planner" stage
  of Playwright's test-agents loop (planner -> generator -> healer). Use when
  asked to plan end-to-end test coverage for a web UI in OtterWorks.
---

# Playwright Test Planner (OtterWorks)

You are an expert web test planner. You explore a running application and
produce a precise, human-readable Markdown test plan that the
`playwright-test-generator` skill later turns into executable Playwright tests.

## Prerequisites

- The `playwright-test` MCP server must be available (tools are prefixed
  `mcp__playwright-test__*`, e.g. `planner_setup_page`, `browser_snapshot`,
  `planner_save_plan`). If those tools are not present, the org admin still
  needs to enable the custom `playwright-test` MCP — stop and report that.
- The target app must be running. For the web app: `cd frontend/web-app &&
  npm run dev` (serves http://localhost:3000). Public pages (`/login`,
  `/register`, landing, navigation) work without the backend; authenticated
  flows need the full stack (`make up`).
- A **seed test** bootstraps the environment/fixtures. In this repo the seed
  lives at `frontend/web-app/e2e/seed.spec.ts` and reuses the helpers in
  `frontend/web-app/e2e/fixtures/test-helpers.ts`.

## Workflow

1. **Navigate and Explore**
   - Invoke `planner_setup_page` once before any other tool to set up the page.
   - Explore via `browser_snapshot`; avoid screenshots unless necessary.
   - Use `browser_*` tools to discover interactive elements, forms, navigation
     paths, and functionality.
2. **Analyze User Flows** — map primary journeys and critical paths; consider
   different user types (guest, logged-in USER, ADMIN).
3. **Design Comprehensive Scenarios** — happy paths, edge/boundary cases, and
   error/validation handling.
4. **Structure the Plan** — each scenario has a clear title, numbered
   step-by-step instructions, expected outcomes, starting-state assumptions
   (assume fresh/blank state), and success/failure criteria. Reference the seed
   test at the top of each scenario group (`**Seed:** e2e/seed.spec.ts`).
5. **Save** — submit the plan with `planner_save_plan`. In this repo, plans are
   saved under `frontend/web-app/specs/<feature>.md`.

## Quality standards

- Steps must be specific enough for any tester (human or the generator) to
  follow deterministically.
- Include negative testing scenarios.
- Keep scenarios independent and runnable in any order.
- Prefer role/label-based intents (they map cleanly to Playwright locators),
  matching the conventions already used in `e2e/`.
