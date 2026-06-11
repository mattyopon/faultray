import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Missing Supabase environment variables. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY."
    );
  }

  return createBrowserClient(url, key);
}

/**
 * Current Supabase access token for the logged-in user, or undefined.
 *
 * Used to authenticate calls to the Python API (e.g. /api/projects), which
 * runs in a separate runtime and cannot read the Next.js session cookie.
 * Returns undefined on the server or when no session exists.
 */
export async function getAccessToken(): Promise<string | undefined> {
  if (typeof window === "undefined") return undefined;
  try {
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  } catch {
    return undefined;
  }
}
