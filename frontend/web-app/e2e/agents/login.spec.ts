import { test, expect } from "@playwright/test";
import { loginUser } from "../fixtures/test-helpers";

// spec: specs/login-and-navigation.md
// seed: e2e/seed.spec.ts

test.describe("Login Page", () => {
  test("Login form fields and branding are visible", async ({ page }) => {
    // 1. Navigate to `/login`.
    await page.goto("/login");
    // 2. Verify the Email field is visible.
    await expect(page.getByLabel("Email")).toBeVisible();
    // 3. Verify the Password field is visible.
    await expect(page.getByLabel("Password")).toBeVisible();
    // 4. Verify the Sign in button is visible.
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    // 5. Verify the OtterWorks branding is visible.
    await expect(page.getByText("OtterWorks")).toBeVisible();
    // 6. Verify the text "Sign in to your account" is visible.
    await expect(page.getByText("Sign in to your account")).toBeVisible();
  });

  test("Login validation rejects an empty email", async ({ page }) => {
    // 1. Navigate to `/login`.
    await page.goto("/login");
    // 2. Enter a password in the Password field.
    await page.getByLabel("Password").fill("somepassword");
    // 3. Activate the Sign in button.
    await page.getByRole("button", { name: "Sign in" }).click();
    // 4. Verify "Please enter a valid email" is visible.
    await expect(page.getByText("Please enter a valid email")).toBeVisible();
  });

  test("Login page links to registration", async ({ page }) => {
    // 1. Navigate to `/login`.
    await page.goto("/login");
    // 2. Verify the "Create one" link is visible.
    await expect(page.getByRole("link", { name: "Create one" })).toBeVisible();
    // 3. Activate the "Create one" link.
    await page.getByRole("link", { name: "Create one" }).click();
    // 4. Verify the browser URL is `/register`.
    await expect(page).toHaveURL(/\/register/);
  });

  test("Invalid credentials show an error", async ({ page }) => {
    // 1. Navigate to `/login` and enter invalid credentials.
    await loginUser(page, "nonexistent@test.com", "WrongPassword123");
    // 5. Verify "Invalid email or password" is visible.
    await expect(page.getByText("Invalid email or password")).toBeVisible({
      timeout: 10_000,
    });
  });
});
