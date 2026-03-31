/**
 * L4: E2E — Dashboard page
 */
import { test, expect } from "@playwright/test";

test.describe("Dashboard page", () => {
  test("loads without crashing", async ({ page }) => {
    const response = await page.goto("/dashboard");
    expect(response?.status()).toBe(200);
  });

  test("contains navigation elements", async ({ page }) => {
    await page.goto("/dashboard");
    // The navbar should be present
    await expect(page.locator("nav").first()).toBeVisible();
  });
});
