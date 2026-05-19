import { test, expect } from "@playwright/test";

test.describe("Admin Users Page", () => {
  test("unauthenticated access to users page redirects to login", async ({
    page,
  }) => {
    await page.goto("/users");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  test("user detail route requires authentication", async ({ page }) => {
    await page.goto("/users/test-user-id");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });
});
