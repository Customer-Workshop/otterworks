import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { registerUser, expectDashboard } from "../fixtures/test-helpers";

/**
 * OW-UI-104 — Download action gives no visible feedback.
 *
 * Expected: clicking Download on the file detail page keeps the user in the
 * app, actually starts a download, and shows a visible started state followed
 * by a finished (or failed) state.
 */
test("OW-UI-104: download shows started and finished (or failed) state", async ({ page }) => {
  await registerUser(page);
  await expectDashboard(page);

  const tmp = path.join(os.tmpdir(), `ow-ui-104-${Date.now()}.txt`);
  fs.writeFileSync(tmp, "ow-ui-104 download feedback fixture\n");
  const fileName = path.basename(tmp);

  await page.goto("/files");
  await page.getByRole("button", { name: "Upload" }).click();
  await page.locator('input[type="file"]').first().setInputFiles(tmp);
  const fileLink = page.getByRole("link", { name: new RegExp(fileName) }).first();
  await expect(fileLink).toBeVisible({ timeout: 15_000 });

  await fileLink.click();
  await expect(page).toHaveURL(/\/files\/[0-9a-f-]+/, { timeout: 10_000 });

  const downloadPromise = page.waitForEvent("download", { timeout: 10_000 });
  await page.getByRole("button", { name: /Download/ }).first().click();

  // A visible started state the user can see.
  await expect(
    page.getByText(/Downloading/i).first(),
    "clicking Download must show a visible started state"
  ).toBeVisible({ timeout: 5_000 });

  // The click must not navigate the SPA away to the raw storage URL.
  await expect(
    page,
    "clicking Download must keep the user on the file detail page"
  ).toHaveURL(/\/files\/[0-9a-f-]+/);

  // A real download starts.
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(fileName);

  // A visible finished (or failed) state the user can see.
  await expect(
    page.getByText(/Downloaded|Download failed/i).first(),
    "the download must report a finished (or failed) state"
  ).toBeVisible({ timeout: 10_000 });
});
