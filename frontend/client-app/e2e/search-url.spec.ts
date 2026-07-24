import { test, expect } from "@playwright/test";

const SEARCH_INPUT = "Search files, documents, and folders...";

test.describe("Shareable search URLs", () => {
  test("submitting a query updates the URL to /search?q=<term>", async ({
    page,
  }) => {
    await page.goto("/search");
    await page.waitForLoadState("networkidle");

    const searchInput = page.getByPlaceholder(SEARCH_INPUT);
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill("otter");
    await searchInput.press("Enter");

    await expect(page).toHaveURL(/[?&]q=otter(&|$)/, { timeout: 10_000 });
  });

  test("loading /search?q=<term> directly runs the search and renders a result state", async ({
    page,
  }) => {
    await page.goto("/search?q=xyznonexistent9999");
    await page.waitForLoadState("networkidle");

    // The input should be pre-filled from the URL.
    await expect(page.getByPlaceholder(SEARCH_INPUT)).toHaveValue(
      "xyznonexistent9999",
      { timeout: 10_000 }
    );

    // Because a query was provided, the search runs and we land on the
    // no-results state (or the loading spinner) — NOT the pristine
    // "Search OtterWorks" empty state.
    const noResults = page.getByText("No results found");
    const spinner = page.locator("[class*='animate-spin']");
    await expect(noResults.or(spinner).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Search OtterWorks")).toHaveCount(0);
  });

  test("clearing the query with the X button resets the query param", async ({
    page,
  }) => {
    await page.goto("/search?q=otter");
    await page.waitForLoadState("networkidle");

    const searchInput = page.getByPlaceholder(SEARCH_INPUT);
    await expect(searchInput).toHaveValue("otter", { timeout: 10_000 });

    // The clear (X) button is the last type=button control inside the form.
    const clearButton = page.locator("form button[type='button']").last();
    await clearButton.click();

    await expect(searchInput).toHaveValue("");
    await expect(page).not.toHaveURL(/[?&]q=otter(&|$)/, { timeout: 10_000 });
  });
});
