import { test, expect } from "@playwright/test";

test.describe("Notifications Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/notifications");
  });

  test("shows Notifications heading or redirects to login", async ({ page }) => {
    const heading = page.getByRole("heading", { name: /Notification/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("shows empty state or notification list", async ({ page }) => {
    // Wait for the Notifications heading to appear
    const heading = page.getByRole("heading", { name: /Notification/i });
    await expect(heading).toBeVisible({ timeout: 15_000 });

    // Wait for loading to finish, then check for empty state or notification items
    const emptyState = page.getByText(/No notifications/i);
    const notifItems = page.locator("[class*='divide-y'] > *").first();
    await expect(emptyState.or(notifItems)).toBeVisible({ timeout: 15_000 });
  });
});
