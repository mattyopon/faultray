import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

interface RedeemBody {
  code: string;
}

export async function POST(request: Request) {
  // API-08: レート制限 — 5 attempts / minute per IP (brute-force protection)
  const limited = applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  let body: Partial<RedeemBody>;
  try {
    body = (await request.json()) as Partial<RedeemBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { code } = body;
  if (!code || typeof code !== "string" || code.trim() === "") {
    return NextResponse.json({ error: "code is required" }, { status: 400 });
  }
  const normalizedCode = code.trim().toUpperCase();

  let supabase: Awaited<ReturnType<typeof import("@/lib/supabase/server").createClient>>;
  try {
    const { createClient } = await import("@/lib/supabase/server");
    supabase = await createClient();
  } catch {
    return NextResponse.json({ error: "Supabase not configured" }, { status: 503 });
  }

  // 1. 認証チェック
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // 2. couponsテーブルからコードを検索
  const { data: coupon, error: couponError } = await supabase
    .from("coupons")
    .select("id, code, tier, days, max_uses, current_uses, revoked")
    .eq("code", normalizedCode)
    .single();

  if (couponError || !coupon) {
    return NextResponse.json({ error: "Invalid coupon code" }, { status: 404 });
  }

  // 3. バリデーション
  if (coupon.revoked) {
    return NextResponse.json({ error: "This coupon has been revoked" }, { status: 400 });
  }
  if (coupon.max_uses > 0 && coupon.current_uses >= coupon.max_uses) {
    return NextResponse.json({ error: "This coupon has reached its usage limit" }, { status: 400 });
  }

  // 4. profilesテーブルを更新
  const expiresAt = new Date(
    Date.now() + coupon.days * 24 * 60 * 60 * 1000
  ).toISOString();

  const { error: profileError } = await supabase
    .from("profiles")
    .update({ plan: coupon.tier, trial_ends_at: expiresAt })
    .eq("id", user.id);

  if (profileError) {
    return NextResponse.json({ error: "Failed to update profile" }, { status: 500 });
  }

  // 5. couponsテーブルのcurrent_usesをインクリメント
  const { error: incrementError } = await supabase
    .from("coupons")
    .update({ current_uses: coupon.current_uses + 1 })
    .eq("id", coupon.id);

  if (incrementError) {
    // ロールバックは困難なのでログに留めて続行
    console.error("Failed to increment coupon uses:", incrementError);
  }

  return NextResponse.json({
    success: true,
    tier: coupon.tier,
    expires_at: expiresAt,
  });
}
