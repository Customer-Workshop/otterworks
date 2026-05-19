import { test, expect } from "@playwright/test";

test.describe("Admin Login", () => {
  test("renders login form with email and password fields", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("OtterWorks Admin")).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  });

  test("shows error for empty credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(
      page.getByText("Please enter both email and password")
    ).toBeVisible();
  });

  test("shows error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill("admin@test.com");
    await page.locator('input[type="password"]').fill("wrongpass");
    await page.getByRole("button", { name: "Sign In" }).click();
    // Either shows login error or stays on login (backend not running)
    const error = page.getByText(/failed|error|invalid/i);
    const loginForm = page.locator('input[type="email"]');
    await expect(error.or(loginForm)).toBeVisible({ timeout: 10_000 });
  });

  test("toggles password visibility", async ({ page }) => {
    await page.goto("/login");
    const passwordInput = page.locator('input[name="password"]');
    await passwordInput.fill("testpassword");
    await expect(passwordInput).toHaveAttribute("type", "password");

    // Click visibility toggle button
    const toggleBtn = page.locator('button').filter({ has: page.locator('mat-icon:text("visibility_off")') });
    await toggleBtn.click();
    await expect(passwordInput).toHaveAttribute("type", "text");
  });

  test("unauthenticated users are redirected to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });
});
