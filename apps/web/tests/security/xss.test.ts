/**
 * L8: Security — XSS prevention
 * Verifies that components don't use dangerouslySetInnerHTML without sanitization.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import path from "path";

const SRC_DIR = path.resolve(__dirname, "../../src");

function getAllTsxFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && entry.name !== "node_modules") {
      results.push(...getAllTsxFiles(fullPath));
    } else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) {
      results.push(fullPath);
    }
  }
  return results;
}

describe("L8: XSS Prevention", () => {
  const files = getAllTsxFiles(SRC_DIR);

  it("scans at least 1 TSX file", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("no unexpected dangerouslySetInnerHTML usage in source files", () => {
    // Known legitimate uses: i18n pages that render translated HTML
    const ALLOWED_DANGEROUS_HTML = new Set([
      "app/[lang]/page.tsx",
    ]);

    const violations: string[] = [];

    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      const rel = path.relative(SRC_DIR, file);
      if (content.includes("dangerouslySetInnerHTML") && !ALLOWED_DANGEROUS_HTML.has(rel)) {
        violations.push(rel);
      }
    }

    if (violations.length > 0) {
      console.warn("Unexpected dangerouslySetInnerHTML usage:", violations);
    }
    expect(violations).toHaveLength(0);
  });

  it("no eval() usage in source files", () => {
    const violations: string[] = [];

    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      // Match eval( but not .evaluate or similar
      if (/\beval\s*\(/.test(content)) {
        violations.push(path.relative(SRC_DIR, file));
      }
    }

    expect(violations).toHaveLength(0);
  });

  it("no direct document.write usage (window.document.write for popups is allowed)", () => {
    const violations: string[] = [];

    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      // Match bare document.write but not win.document.write / popup.document.write
      // which are legitimate patterns for opening print/export windows
      const lines = content.split("\n");
      for (const line of lines) {
        if (/(?<!\w\.)document\.write\s*\(/.test(line)) {
          violations.push(path.relative(SRC_DIR, file));
          break;
        }
      }
    }

    expect(violations).toHaveLength(0);
  });
});
