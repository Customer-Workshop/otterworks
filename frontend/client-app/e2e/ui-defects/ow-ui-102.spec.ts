import { test, expect } from "@playwright/test";
import { registerUser, expectDashboard } from "../fixtures/test-helpers";

/**
 * OW-UI-102 — Settings page calls a route that does not exist.
 *
 * Expected behavior under contract (qa/registry.yaml): the settings surface is
 * backed by real endpoints — edits made on /settings persist to the backend
 * and the user can see that they did. A form that silently discards input is
 * the defect.
 */
test("OW-UI-102: saving the profile on /settings persists and confirms", async ({
  page,
}) => {
  await registerUser(page, { name: "Settings Repro" });
  await expectDashboard(page);

  const failedSaves: string[] = [];
  page.on("response", (res) => {
    if (res.status() >= 400 && res.url().includes("/api/v1/auth/profile")) {
      failedSaves.push(`${res.status()} ${res.request().method()} ${res.url()}`);
    }
  });

  await page.goto("/settings");
  const nameInput = page.getByLabel("Full name");
  await expect(nameInput).toBeVisible();

  const newName = `Renamed ${Date.now()}`;
  await nameInput.fill(newName);

  const saveResponse = page.waitForResponse(
    (res) =>
      res.url().includes("/api/v1/auth/profile") &&
      res.request().method() !== "GET"
  );
  await page.getByRole("button", { name: "Save changes" }).click();
  const res = await saveResponse;

  expect(res.status(), `profile save answered ${res.status()}`).toBeLessThan(400);
  expect(failedSaves, `failed profile saves: ${failedSaves.join(", ")}`).toEqual([]);

  // The user must be able to see that the save happened.
  await expect(page.getByText("Profile updated successfully.")).toBeVisible();

  // And the edit must actually have persisted to the backend.
  await page.reload();
  await expect(page.getByLabel("Full name")).toHaveValue(newName);
});
