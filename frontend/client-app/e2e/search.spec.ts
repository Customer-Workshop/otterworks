import { test, expect } from "@playwright/test";

test.describe("Search Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/search");
    await page.waitForLoadState("networkidle");
  });

  test("shows Search heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Search", exact: true })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("displays search input with placeholder", async ({ page }) => {
    await expect(
      page.getByPlaceholder("Search files, documents, and folders...")
    ).toBeVisible({ timeout: 10_000 });
  });

  test("shows empty state before searching", async ({ page }) => {
    await expect(page.getByText("Search OtterWorks")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText("Find files, documents, and folders across your workspace")
    ).toBeVisible();
  });

  test("has filter toggle button", async ({ page }) => {
    // The filter button is inside the search form
    const filterButton = page.locator("form button[type='button']").first();
    await expect(filterButton).toBeVisible({ timeout: 10_000 });
  });

  test("can type a query in the search input", async ({ page }) => {
    const searchInput = page.getByPlaceholder(
      "Search files, documents, and folders..."
    );
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill("test query");
    await expect(searchInput).toHaveValue("test query");
  });

  test("shows no results for gibberish query", async ({ page }) => {
    const searchInput = page.getByPlaceholder(
      "Search files, documents, and folders..."
    );
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill("xyznonexistent9999");
    await searchInput.press("Enter");

    // Wait for either results or no-results state
    const noResults = page.getByText("No results found");
    const spinner = page.locator("[class*='animate-spin']");
    await expect(noResults.or(spinner)).toBeVisible({ timeout: 15_000 });
  });

  test("displays breadcrumb navigation", async ({ page }) => {
    // Breadcrumb nav (aria-label="Breadcrumb") should contain "Search"
    const breadcrumb = page.getByLabel("Breadcrumb").getByText("Search");
    await expect(breadcrumb).toBeVisible({ timeout: 10_000 });
  });
});
