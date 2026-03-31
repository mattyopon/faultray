/**
 * L4: E2E — Simulation page
 */
import { test, expect } from "@playwright/test";

test.describe("Simulate page", () => {
  test("loads simulation page", async ({ page }) => {
    const response = await page.goto("/simulate");
    expect(response?.status()).toBe(200);
  });

  test("page has interactive elements", async ({ page }) => {
    await page.goto("/simulate");
    // Should have at least one button for running simulation
    const buttons = page.locator("button");
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
  });
});
