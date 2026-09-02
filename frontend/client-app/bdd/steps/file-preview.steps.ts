import { Given, Then, When } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { OtterWorld } from "../support/world";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

Given("I am logged in as the seeded drive user", async function (this: OtterWorld) {
  const email = process.env.DRIVE_EMAIL;
  const password = process.env.DRIVE_PASSWORD;
  if (!email || !password) throw new Error("DRIVE_EMAIL and DRIVE_PASSWORD are required");

  await this.page.goto(`${BASE_URL}/login`);
  await this.page.getByLabel("Email").fill(email);
  await this.page.getByLabel("Password", { exact: true }).fill(password);
  await this.page.getByRole("button", { name: "Sign in" }).click();
  await expect(this.page).toHaveURL(/\/dashboard|\/files/, { timeout: 15_000 });
});

Given("I am logged out", async function (this: OtterWorld) {
  await this.page.context().clearCookies();
  await this.page.goto(`${BASE_URL}/login`);
  await this.page.evaluate(() => localStorage.clear());
});

When(
  "I open a seeded {string} file from the file list",
  { timeout: 20_000 },
  async function (this: OtterWorld, extension: string) {
    const fileId = await this.page.evaluate(async (fileExtension) => {
      const token = localStorage.getItem("otter_access_token");
      if (!token) return null;
      const response = await fetch(
        `/api/v1/files?page=1&page_size=100`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) return null;
      const payload = await response.json();
      const file = (payload.files ?? []).find((candidate: { name?: string }) =>
        candidate.name?.toLowerCase().endsWith(`.${fileExtension}`),
      );
      return file?.id ?? null;
    }, extension);
    if (!fileId) throw new Error(`No seeded .${extension} file is available`);
    await this.page.goto(`${BASE_URL}/files/${fileId}`);
    await expect(this.page.getByRole("heading", { name: "Preview" })).toBeVisible();
  },
);

Then("I should see an inline file preview", async function (this: OtterWorld) {
  await expect(this.page.locator("img, video, audio, iframe, table").first()).toBeVisible({
    timeout: 20_000,
  });
});

Then(
  "I should see a spreadsheet table preview",
  { timeout: 30_000 },
  async function (this: OtterWorld) {
    await expect(this.page.locator("table")).toBeVisible({ timeout: 20_000 });
  },
);

Then(
  "I should see a document preview",
  { timeout: 30_000 },
  async function (this: OtterWorld) {
    await expect(this.page.locator("[class*='docx'], [data-docx-preview]").first()).toBeVisible({
      timeout: 20_000,
    });
  },
);

Then("I should see the generic file fallback", async function (this: OtterWorld) {
  await expect(this.page.getByRole("button", { name: "Download" })).toBeVisible();
  await expect(this.page.getByText(/application\/|presentation|preview/i).first()).toBeVisible();
});
