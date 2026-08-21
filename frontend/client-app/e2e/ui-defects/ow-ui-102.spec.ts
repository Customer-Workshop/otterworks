import { test, expect } from "@playwright/test";
import { registerUser, expectDashboard } from "../fixtures/test-helpers";

/**
 * OW-UI-102 — the settings surface must not silently discard input.
 *
 * Saving a profile change must call an endpoint that exists, report success
 * visibly, and persist across a reload. Controls without a backend (email)
 * must be disabled with a visible explanation rather than pretend to work.
 */
test.describe("OW-UI-102 settings surface persists input", () => {
  test("profile save succeeds visibly and persists", async ({ page }) => {
    const failures: string[] = [];
    page.on("response", (res) => {
      if (res.status() >= 400 && res.url().includes("/api/v1/")) {
        failures.push(`${res.status()} ${res.request().method()} ${res.url()}`);
      }
    });

    await registerUser(page);
    await expectDashboard(page);

    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const newName = `Renamed ${Date.now()}`;
    await page.getByLabel("Full name").fill(newName);
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByText("Profile updated successfully.")).toBeVisible();

    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.getByLabel("Full name")).toHaveValue(newName);

    await expect(
      page.getByLabel("Email"),
      "email has no update backend, so the control must be disabled, not silently ignored"
    ).toBeDisabled();

    expect(
      failures,
      "no settings-surface call may answer 4xx/5xx"
    ).toEqual([]);
  });
});
