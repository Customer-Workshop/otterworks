import { test, expect, request as apiRequest } from "@playwright/test";

/**
 * End-to-end acceptance suite for the /search page (Jira PD-2).
 *
 * The client-app /search page talks to the search-service *through the API
 * gateway*, so this suite is a real acceptance gate for the Flask -> FastAPI
 * migration: every assertion exercises the running search-service.
 *
 * Each acceptance criterion is its own test. Data-dependent criteria seed
 * deterministic, tenant-scoped fixtures directly into the search-service
 * index (owner_id == the authenticated user) so results are stable and
 * isolated per Playwright worker.
 */

// The gateway the browser proxies to, and the search-service (for seeding).
const GATEWAY_URL = process.env.SEARCH_GATEWAY_URL || "http://localhost:8080";
const SEARCH_SERVICE_URL =
  process.env.SEARCH_SERVICE_URL || "http://localhost:8087";

const PLACEHOLDER = "Search files, documents, and folders...";

// Per-worker fixtures, populated in beforeAll.
let token = "";
let userId = "";
let marker = ""; // matches exactly one document + one file
let xssMarker = ""; // matches one document whose content carries an XSS payload
let docId = "";
let fileId = "";
let xssDocId = "";

function decodeSub(jwt: string): string {
  const payload = jwt.split(".")[1];
  return JSON.parse(Buffer.from(payload, "base64url").toString()).sub as string;
}

function hoursAgoIso(h: number): string {
  return new Date(Date.now() - h * 3_600_000).toISOString();
}

test.beforeAll(async () => {
  const api = await apiRequest.newContext();
  const rand = Math.random().toString(36).slice(2, 8);

  // Register a fresh, isolated user through the gateway.
  const email = `e2e-search-${Date.now()}-${rand}@otterworks.test`;
  const reg = await api.post(`${GATEWAY_URL}/api/v1/auth/register`, {
    data: { displayName: "E2E Search", email, password: "Passw0rd!23" },
  });
  expect(reg.ok(), `register failed: ${reg.status()}`).toBeTruthy();
  token = ((await reg.json()) as { accessToken: string }).accessToken;
  userId = decodeSub(token);

  // Distinct tokens (no shared suffix) so MeiliSearch typo-tolerance can't
  // make one marker match the other's document.
  marker = `markeralpha${rand}`;
  xssMarker = `xsspayloadbravo${Math.random().toString(36).slice(2, 8)}`;
  docId = `e2e-doc-${rand}`;
  fileId = `e2e-file-${rand}`;
  xssDocId = `e2e-xss-${rand}`;

  const headers = { "X-User-ID": userId };

  // A document that matches `marker`.
  let r = await api.post(`${SEARCH_SERVICE_URL}/api/v1/search/index/document`, {
    headers,
    data: {
      id: docId,
      title: `${marker} Budget Plan`,
      content: `The ${marker} budget plan covers revenue and spending.`,
      owner_id: userId,
      updated_at: hoursAgoIso(3),
    },
  });
  expect(r.status(), "index document").toBe(201);

  // A file that matches `marker`.
  r = await api.post(`${SEARCH_SERVICE_URL}/api/v1/search/index/file`, {
    headers,
    data: {
      id: fileId,
      name: `${marker}-report.pdf`,
      owner_id: userId,
      mime_type: "application/pdf",
      updated_at: hoursAgoIso(5),
    },
  });
  expect(r.status(), "index file").toBe(201);

  // A document whose content embeds an XSS payload alongside `xssMarker`.
  r = await api.post(`${SEARCH_SERVICE_URL}/api/v1/search/index/document`, {
    headers,
    data: {
      id: xssDocId,
      title: `${xssMarker} security note`,
      content: `${xssMarker} danger <img src=x onerror=alert(1)> tail`,
      owner_id: userId,
      updated_at: hoursAgoIso(2),
    },
  });
  expect(r.status(), "index xss document").toBe(201);

  // MeiliSearch indexing is task-based; wait until the fixtures are queryable.
  await expect
    .poll(
      async () => {
        const s = await api.get(
          `${SEARCH_SERVICE_URL}/api/v1/search/?q=${marker}`,
          { headers }
        );
        return ((await s.json()) as { total: number }).total;
      },
      { timeout: 20_000, message: "seeded documents never became searchable" }
    )
    .toBe(2);

  await api.dispose();
});

test.beforeEach(async ({ context }) => {
  // Authenticate the browser: the api-client reads the token from localStorage
  // and the gateway turns it into the X-User-ID the search-service scopes on.
  await context.addInitScript((t) => {
    localStorage.setItem("otter_access_token", t);
  }, token);
});

test.describe("Search page — static UI", () => {
  test("shows the Search heading", async ({ page }) => {
    await page.goto("/search");
    await expect(
      page.getByRole("heading", { name: "Search", exact: true })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("shows the search input with the expected placeholder", async ({
    page,
  }) => {
    await page.goto("/search");
    await expect(page.getByPlaceholder(PLACEHOLDER)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("shows the empty state before searching", async ({ page }) => {
    await page.goto("/search");
    await expect(page.getByText("Search OtterWorks")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText(
        "Find files, documents, and folders across your workspace"
      )
    ).toBeVisible();
  });

  test("can type a query into the search input", async ({ page }) => {
    await page.goto("/search");
    const input = page.getByPlaceholder(PLACEHOLDER);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("quarterly report");
    await expect(input).toHaveValue("quarterly report");
  });

  test("exposes the All / Files / Documents / Folders type filters", async ({
    page,
  }) => {
    await page.goto("/search");
    // Reveal the filter toggle (first type=button inside the search form).
    await page.locator("form button[type='button']").first().click();
    await expect(
      page.getByRole("button", { name: "All types", exact: true })
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByRole("button", { name: "Files", exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Documents", exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Folders", exact: true })
    ).toBeVisible();
  });
});

test.describe("Search page — results", () => {
  test('shows an "N results for query" summary', async ({ page }) => {
    await page.goto(`/search?q=${marker}`);
    // The summary paragraph echoes the count and the exact query.
    await expect(
      page.getByText(new RegExp(`2 results for .*${marker}`))
    ).toBeVisible({ timeout: 15_000 });
  });

  test("renders result rows with name, relative updated-at and correct routes", async ({
    page,
  }) => {
    await page.goto(`/search?q=${marker}`);

    // Document result -> /documents/:id
    const docRow = page.locator(`a[href="/documents/${docId}"]`);
    await expect(docRow).toBeVisible({ timeout: 15_000 });
    await expect(docRow).toContainText(`${marker} Budget Plan`);
    await expect(docRow).toContainText(/ago|just now/i);

    // File result -> /files/:id
    const fileRow = page.locator(`a[href="/files/${fileId}"]`);
    await expect(fileRow).toBeVisible();
    await expect(fileRow).toContainText(`${marker}-report.pdf`);
    await expect(fileRow).toContainText(/ago|just now/i);
  });

  test("type filter narrows results to the selected type", async ({ page }) => {
    await page.goto(`/search?q=${marker}`);
    await expect(page.getByText(new RegExp(`2 results for`))).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("form button[type='button']").first().click();

    // Documents only.
    await page.getByRole("button", { name: "Documents", exact: true }).click();
    await expect(page.getByText(new RegExp(`1 result for`))).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator(`a[href="/documents/${docId}"]`)).toBeVisible();
    await expect(page.locator(`a[href="/files/${fileId}"]`)).toHaveCount(0);

    // Files only.
    await page.getByRole("button", { name: "Files", exact: true }).click();
    await expect(page.getByText(new RegExp(`1 result for`))).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator(`a[href="/files/${fileId}"]`)).toBeVisible();
    await expect(page.locator(`a[href="/documents/${docId}"]`)).toHaveCount(0);
  });

  test("renders MeiliSearch <em> highlights as emphasis and stays XSS-safe", async ({
    page,
  }) => {
    await page.goto(`/search?q=${xssMarker}`);

    const row = page.locator(`a[href="/documents/${xssDocId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });

    // The matched term is emphasised via a real <em> element.
    const em = row.locator("em");
    await expect(em.first()).toBeVisible();
    await expect(em.first()).toHaveText(xssMarker);

    // The embedded <img onerror> payload must NOT become a live element...
    await expect(row.locator("img")).toHaveCount(0);
    // ...it must be rendered as inert, escaped text instead.
    await expect(row).toContainText("<img");
  });

  test('shows "No results found" for a gibberish query', async ({ page }) => {
    await page.goto("/search?q=zzznotarealquery999planttest");
    await expect(page.getByText("No results found")).toBeVisible({
      timeout: 15_000,
    });
  });
});
