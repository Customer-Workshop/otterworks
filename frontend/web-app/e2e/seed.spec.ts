import { test, expect } from "@playwright/test";
import { clearAuth } from "./fixtures/test-helpers";

test("bootstraps a clean unauthenticated page", async ({ page }) => {
  await page.goto("/");
  await clearAuth(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "OtterWorks" })).toBeVisible();
});
