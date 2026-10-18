import type { MetadataRoute } from "next";

// ASSET-03: PWA manifest for installability
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FaultRay — Chaos Engineering",
    short_name: "FaultRay",
    description:
      "Explore your system's availability ceiling — research prototype, without touching production.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0a0e1a",
    theme_color: "#FFD700",
    orientation: "portrait-primary",
    icons: [
      {
        src: "/favicon-16.png",
        sizes: "16x16",
        type: "image/png",
      },
      {
        src: "/favicon-32.png",
        sizes: "32x32",
        type: "image/png",
      },
      {
        src: "/apple-touch-icon.png",
        sizes: "180x180",
        type: "image/png",
        purpose: "any",
      },
    ],
    categories: ["business", "productivity", "developer tools"],
    lang: "en",
  };
}
