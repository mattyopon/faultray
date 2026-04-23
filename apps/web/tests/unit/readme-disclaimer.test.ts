/**
 * L2 Regression: README + NOTICE structure (#40, #44).
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "../..");

describe("L2: README disclaimer + NOTICE file", () => {
  it("README has prominent Research Prototype disclaimer block (#44)", () => {
    const readme = readFileSync(resolve(ROOT, "README.md"), "utf-8");
    // Must contain a blockquote (> ...) AND the phrase "Research Prototype"
    // with warning / ⚠️ emoji to catch the eye.
    expect(readme).toMatch(/^>\s+.*Research Prototype/mi);
    expect(readme).toMatch(/not a certified/i);
  });

  it("NOTICE file exists with third-party attribution (#40)", () => {
    const noticePath = resolve(ROOT, "NOTICE");
    expect(existsSync(noticePath)).toBe(true);

    const notice = readFileSync(noticePath, "utf-8");
    expect(notice).toMatch(/Copyright .* Yutaro Maeda/);
    expect(notice).toMatch(/Apache License/);
    expect(notice).toMatch(/Third-Party Notices/);

    // Sanity: at least a handful of known deps appear in the table.
    for (const lib of ["Next.js", "React", "Stripe", "Tailwind"]) {
      expect(notice).toContain(lib);
    }
  });
});
