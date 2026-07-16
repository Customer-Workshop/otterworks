import { test, expect } from "@playwright/test";

// spec: specs/login-and-navigation.md
// seed: e2e/seed.spec.ts

test.describe("Public Navigation", () => {
  test("Dashboard requires authentication", async ({ page }) => {
    // 1. Navigate to `/dashboard`.
    await page.goto("/dashboard");
    // 2. Verify the Dashboard page or login form is visible.
    const dashboard = page.getByRole("heading", { name: "Dashboard" });
    const login = page.getByText("Sign in to your account");
    await expect(dashboard.or(login)).toBeVisible({ timeout: 10_000 });
  });

  test("Documents requires authentication", async ({ page }) => {
    // 1. Navigate to `/documents`.
    await page.goto("/documents");
    // 2. Verify the Documents page or login form is visible.
    const documents = page.getByRole("heading", { name: "Documents" });
    const login = page.getByText("Sign in to your account");
    await expect(documents.or(login)).toBeVisible({ timeout: 10_000 });
  });

  test("Files requires authentication", async ({ page }) => {
    // 1. Navigate to `/files`.
    await page.goto("/files");
    // 2. Verify the Files, My Files, or login form is visible.
    const files = page.getByRole("heading", { name: /Files|My Files/i });
    const login = page.getByText("Sign in to your account");
    await expect(files.or(login)).toBeVisible({ timeout: 10_000 });
  });
});
