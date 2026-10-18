#!/usr/bin/env node
// Generates FaultRay extension icons using @napi-rs/canvas (if available)
// or falls back to writing a minimal PNG via raw bytes.
//
// Colors: #FFD700 (gold) on #0a0e1a (dark navy) — matching FaultRay brand.
//
// Run: node scripts/generate-icons.mjs

import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS_DIR = join(__dirname, "../src/assets");
mkdirSync(ASSETS_DIR, { recursive: true });

// Minimal valid 1x1 transparent PNG (used as placeholder if canvas is unavailable)
// Real icons are the inline SVG-based ones below.
// We encode a simple colored PNG using raw deflate.

// Actually, we'll write the SVG and let esbuild handle conversion,
// but for the manifest we need PNG. We'll create them via a simple
// Node.js approach using the "sharp" package if available, or write
// SVG files that the user can convert.

const SIZES = [16, 48, 128];

const SVG_TEMPLATE = (size) => `<svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" rx="${size < 48 ? 20 : 16}" fill="#0a0e1a"/>
  <g opacity="0.2">
    <line x1="25" y1="0" x2="25" y2="100" stroke="#e2e8f0" stroke-width="2"/>
    <line x1="50" y1="0" x2="50" y2="100" stroke="#e2e8f0" stroke-width="2"/>
    <line x1="75" y1="0" x2="75" y2="100" stroke="#e2e8f0" stroke-width="2"/>
    <line x1="0" y1="25" x2="100" y2="25" stroke="#e2e8f0" stroke-width="2"/>
    <line x1="0" y1="50" x2="100" y2="50" stroke="#e2e8f0" stroke-width="2"/>
    <line x1="0" y1="75" x2="100" y2="75" stroke="#e2e8f0" stroke-width="2"/>
  </g>
  <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" stroke-width="12" opacity="0.15" stroke-linecap="round"/>
  <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" stroke-width="4" stroke-linecap="round"/>
  <line x1="32" y1="32" x2="85" y2="15" stroke="#FFD700" stroke-width="2" opacity="0.4" stroke-linecap="round"/>
</svg>`;

// Write SVG files (can be used directly in Chromium-based extensions)
for (const size of SIZES) {
  const svgPath = join(ASSETS_DIR, `icon${size}.svg`);
  writeFileSync(svgPath, SVG_TEMPLATE(size), "utf8");
  console.log(`✓ Written: ${svgPath}`);
}

// Try to convert to PNG using sharp if available
let sharp;
try {
  const mod = await import("sharp");
  sharp = mod.default;
} catch {
  console.log("\nNote: 'sharp' is not installed. SVG icons written.");
  console.log("To generate PNG icons, run: npm install sharp && node scripts/generate-icons.mjs");
  console.log("Or convert SVGs manually. Chromium accepts SVG in the manifest for development.\n");
  process.exit(0);
}

for (const size of SIZES) {
  const svgPath = join(ASSETS_DIR, `icon${size}.svg`);
  const pngPath = join(ASSETS_DIR, `icon${size}.png`);
  await sharp(svgPath).resize(size, size).png().toFile(pngPath);
  console.log(`✓ PNG: ${pngPath}`);
}

console.log("\nAll icons generated successfully.");
