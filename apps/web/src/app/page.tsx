import { redirect } from "next/navigation";

/**
 * Root page — the proxy handles Accept-Language detection and redirects
 * to /{locale}. This is a fallback in case the proxy is bypassed.
 */
export default function RootPage() {
  redirect("/en");
}
