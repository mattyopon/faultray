/**
 * L2: Unit Test — /whatif "Backend unreachable" error card
 *
 * Locks in the behavior introduced by faultray-app PR #18: when
 * `api.whatIf()` throws, the /whatif page MUST surface a visible
 * "Backend unreachable" error Card. Before PR #18 the catch block
 * silently fabricated `baseline: { overall_score: 85.2 }`.
 *
 * Closes Issue #19 (faultray-app).
 *
 * Strategy: mock the `@/lib/api` module so `api.whatIf` rejects,
 * render the page, click Run, assert the error Card mounts and the
 * fabricated 85.2 value does NOT appear anywhere.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

// Mock the API module BEFORE importing the page so the page's
// `import { api } from "@/lib/api"` picks up our mock.
//
// Note: the error message intentionally does NOT contain the phrase
// "Backend unreachable" — otherwise it would collide with the Card's
// heading text and make "only the heading mounts" queries ambiguous.
vi.mock("@/lib/api", () => ({
  api: {
    whatIf: vi.fn().mockRejectedValue(
      new Error("fetch failed (test stub)")
    ),
  },
}));

describe("L2: /whatif backend-unreachable error Card", () => {
  beforeEach(() => {
    // Suppress noisy error logs from the expected rejection path.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the 'Backend unreachable' error Card on api failure", async () => {
    const { default: WhatIfPage } = await import("@/app/whatif/page");
    render(React.createElement(WhatIfPage));

    // Defensive: if the component didn't render the Run button, the
    // test should fail with a specific message (not just "timeout").
    const allButtons = screen.queryAllByRole("button");
    expect(allButtons.length).toBeGreaterThan(0);

    // Find the Run Analysis button by its English label. useLocale()
    // without a provider returns defaultLocale ("en") so the button
    // text is "Run Analysis".
    const runButton = allButtons.find((b) =>
      /run\s*analysis/i.test(b.textContent ?? "")
    );
    expect(runButton).toBeDefined();
    expect(runButton).not.toBeNull();

    fireEvent.click(runButton!);

    // The async rejection + setState → re-render should complete well
    // within 3s in jsdom. If it doesn't, the test timeout exposes the
    // regression. We assert on the Card's H3 heading specifically (role=heading)
    // to avoid matching the error-message body text.
    await waitFor(
      () => {
        expect(
          screen.getByRole("heading", { name: /Backend unreachable/i })
        ).toBeDefined();
      },
      { timeout: 4000 }
    );

    // The Card body tells the user where to look. (Matched as a substring
    // of a <code> element nested in a <p>.)
    expect(
      screen.queryByText(/NEXT_PUBLIC_FAULTRAY_API_URL/i)
    ).not.toBeNull();

    // Regression guard: the fabricated 85.2 baseline score must NOT
    // appear anywhere on screen.
    expect(screen.queryAllByText(/85\.2/).length).toBe(0);
  }, 10_000);
});
