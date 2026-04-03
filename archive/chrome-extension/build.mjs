#!/usr/bin/env node
// FaultRay Chrome Extension — esbuild build script
// Produces Manifest V3-compatible bundles in ./dist/

import * as esbuild from "esbuild";
import { copyFileSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, "dist");

// Create output directories
mkdirSync(OUT_DIR, { recursive: true });

const sharedConfig = {
  bundle: true,
  platform: "browser",
  target: ["chrome120"],
  format: "esm",
  sourcemap: true,
  minify: process.env["NODE_ENV"] === "production",
  external: [], // No externals — bundle everything
};

// ── 1. Popup (React app) ──────────────────────────────────────────────────────
await esbuild.build({
  ...sharedConfig,
  entryPoints: ["src/popup/index.tsx"],
  outfile: join(OUT_DIR, "popup.js"),
  define: {
    "process.env.NODE_ENV": '"development"',
  },
});
console.log("✓ popup.js");

// ── 2. Content script ────────────────────────────────────────────────────────
await esbuild.build({
  ...sharedConfig,
  entryPoints: ["src/content/aws-guide.ts"],
  outfile: join(OUT_DIR, "aws-guide.js"),
  // Content scripts use chrome.* globals — no module wrapper
  format: "iife",
});
console.log("✓ aws-guide.js");

// ── 3. Service worker ────────────────────────────────────────────────────────
await esbuild.build({
  ...sharedConfig,
  entryPoints: ["src/background/service-worker.ts"],
  outfile: join(OUT_DIR, "service-worker.js"),
});
console.log("✓ service-worker.js");

// ── 4. Copy static assets ────────────────────────────────────────────────────

// HTML
copyFileSync("src/popup/popup.html", join(OUT_DIR, "popup.html"));
console.log("✓ popup.html");

// CSS
copyFileSync("src/popup/popup.css", join(OUT_DIR, "popup.css"));
console.log("✓ popup.css");

copyFileSync("src/content/content.css", join(OUT_DIR, "content.css"));
console.log("✓ content.css");

// Manifest
copyFileSync("manifest.json", join(OUT_DIR, "manifest.json"));
console.log("✓ manifest.json");

// Icons — copy SVG/PNG from assets if they exist
const SIZES = [16, 48, 128];
const ASSETS_DIR = join(__dirname, "src/assets");
for (const size of SIZES) {
  const pngSrc = join(ASSETS_DIR, `icon${size}.png`);
  const svgSrc = join(ASSETS_DIR, `icon${size}.svg`);
  if (existsSync(pngSrc)) {
    copyFileSync(pngSrc, join(OUT_DIR, `icon${size}.png`));
    console.log(`✓ icon${size}.png`);
  } else if (existsSync(svgSrc)) {
    // Chromium accepts SVGs in development
    copyFileSync(svgSrc, join(OUT_DIR, `icon${size}.png`));
    console.log(`✓ icon${size}.png (SVG copy)`);
  } else {
    // Write a minimal placeholder so the extension loads without errors
    // This is a valid 1x1 gold pixel PNG encoded as base64
    const PLACEHOLDER_PNG = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI6QAAAABJRU5ErkJggg==",
      "base64"
    );
    writeFileSync(join(OUT_DIR, `icon${size}.png`), PLACEHOLDER_PNG);
    console.log(`✓ icon${size}.png (placeholder)`);
  }
}

console.log("\nBuild complete → ./dist/");
console.log("Load in Chrome: chrome://extensions → Developer mode → Load unpacked → select ./dist/");
