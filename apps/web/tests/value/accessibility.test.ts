/**
 * L6: Value — Basic accessibility checks
 * Verifies components render with proper semantic HTML.
 * For full axe-core, use the E2E accessibility tests.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";

describe("L6: Accessibility — Semantic HTML", () => {
  it("Button renders as <button> element", async () => {
    const { Button } = await import("@/components/ui/button");
    const { container } = render(React.createElement(Button, null, "Click me"));
    const btn = container.querySelector("button");
    expect(btn).not.toBeNull();
    expect(btn?.tagName).toBe("BUTTON");
  });

  it("Button forwards disabled attribute", async () => {
    const { Button } = await import("@/components/ui/button");
    const { container } = render(
      React.createElement(Button, { disabled: true }, "Disabled")
    );
    const btn = container.querySelector("button");
    expect(btn?.disabled).toBe(true);
  });

  it("CardTitle renders as heading element", async () => {
    const { CardTitle } = await import("@/components/ui/card");
    const { container } = render(
      React.createElement(CardTitle, null, "My Title")
    );
    const heading = container.querySelector("h3");
    expect(heading).not.toBeNull();
    expect(heading?.textContent).toBe("My Title");
  });

  it("Badge uses <span> (inline semantics)", async () => {
    const { Badge } = await import("@/components/ui/badge");
    const { container } = render(
      React.createElement(Badge, null, "Active")
    );
    const span = container.querySelector("span");
    expect(span).not.toBeNull();
  });

  it("All pages have a root layout with lang attribute", async () => {
    // Verify the root layout sets html lang attribute
    const { readFileSync } = await import("fs");
    const { resolve } = await import("path");
    const layoutContent = readFileSync(
      resolve(__dirname, "../../src/app/layout.tsx"),
      "utf-8"
    );
    expect(layoutContent).toContain("<html");
    expect(layoutContent).toMatch(/lang[=]/);
  });
});
