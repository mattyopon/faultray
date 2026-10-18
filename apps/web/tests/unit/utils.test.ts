/**
 * L2: Unit Tests — src/lib/utils.ts
 */
import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn() utility", () => {
  it("merges simple class names", () => {
    expect(cn("px-2", "py-1")).toBe("px-2 py-1");
  });

  it("handles conditional classes via clsx", () => {
    const result = cn("base", false && "hidden", "visible");
    expect(result).toBe("base visible");
  });

  it("resolves tailwind conflicts (last wins)", () => {
    // tailwind-merge should resolve px-2 vs px-4 → px-4
    const result = cn("px-2 py-1", "px-4");
    expect(result).toBe("py-1 px-4");
  });

  it("handles empty / undefined / null inputs", () => {
    expect(cn("", undefined, null, "foo")).toBe("foo");
  });

  it("handles no arguments", () => {
    expect(cn()).toBe("");
  });

  it("merges object syntax from clsx", () => {
    const result = cn({ "text-red-500": true, "text-blue-500": false });
    expect(result).toBe("text-red-500");
  });

  it("merges array syntax from clsx", () => {
    const result = cn(["a", "b"], "c");
    expect(result).toBe("a b c");
  });
});
