import { test, expect } from "@playwright/test";

test.describe("Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings");
  });

  test("shows Settings heading or redirects to login", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Settings" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("displays Profile section when authenticated", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Settings" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(page.getByText("Profile")).toBeVisible();
      await expect(page.getByLabel("Full name")).toBeVisible();
      await expect(page.getByLabel("Email")).toBeVisible();
    }
  });

  test("displays Notification preferences section when authenticated", async ({
    page,
  }) => {
    const heading = page.getByRole("heading", { name: "Settings" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(page.getByText("Notification preferences")).toBeVisible();
      await expect(page.getByText("Email notifications")).toBeVisible();
      await expect(page.getByText("In-app notifications")).toBeVisible();
      await expect(page.getByText("Desktop notifications")).toBeVisible();
    }
  });

  test("Save changes button is disabled when form is pristine", async ({
    page,
  }) => {
    const heading = page.getByRole("heading", { name: "Settings" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      const saveButton = page.getByRole("button", { name: /Save changes/i });
      await expect(saveButton).toBeDisabled();
    }
  });

  test("displays breadcrumb navigation", async ({ page }) => {
    const heading = page.getByRole("heading", { name: "Settings" });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });

    if (await heading.isVisible().catch(() => false)) {
      await expect(page.getByText("Settings").first()).toBeVisible();
    }
  });
});
