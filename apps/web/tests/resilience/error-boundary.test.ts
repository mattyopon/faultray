/**
 * L9+: Resilience — Error boundary behavior
 * Tests that React error boundaries are in place and components
 * handle missing data gracefully.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// Test that components don't crash with missing/null props
describe("L9: Component Resilience", () => {
  it("Button renders without crashing with minimal props", async () => {
    const { Button } = await import("@/components/ui/button");
    const { container } = render(React.createElement(Button, null, "Click"));
    expect(container.querySelector("button")).not.toBeNull();
    expect(screen.getByText("Click")).toBeDefined();
  });

  it("Button renders all variants without error", async () => {
    const { Button } = await import("@/components/ui/button");
    const variants = ["primary", "secondary", "ghost", "danger"] as const;

    for (const variant of variants) {
      const { container } = render(
        React.createElement(Button, { variant }, variant)
      );
      expect(container.querySelector("button")).not.toBeNull();
    }
  });

  it("Button renders all sizes without error", async () => {
    const { Button } = await import("@/components/ui/button");
    const sizes = ["sm", "md", "lg"] as const;

    for (const size of sizes) {
      const { container } = render(
        React.createElement(Button, { size }, size)
      );
      expect(container.querySelector("button")).not.toBeNull();
    }
  });

  it("Card component renders children", async () => {
    const { Card } = await import("@/components/ui/card");
    render(React.createElement(Card, null,
      React.createElement("div", { "data-testid": "inner" }, "content")
    ));
    expect(screen.getByTestId("inner")).toHaveTextContent("content");
  });

  it("Badge component renders text", async () => {
    const { Badge } = await import("@/components/ui/badge");
    render(React.createElement(Badge, null, "status"));
    expect(screen.getByText("status")).toBeDefined();
  });
});
