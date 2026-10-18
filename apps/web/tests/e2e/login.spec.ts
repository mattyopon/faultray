/**
 * L4: E2E — Login page
 */
import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test("renders login form with OAuth buttons", async ({ page }) => {
    await page.goto("/login");

    // Should show Welcome text
    await expect(page.getByText("Welcome to FaultRay")).toBeVisible();

    // Should have at least the Google sign-in button
    await expect(page.getByText("Continue with Google")).toBeVisible();
  });

  test("displays terms of service notice", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Terms of Service")).toBeVisible();
  });
});
