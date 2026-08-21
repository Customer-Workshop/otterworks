import { test, expect } from "@playwright/test";
import { registerUser, expectDashboard } from "../fixtures/test-helpers";

/**
 * OW-UI-103 — Text file detail page never shows the file contents.
 *
 * Expected behavior under contract (qa/registry.yaml): the detail page of a
 * text file shows its contents inline, in the page itself, without a download.
 */
const FILE_NAME = "ow-ui-103.txt";
const LINE_ONE = "OW-UI-103 inline preview line one";
const LINE_TWO = "OW-UI-103 inline preview line two";

test("text file detail page shows the uploaded contents inline", async ({ page }) => {
  await registerUser(page);
  await expectDashboard(page);

  await page.goto("/files");
  await page.getByRole("button", { name: "Upload" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: FILE_NAME,
    mimeType: "text/plain",
    buffer: Buffer.from(`${LINE_ONE}\n${LINE_TWO}\n`),
  });

  await page.getByRole("link", { name: FILE_NAME }).first().click({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/files\/[0-9a-f-]+/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible({ timeout: 10_000 });

  // The contents must be rendered inline in the page document itself — not
  // reachable only through a download or an opaque cross-origin frame.
  await expect(page.getByText(LINE_ONE)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(LINE_TWO)).toBeVisible();
});
