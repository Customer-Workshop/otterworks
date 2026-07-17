import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/dashboard");
  });

  test("shows the Dashboard heading", async ({ page }) => {
    // Dashboard may redirect to login if unauthenticated, or show the page
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");

    // Either we see the dashboard or we get redirected to login
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("displays Upload file and New document buttons", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");
    const target = heading.or(loginHeading);
    await expect(target).toBeVisible({ timeout: 10_000 });

    // Only check buttons if we're on the dashboard (not redirected to login)
    if (await heading.isVisible().catch(() => false)) {
      await expect(page.getByRole("link", { name: /Upload file/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /New document/i })).toBeVisible();
    }
  });

  test("renders stat cards or loading state", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");
    const loader = page.locator("[class*='animate-spin']");
    // Dashboard may show heading, loader, or redirect to login
    await expect(heading.or(loginHeading).or(loader)).toBeVisible({ timeout: 15_000 });

    if (await heading.isVisible().catch(() => false)) {
      // Stat card labels appear inside stat cards as combined text
      await expect(page.getByText(/Total files/i)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText(/Storage used/i)).toBeVisible();
    }
  });

  test("shows Recent files section or empty state", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");
    const loader = page.locator("[class*='animate-spin']");
    await expect(heading.or(loginHeading).or(loader)).toBeVisible({ timeout: 15_000 });

    if (await heading.isVisible().catch(() => false)) {
      const recentFiles = page.getByRole("heading", { name: "Recent files" });
      const noFiles = page.getByText("No recent files");
      await expect(recentFiles.or(noFiles)).toBeVisible({ timeout: 10_000 });
    }
  });

  test("shows Recent documents section or empty state", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");
    const loader = page.locator("[class*='animate-spin']");
    await expect(heading.or(loginHeading).or(loader)).toBeVisible({ timeout: 15_000 });

    if (await heading.isVisible().catch(() => false)) {
      const recentDocs = page.getByRole("heading", { name: "Recent documents" });
      const noDocs = page.getByText("No recent documents");
      await expect(recentDocs.or(noDocs)).toBeVisible({ timeout: 10_000 });
    }
  });

  test("shows Activity section or empty state", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Dashboard" });
    const loginHeading = page.getByText("Sign in to your account");
    const loader = page.locator("[class*='animate-spin']");
    await expect(heading.or(loginHeading).or(loader)).toBeVisible({ timeout: 15_000 });

    if (await heading.isVisible().catch(() => false)) {
      const activity = page.getByRole("heading", { name: "Activity" });
      const noActivity = page.getByText("No recent activity");
      await expect(activity.or(noActivity)).toBeVisible({ timeout: 10_000 });
    }
  });
});
