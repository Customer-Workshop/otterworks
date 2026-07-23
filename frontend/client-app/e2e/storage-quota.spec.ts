import { test, expect, type Page } from "@playwright/test";
import { registerUser, expectDashboard } from "./fixtures/test-helpers";

// The storage-quota banner reacts to the /api/v1/storage/quota response. We register
// a real user (real auth) and stub only the quota response so the UI behaviour is
// deterministic in headless runs; live real-data behaviour is verified in the browser
// recording attached to the PR.
async function stubQuota(
  page: Page,
  quota: {
    quota_bytes: number;
    used_bytes: number;
    tier: string;
    usage_percentage: number;
  },
) {
  await page.route("**/api/v1/storage/quota", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "00000000-0000-0000-0000-000000000000",
        over_quota: quota.usage_percentage >= 100,
        remaining_bytes: Math.max(quota.quota_bytes - quota.used_bytes, 0),
        ...quota,
      }),
    });
  });
}

test.describe("Storage quota warning banner (OTD-6)", () => {
  test("shows the banner at >= 90% and navigates to storage management (AC-01, AC-04, AC-06)", async ({
    page,
  }) => {
    await stubQuota(page, {
      quota_bytes: 5_368_709_120,
      used_bytes: 4_831_838_208,
      tier: "free",
      usage_percentage: 90,
    });
    await registerUser(page);
    await expectDashboard(page);

    const banner = page.getByRole("alert");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    await expect(banner).toContainText("running low on storage");

    await banner.getByRole("button", { name: "Manage storage" }).click();
    await expect(page).toHaveURL(/\/files/, { timeout: 10_000 });
  });

  test("dismissal persists for the rest of the session (AC-02)", async ({ page }) => {
    await stubQuota(page, {
      quota_bytes: 5_368_709_120,
      used_bytes: 5_100_000_000,
      tier: "free",
      usage_percentage: 95,
    });
    await registerUser(page);
    await expectDashboard(page);

    const banner = page.getByRole("alert");
    await expect(banner).toBeVisible();
    await banner.getByRole("button", { name: "Dismiss storage warning" }).click();
    await expect(banner).toHaveCount(0);

    // Navigate away and back — still hidden this session.
    await page.goto("/files");
    await page.goto("/dashboard");
    await expect(page.getByRole("alert")).toHaveCount(0);

    const dismissed = await page.evaluate(() =>
      window.sessionStorage.getItem("otter_storage_banner_dismissed"),
    );
    expect(dismissed).toBe("true");
  });

  test("does not show the banner below 90% (AC-03, AC-05)", async ({ page }) => {
    // Pro tier at 75% (150GB of 200GB) — below threshold even though 150GB alone
    // would exceed a free quota, proving the threshold respects the tier's quota_bytes.
    await stubQuota(page, {
      quota_bytes: 214_748_364_800,
      used_bytes: 150_000_000_000,
      tier: "pro",
      usage_percentage: 75,
    });
    await registerUser(page);
    await expectDashboard(page);

    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});
