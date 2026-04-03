import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: "https://faultray.com", lastModified: new Date() },
    { url: "https://faultray.com/ja", lastModified: new Date() },
    { url: "https://faultray.com/pricing", lastModified: new Date() },
    { url: "https://faultray.com/features", lastModified: new Date() },
    { url: "https://faultray.com/contact", lastModified: new Date() },
    { url: "https://faultray.com/privacy", lastModified: new Date() },
    { url: "https://faultray.com/terms", lastModified: new Date() },
  ];
}
