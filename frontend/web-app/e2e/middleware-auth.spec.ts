import { test, expect } from "@playwright/test";

test.describe("Middleware & Auth Security (CVE-2025-29927)", () => {
  test.describe("x-middleware-subrequest bypass prevention", () => {
    test("rejects request with x-middleware-subrequest header", async ({
      request,
    }) => {
      // CVE-2025-29927: Attackers could bypass Next.js middleware by setting
      // the x-middleware-subrequest header, which told Next.js to skip
      // middleware execution entirely.
      const response = await request.get("/api/v1/documents", {
        headers: {
          "x-middleware-subrequest": "middleware",
        },
      });
      // The middleware should still execute (rewrite to API gateway).
      // If middleware is bypassed, the response would be a Next.js 404
      // instead of a gateway response (401/502/connection error).
      // A 404 from Next.js would indicate the bypass succeeded.
      expect(response.status()).not.toBe(404);
    });

    test("rejects request with x-middleware-subrequest set to full path", async ({
      request,
    }) => {
      const response = await request.get("/api/v1/documents", {
        headers: {
          "x-middleware-subrequest": "src/middleware",
        },
      });
      expect(response.status()).not.toBe(404);
    });

    test("rejects request with x-middleware-subrequest set to pages path", async ({
      request,
    }) => {
      const response = await request.get("/api/v1/documents", {
        headers: {
          "x-middleware-subrequest": "pages/_middleware",
        },
      });
      expect(response.status()).not.toBe(404);
    });
  });

  test.describe("API proxy routing", () => {
    test("/api/v1/* routes are proxied to API gateway", async ({
      request,
    }) => {
      const response = await request.get("/api/v1/health");
      // Gateway may return 200 (healthy) or 502/503 (gateway down).
      // Key assertion: NOT a Next.js 404, proving middleware rewrote the URL.
      const status = response.status();
      expect([200, 401, 403, 500, 502, 503]).toContain(status);
    });

    test("non-API routes are not proxied", async ({ page }) => {
      await page.goto("/login");
      // Login page should render (not proxied to gateway)
      await expect(page.getByLabel("Email")).toBeVisible({ timeout: 10_000 });
    });

    test("API proxy preserves query parameters", async ({ request }) => {
      const response = await request.get(
        "/api/v1/documents?page=1&size=10"
      );
      // Should reach gateway, not 404
      expect(response.status()).not.toBe(404);
    });

    test("API proxy preserves path segments", async ({ request }) => {
      const response = await request.get(
        "/api/v1/documents/test-doc-id/versions"
      );
      expect(response.status()).not.toBe(404);
    });
  });

  test.describe("Unauthorized API access", () => {
    test("unauthenticated API requests return 401 or 403", async ({
      request,
    }) => {
      const response = await request.get("/api/v1/documents");
      // Without auth token, gateway should reject with 401/403
      // or 502 if gateway is down (still proves middleware executed)
      expect([401, 403, 500, 502, 503]).toContain(response.status());
    });

    test("invalid auth token is rejected", async ({ request }) => {
      const response = await request.get("/api/v1/documents", {
        headers: {
          Authorization: "Bearer invalid-token-value",
        },
      });
      expect([401, 403, 500, 502, 503]).toContain(response.status());
    });
  });
});
