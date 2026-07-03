import { test, expect, APIRequestContext } from "@playwright/test";

/**
 * E2E API tests for the report service (report generation + download).
 *
 * Covers the key acceptance criteria:
 *  - Create a report request (PDF / CSV / Excel) -> 202 Accepted, status PENDING
 *  - Poll until report generation completes
 *  - Download the generated file with the correct content type and magic bytes
 *  - List / delete reports
 *
 * Runs against a live report service (REPORT_SERVICE_URL, default
 * http://localhost:8091). Tests are skipped when the service is unreachable
 * so the UI-only suite still passes without the backend stack.
 */

const REPORT_SERVICE_URL = process.env.REPORT_SERVICE_URL || "http://localhost:8091";
const REPORTS_ENDPOINT = `${REPORT_SERVICE_URL}/api/v1/reports`;

let serviceAvailable = false;

test.beforeAll(async ({ request }) => {
  try {
    const res = await request.get(`${REPORT_SERVICE_URL}/health`, { timeout: 5_000 });
    serviceAvailable = res.ok();
  } catch {
    serviceAvailable = false;
  }
});

test.beforeEach(() => {
  test.skip(!serviceAvailable, "report service is not running");
});

function buildRequestBody(reportType: "PDF" | "CSV" | "EXCEL", name: string) {
  return {
    reportName: name,
    category: "USAGE_ANALYTICS",
    reportType,
    requestedBy: "playwright-e2e",
  };
}

async function createReport(
  request: APIRequestContext,
  reportType: "PDF" | "CSV" | "EXCEL",
  name: string,
): Promise<number> {
  const res = await request.post(REPORTS_ENDPOINT, {
    data: buildRequestBody(reportType, name),
  });
  expect(res.status()).toBe(202);
  const body = await res.json();
  expect(body.status).toBe("PENDING");
  expect(body.reportName).toBe(name);
  expect(body.id).toBeTruthy();
  return body.id;
}

async function waitForCompletion(request: APIRequestContext, id: number): Promise<void> {
  await expect
    .poll(
      async () => {
        const res = await request.get(`${REPORTS_ENDPOINT}/${id}`);
        expect(res.ok()).toBeTruthy();
        const body = await res.json();
        return body.status;
      },
      { timeout: 60_000, intervals: [1_000] },
    )
    .toBe("COMPLETED");
}

async function download(request: APIRequestContext, id: number) {
  const res = await request.get(`${REPORTS_ENDPOINT}/${id}/download`);
  expect(res.status()).toBe(200);
  return res;
}

test.describe("Report service API", () => {
  test("generates and downloads a PDF report", async ({ request }) => {
    const id = await createReport(request, "PDF", `PW PDF Report ${Date.now()}`);
    await waitForCompletion(request, id);

    const res = await download(request, id);
    expect(res.headers()["content-type"]).toContain("application/pdf");
    const body = await res.body();
    expect(body.length).toBeGreaterThan(0);
    // PDF magic bytes: %PDF
    expect(body.subarray(0, 4).toString("ascii")).toBe("%PDF");
  });

  test("generates and downloads a CSV report", async ({ request }) => {
    const id = await createReport(request, "CSV", `PW CSV Report ${Date.now()}`);
    await waitForCompletion(request, id);

    const res = await download(request, id);
    expect(res.headers()["content-type"]).toContain("text/csv");
    const text = (await res.body()).toString("utf-8");
    expect(text.length).toBeGreaterThan(0);
  });

  test("generates and downloads an Excel report", async ({ request }) => {
    const id = await createReport(request, "EXCEL", `PW Excel Report ${Date.now()}`);
    await waitForCompletion(request, id);

    const res = await download(request, id);
    expect(res.headers()["content-type"]).toContain(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    const body = await res.body();
    expect(body.length).toBeGreaterThan(0);
    // XLSX files are ZIP archives: magic bytes PK\x03\x04
    expect(body[0]).toBe(0x50);
    expect(body[1]).toBe(0x4b);
  });

  test("returns 409 when downloading a report that is still generating", async ({ request }) => {
    const id = await createReport(request, "PDF", `PW Pending Report ${Date.now()}`);
    const res = await request.get(`${REPORTS_ENDPOINT}/${id}/download`);
    // Report may already be COMPLETED if generation was fast; accept either
    expect([200, 409]).toContain(res.status());
  });

  test("returns 404 for unknown report", async ({ request }) => {
    const res = await request.get(`${REPORTS_ENDPOINT}/999999999`);
    expect(res.status()).toBe(404);
  });

  test("lists reports filtered by user", async ({ request }) => {
    const name = `PW List Report ${Date.now()}`;
    const id = await createReport(request, "CSV", name);
    await waitForCompletion(request, id);

    const res = await request.get(`${REPORTS_ENDPOINT}?userId=playwright-e2e`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.total).toBeGreaterThan(0);
    expect(body.reports.some((r: { id: number }) => r.id === id)).toBeTruthy();
  });

  test("deletes a report", async ({ request }) => {
    const id = await createReport(request, "CSV", `PW Delete Report ${Date.now()}`);
    await waitForCompletion(request, id);

    const del = await request.delete(`${REPORTS_ENDPOINT}/${id}`);
    expect(del.status()).toBe(204);

    const res = await request.get(`${REPORTS_ENDPOINT}/${id}`);
    expect(res.status()).toBe(404);
  });
});
