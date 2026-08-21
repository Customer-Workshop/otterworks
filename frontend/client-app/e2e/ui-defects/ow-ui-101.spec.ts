import { test, expect } from "@playwright/test";
import { registerUser, expectDashboard } from "../fixtures/test-helpers";

/**
 * OW-UI-101 — Notification data calls must succeed and be reflected in the UI.
 *
 * Expected (qa/registry.yaml): both notification calls return 200 for a
 * logged-in user, the bell badge reflects the real unread count, and the
 * notifications page distinguishes "no notifications" from "could not load
 * notifications".
 */
test.describe("OW-UI-101 — notification data calls", () => {
  test("unread-count and list return 200 and produce no console errors", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    const unreadCountRes = page.waitForResponse((res) =>
      res.url().includes("/api/v1/notifications/unread-count")
    );
    await registerUser(page);
    await expectDashboard(page);
    expect((await unreadCountRes).status()).toBe(200);

    const listRes = page.waitForResponse(
      (res) =>
        res.url().includes("/api/v1/notifications?") &&
        res.request().method() === "GET"
    );
    await page.goto("/notifications");
    expect((await listRes).status()).toBe(200);
    await page.waitForLoadState("networkidle");

    const notificationErrors = consoleErrors.filter((t) =>
      t.toLowerCase().includes("notification")
    );
    expect(
      notificationErrors,
      `notification queries must not error in the console:\n${notificationErrors.join("\n")}`
    ).toEqual([]);
  });

  test("bell badge reflects the unread count the backend reports", async ({
    page,
  }) => {
    await registerUser(page);
    await expectDashboard(page);

    // The real service returns { userId, unreadCount } — serve the same
    // contract shape with a non-zero count so the badge has something to show.
    await page.route("**/api/v1/notifications/unread-count", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ userId: "test-user", unreadCount: 3 }),
      })
    );
    await page.goto("/dashboard");

    const bell = page.getByRole("link", { name: /Notifications \(3 unread\)/ });
    await expect(bell).toBeVisible();
    await expect(bell.locator("span")).toHaveText("3");
  });

  test("notifications page distinguishes a failed load from an empty inbox", async ({
    page,
  }) => {
    await registerUser(page);
    await expectDashboard(page);

    await page.route("**/api/v1/notifications?*", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "boom" }),
      })
    );
    await page.goto("/notifications");

    await expect(
      page.getByText(/could not load notifications/i)
    ).toBeVisible();
    await expect(page.getByText("No notifications")).not.toBeVisible();
  });
});
