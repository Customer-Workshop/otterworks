import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { OtterWorld } from "../support/world";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

const TIER_QUOTA_BYTES: Record<string, number> = {
  free: 5_368_709_120, // 5 GB
  basic: 53_687_091_200, // 50 GB
  pro: 214_748_364_800, // 200 GB
  enterprise: 1_099_511_627_776, // 1 TB
};

// Stub only the quota response so the banner behaviour is deterministic; auth is real.
Given(
  "my storage usage is {int} percent of a {string} quota",
  async function (this: OtterWorld, percent: number, tier: string) {
    const quotaBytes = TIER_QUOTA_BYTES[tier] ?? TIER_QUOTA_BYTES.free;
    const usedBytes = Math.round((quotaBytes * percent) / 100);
    await this.page.route("**/api/v1/storage/quota", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "00000000-0000-0000-0000-000000000000",
          quota_bytes: quotaBytes,
          used_bytes: usedBytes,
          tier,
          usage_percentage: percent,
          over_quota: percent >= 100,
          remaining_bytes: Math.max(quotaBytes - usedBytes, 0),
        }),
      });
    });
  },
);

Given("I register and open the app", async function (this: OtterWorld) {
  const email = `test-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@otterworks.test`;
  await this.page.goto(`${BASE_URL}/register`);
  await this.page.getByLabel("Full name").fill("Test User");
  await this.page.getByLabel("Email").fill(email);
  await this.page.getByLabel("Password", { exact: true }).fill("Passw0rd!23");
  await this.page.getByLabel("Confirm password").fill("Passw0rd!23");
  await this.page.getByRole("button", { name: "Create account" }).click();
  await this.page.waitForURL(/\/dashboard/, { timeout: 15_000 });
});

Then("I should see the storage warning banner", async function (this: OtterWorld) {
  await expect(this.page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
});

Then(
  "the storage warning banner should not be visible",
  async function (this: OtterWorld) {
    await expect(this.page.getByRole("alert")).toHaveCount(0, { timeout: 10_000 });
  },
);

When("I dismiss the storage warning banner", async function (this: OtterWorld) {
  await this.page
    .getByRole("alert")
    .getByRole("button", { name: "Dismiss storage warning" })
    .click();
});

When(
  "I click the banner {string} action",
  async function (this: OtterWorld, label: string) {
    await this.page.getByRole("alert").getByRole("button", { name: label }).click();
  },
);
