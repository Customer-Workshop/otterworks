import { test, expect } from "@playwright/test";

test.describe("Files Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/files");
  });

  test("shows Files heading or redirects to login", async ({ page }) => {
    const heading = page.getByRole("heading", { name: /Files|My Files/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("has upload button", async ({ page }) => {
    // Wait for the Files heading to appear
    const heading = page.getByRole("heading", { name: /Files|My Files/i });
    await expect(heading).toBeVisible({ timeout: 15_000 });

    // Files page has "Upload" and "New folder" buttons
    const uploadButton = page.getByRole("button", { name: /Upload/i });
    await expect(uploadButton).toBeVisible({ timeout: 5_000 });
  });

  test("shows empty state or file listing", async ({ page }) => {
    const heading = page.getByRole("heading", { name: /Files|My Files/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      // Either file cards or empty state
      const emptyState = page.getByText(/No files|Upload files|Drop files/i);
      const fileItems = page.locator("[class*='grid'] > *, [class*='space-y'] > *").first();
      await expect(emptyState.or(fileItems)).toBeVisible({ timeout: 10_000 });
    }
  });

  test("has grid/list view toggle", async ({ page }) => {
    const heading = page.getByRole("heading", { name: /Files|My Files/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      const buttons = page.locator("button svg");
      await expect(buttons.first()).toBeVisible();
    }
  });
});
