import { test, expect } from "@playwright/test";

test.describe("Admin Navigation", () => {
  test("login page is accessible", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("OtterWorks Admin")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("unknown routes redirect to root", async ({ page }) => {
    await page.goto("/nonexistent-route");
    // Should redirect to root (which redirects to login if not authenticated)
    await expect(page).toHaveURL(/\/(login)?$/, { timeout: 10_000 });
  });

  test("protected routes redirect unauthenticated users to login", async ({
    page,
  }) => {
    const protectedRoutes = [
      "/users",
      "/audit",
      "/features",
      "/health",
      "/announcements",
      "/quotas",
      "/analytics",
      "/incidents",
    ];

    for (const route of protectedRoutes) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    }
  });
});
