/**
 * L4: E2E — Navigation: every page returns 200
 */
import { test, expect } from "@playwright/test";

const PAGES = [
  "/",
  "/login",
  "/dashboard",
  "/simulate",
  "/topology",
  "/heatmap",
  "/score-detail",
  "/whatif",
  "/fmea",
  "/incidents",
  "/compliance",
  "/security",
  "/cost",
  "/reports",
  "/benchmark",
  "/advisor",
  "/settings",
  "/help",
  "/demo",
  "/evidence",
  "/remediation",
  "/suggestions",
  "/results",
  "/apm",
  "/projects",
  "/pricing",
];

for (const page of PAGES) {
  test(`GET ${page} returns 200`, async ({ page: p }) => {
    const response = await p.goto(page);
    expect(response?.status()).toBe(200);
  });
}
