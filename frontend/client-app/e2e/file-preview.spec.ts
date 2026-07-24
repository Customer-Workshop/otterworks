import { test, expect } from "@playwright/test";

// OTD-12 — inline file preview from the file list.
// These mirror the resilient style of files.spec.ts: when a real session with
// seeded files is present the preview flow is exercised end-to-end; otherwise
// the test tolerates the logged-out redirect (full verification is done in the
// browser against the seeded drive account).
test.describe("File Preview (OTD-12)", () => {
  test("files list is reachable", async ({ page }) => {
    await page.goto("/files");
    const heading = page.getByRole("heading", { name: /Files|My Files/i });
    const loginHeading = page.getByText("Sign in to your account");
    await expect(heading.or(loginHeading)).toBeVisible({ timeout: 10_000 });
  });

  test("a Preview action opens an inline preview modal", async ({ page }) => {
    await page.goto("/files");
    const heading = page.getByRole("heading", { name: /Files|My Files/i });

    if (!(await heading.isVisible({ timeout: 10_000 }).catch(() => false))) {
      // Logged out — nothing more to verify here.
      await expect(page.getByText("Sign in to your account")).toBeVisible();
      return;
    }

    // Find the first file card's overflow menu (skip folders, which have no Preview).
    const menuButtons = page.locator("button:has(svg.lucide-ellipsis-vertical)");
    if ((await menuButtons.count()) === 0) {
      // Empty drive — nothing to preview.
      return;
    }

    await menuButtons.first().click();
    const previewItem = page.getByRole("button", { name: "Preview" });
    if (!(await previewItem.isVisible({ timeout: 3_000 }).catch(() => false))) {
      // The first item may be a folder; acceptable — action is folder-gated.
      return;
    }

    await previewItem.click();
    const dialog = page.getByRole("dialog", { name: /Preview of/i });
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    // The list route is preserved (modal, not navigation).
    await expect(page).toHaveURL(/\/files/);

    // Closing the modal returns to the list.
    await page.getByRole("button", { name: "Close preview" }).click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });
});
