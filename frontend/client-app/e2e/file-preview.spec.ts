import { test, expect, type Page } from "@playwright/test";

const seededCredentials = {
  email: process.env.DRIVE_EMAIL,
  password: process.env.DRIVE_PASSWORD,
};

type SeededFile = { id: string; name: string; mimeType: string };

async function loginAndFindFile(page: Page, extension: string): Promise<SeededFile | null> {
  if (!seededCredentials.email || !seededCredentials.password) {
    test.skip(true, "Seeded-drive credentials are not configured");
  }

  await page.goto("/login");
  await page.getByLabel("Email").fill(seededCredentials.email!);
  await page.getByLabel("Password", { exact: true }).fill(seededCredentials.password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard|\/files/, { timeout: 15_000 });

  return page.evaluate(async (fileExtension): Promise<SeededFile | null> => {
    const token = localStorage.getItem("otter_access_token");
    if (!token) return null;
    const headers = { Authorization: `Bearer ${token}` };
    const request = async (path: string) => {
      const response = await fetch(`/api/v1${path}`, { headers });
      if (!response.ok) throw new Error(`HTTP ${response.status} for ${path}`);
      return response.json();
    };
    const files: SeededFile[] = [];
    let pageNumber = 1;
    while (true) {
      const fileQuery = new URLSearchParams({
        page: String(pageNumber),
        page_size: "100",
      });
      const fileResponse = await request(`/files?${fileQuery}`);
      const batch = fileResponse.files ?? [];
      files.push(...batch.map((file: Record<string, unknown>) => ({
        id: file.id as string,
        name: file.name as string,
        mimeType: (file.mime_type ?? file.mimeType ?? "") as string,
      })));
      const match = files.find((file) =>
        file.name.toLowerCase().endsWith(`.${fileExtension}`),
      );
      if (match) return match;
      if (!batch.length || files.length >= (fileResponse.total ?? 0)) break;
      pageNumber++;
    }
    return null;
  }, extension);
}

test.describe("File previews", () => {
  for (const preview of [
    { extension: "xlsx", surface: "table" },
    { extension: "csv", surface: "table" },
    { extension: "docx", surface: "[data-docx-preview]" },
    { extension: "pptx", surface: "generic" },
    { extension: "pdf", surface: "iframe" },
    { extension: "png", surface: "img" },
    { extension: "mp4", surface: "video" },
    { extension: "wav", surface: "audio" },
  ]) {
    test(`AC-01/BDD: real seeded ${preview.extension} file renders its preview surface`, async ({ page }) => {
      const file = await loginAndFindFile(page, preview.extension);
      test.skip(!file, `No seeded .${preview.extension} file is available`);
      await page.goto(`/files/${file!.id}`);
      await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible();
      if (preview.surface === "generic") {
        await expect(page.getByRole("link", { name: "Download" })).toBeVisible();
        await expect(page.getByRole("heading", { name: file!.name })).toBeVisible();
      } else if (preview.surface === "img") {
        await expect(page.getByRole("img", { name: file!.name })).toBeVisible({ timeout: 20_000 });
      } else if (preview.surface === "[data-docx-preview]") {
        await expect(page.locator(preview.surface)).toContainText(/\S+/, { timeout: 20_000 });
      } else {
        await expect(page.locator(preview.surface)).toBeVisible({ timeout: 20_000 });
      }
    });
  }

  test("AC-11/BDD-11: an unknown or archive file uses the generic fallback when seeded", async ({ page }) => {
    const file = await loginAndFindFile(page, "zip");
    test.skip(!file, "No seeded archive file is available");
    await page.goto(`/files/${file!.id}`);
    await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Download" })).toBeVisible();
  });

  test("AC-18/BDD-18: unauthenticated file detail redirects to login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/files/00000000-0000-0000-0000-000000000000");
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });
});
