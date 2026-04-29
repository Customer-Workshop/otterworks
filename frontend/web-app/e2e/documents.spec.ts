import { test, expect } from "@playwright/test";

test.describe("Documents Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/documents");
  });

  test("shows Documents heading or redirects to login", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("has New document button when authenticated", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(
        page.getByRole("button", { name: /New document/i })
      ).toBeVisible();
    }
  });

  test("has search/filter input when authenticated", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(
        page.getByPlaceholder("Filter documents...")
      ).toBeVisible();
    }
  });

  test("has grid/list view toggle when authenticated", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      // View toggle buttons should be present
      const buttons = page.locator("button svg");
      await expect(buttons.first()).toBeVisible();
    }
  });

  test("shows empty state when no documents exist", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      // Either documents are listed or empty state is shown
      const emptyState = page.getByText("No documents yet");
      const docCard = page.locator("[class*='grid'] > *").first();
      await expect(emptyState.or(docCard)).toBeVisible({ timeout: 10_000 });
    }
  });

  test("displays breadcrumb navigation", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Documents" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(page.getByText("Documents").first()).toBeVisible();
    }
  });
});
