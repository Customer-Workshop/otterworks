import { test, expect } from "@playwright/test";

test.describe("Landing Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("displays the hero section with branding", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "OtterWorks" })).toBeVisible();
    await expect(
      page.getByText("Collaborative document and file management")
    ).toBeVisible();
  });

  test("shows Sign In and Create Account CTAs", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Sign In" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Create Account" })
    ).toBeVisible();
  });

  test("renders all six feature cards", async ({ page }) => {
    const features = [
      "File Management",
      "Document Editing",
      "Real-time Collaboration",
      "Powerful Search",
      "Secure Sharing",
      "Instant Notifications",
    ];
    for (const title of features) {
      await expect(page.getByText(title, { exact: true })).toBeVisible();
    }
  });

  test("Sign In link navigates to /login", async ({ page }) => {
    await page.getByRole("link", { name: "Sign In" }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("Create Account link navigates to /register", async ({ page }) => {
    await page.getByRole("link", { name: "Create Account" }).click();
    await expect(page).toHaveURL(/\/register/);
  });

  test("footer is visible with copyright text", async ({ page }) => {
    await expect(
      page.getByText("Collaborative document & file management platform")
    ).toBeVisible();
  });
});
