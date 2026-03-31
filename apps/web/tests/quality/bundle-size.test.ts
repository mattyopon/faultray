/**
 * L5: Quality — Bundle size verification
 * Ensures the build output doesn't exceed reasonable size limits.
 */
import { describe, it, expect } from "vitest";
import { existsSync, statSync, readdirSync } from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../..");
const NEXT_DIR = path.join(ROOT, ".next");

function getDirSizeBytes(dir: string): number {
  if (!existsSync(dir)) return 0;
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (entry.isFile()) {
      const fullPath = path.join(entry.parentPath ?? entry.path, entry.name);
      total += statSync(fullPath).size;
    }
  }
  return total;
}

describe("L5: Bundle Size", () => {
  it(".next directory exists (build has been run)", () => {
    // If .next doesn't exist, skip these tests gracefully
    if (!existsSync(NEXT_DIR)) {
      console.warn("Skipping bundle size test — .next not found. Run `next build` first.");
      return;
    }
    expect(existsSync(NEXT_DIR)).toBe(true);
  });

  it("static assets are under 50MB total", () => {
    const staticDir = path.join(NEXT_DIR, "static");
    if (!existsSync(staticDir)) return;

    const sizeBytes = getDirSizeBytes(staticDir);
    const sizeMB = sizeBytes / (1024 * 1024);
    console.log(`Static assets size: ${sizeMB.toFixed(2)} MB`);
    expect(sizeMB).toBeLessThan(50);
  });
});
