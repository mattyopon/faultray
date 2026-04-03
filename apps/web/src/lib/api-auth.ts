import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { User } from "@supabase/supabase-js";

type AuthSuccess = { user: User; error: null };
type AuthFailure = { user: null; error: NextResponse };

/**
 * API Route Handler で認証を要求するヘルパー。
 *
 * 使い方:
 *   const { user, error } = await requireAuth();
 *   if (error) return error;
 *   // user は認証済み
 */
export async function requireAuth(): Promise<AuthSuccess | AuthFailure> {
  let supabase: Awaited<ReturnType<typeof createClient>>;
  try {
    supabase = await createClient();
  } catch {
    return {
      user: null,
      error: NextResponse.json({ error: "Supabase not configured" }, { status: 503 }),
    };
  }

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return {
      user: null,
      error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    };
  }

  return { user, error: null };
}
