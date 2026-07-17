import { test, expect } from "@playwright/test";

test.describe("Shared Page", () => {
  test("shows Shared heading or redirects to login", async ({ page }) => {
    await page.goto("/shared");
    const heading = page.getByRole("heading", { name: /Shared/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("shows empty state or shared items", async ({ page }) => {
    await page.goto("/shared");
    const heading = page.getByRole("heading", { name: /Shared/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      const emptyState = page.getByText(/No shared|Nothing shared/i);
      const items = page.locator("[class*='grid'] > *, [class*='divide'] > *").first();
      await expect(emptyState.or(items)).toBeVisible({ timeout: 10_000 });
    }
  });
});

test.describe("Trash Page", () => {
  test("shows Trash heading or redirects to login", async ({ page }) => {
    await page.goto("/trash");
    const heading = page.getByRole("heading", { name: /Trash/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("shows empty state or trashed items", async ({ page }) => {
    await page.goto("/trash");
    const heading = page.getByRole("heading", { name: /Trash/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      const emptyState = page.getByText(/No deleted|Trash is empty|No items/i);
      const items = page.locator("[class*='grid'] > *, [class*='divide'] > *").first();
      await expect(emptyState.or(items)).toBeVisible({ timeout: 10_000 });
    }
  });
});
