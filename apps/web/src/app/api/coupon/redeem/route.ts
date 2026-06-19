import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";

export const dynamic = "force-dynamic";

interface RedeemBody {
  code: string;
}

export async function POST(request: Request) {
  // API-08: レート制限 — 5 attempts / minute per IP (brute-force protection)
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2). Was using bare auth.getUser() so CSRF check was
  // skipped — a malicious cross-origin POST could redeem a victim's coupon.
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

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

  // 1. couponsテーブルからコードを検索 (RLS-protected user client)
  const { data: coupon, error: couponError } = await supabase
    .from("coupons")
    .select("id, code, tier, days, max_uses, current_uses, revoked")
    .eq("code", normalizedCode)
    .single();

  if (couponError || !coupon) {
    return NextResponse.json({ error: "Invalid coupon code" }, { status: 404 });
  }

  // 2. バリデーション
  if (coupon.revoked) {
    return NextResponse.json({ error: "This coupon has been revoked" }, { status: 400 });
  }
  if (coupon.max_uses > 0 && coupon.current_uses >= coupon.max_uses) {
    return NextResponse.json({ error: "This coupon has reached its usage limit" }, { status: 400 });
  }

  // 3. (review-loop 1, P1-B) Admin client config を increment より前に検証。
  // Codex review (PR #89) の指摘: 検証を後に置くと service_role 不備時に
  // current_uses だけ消費されて plan 更新が失敗する "burn-without-credit"
  // が起きる。検証順序を入れ替え、設定不備は increment 前に弾く。
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceRoleKey) {
    console.error("[coupon/redeem] service role not configured");
    return NextResponse.json(
      { error: "Server configuration error. Please contact support." },
      { status: 503 }
    );
  }
  const { createClient: createAdminClient } = await import("@supabase/supabase-js");
  const admin = createAdminClient(supabaseUrl, serviceRoleKey);

  // 3b. coupon.days を increment の前に検証する。null / NaN / 非数値文字列だと
  //     `new Date(NaN).toISOString()` が RangeError を投げる。これは increment の
  //     後ろ (line 103〜) で計算していたため、不正な days を持つ coupon では
  //     current_uses だけ消費されて 500 になる "burn-without-credit" を招く。
  //     検証を increment より前に置き、設定不備は use を消費する前に弾く。
  const couponDays = Number(coupon.days);
  if (!Number.isFinite(couponDays) || couponDays <= 0 || couponDays > 3650) {
    console.error(
      "[coupon/redeem] misconfigured coupon.days:",
      coupon.id,
      coupon.days
    );
    return NextResponse.json(
      { error: "Coupon is misconfigured. Please contact support." },
      { status: 500 }
    );
  }

  // 4. クーポンのcurrent_usesを楽観的ロックでインクリメント。
  // WHERE current_uses = coupon.current_uses で競合を検出。
  // admin client で実行: coupons の RLS は SELECT (authenticated) のみ許可、
  // INSERT/UPDATE/DELETE policy 不在 → user client では RLS deny。migration 016
  // で production faithful な policy 設計を再現したのに合わせ、increment は
  // service_role bypass で行う (#72 / Codex review PR #100)。
  const { data: updatedCoupons, error: incrementError } = await admin
    .from("coupons")
    .update({ current_uses: coupon.current_uses + 1 })
    .eq("id", coupon.id)
    .eq("current_uses", coupon.current_uses)
    // Re-assert `revoked = false` in the UPDATE itself: the validation above ran
    // against a stale SELECT, so an operator revoking the coupon between the
    // SELECT and this write would otherwise still let the redemption through.
    // The optimistic current_uses lock alone does not cover a revoke flip.
    .eq("revoked", false)
    // Re-assert the max_uses bound at write time. The capacity check above ran
    // against a stale SELECT; if an operator lowers max_uses between the SELECT
    // and this write the redemption could otherwise still push current_uses past
    // the cap. The CAS pins current_uses = coupon.current_uses, so comparing
    // max_uses against that literal is equivalent to `max_uses > current_uses`.
    // (max_uses <= 0 means "unlimited".)
    .or(`max_uses.lte.0,max_uses.gt.${coupon.current_uses}`)
    .select("id");

  if (incrementError) {
    console.error("Failed to increment coupon uses:", incrementError);
    return NextResponse.json({ error: "Failed to record coupon usage" }, { status: 500 });
  }

  if (!updatedCoupons || updatedCoupons.length === 0) {
    return NextResponse.json(
      { error: "Coupon usage conflict. Please try again." },
      { status: 409 }
    );
  }

  // 5. profilesテーブルを更新（クーポン消費が確定した後、admin 経由）。
  // 失敗した場合は increment を rollback。
  // P1-1: profiles.plan / trial_ends_at は migration 013 で user role の UPDATE
  // 権限が剥奪されている (billing bypass 防止)。
  const expiresAt = new Date(
    Date.now() + couponDays * 24 * 60 * 60 * 1000
  ).toISOString();

  const { data: updatedProfiles, error: profileError } = await admin
    .from("profiles")
    // subscription_status='trialing' marks this as a non-paying, time-boxed
    // grant. Without it the column keeps its 'active' DEFAULT, which the
    // trial-expiry job treats as a paying customer and never downgrades — a
    // coupon would grant the paid plan forever (see migration 025).
    .update({
      plan: coupon.tier,
      trial_ends_at: expiresAt,
      subscription_status: "trialing",
    })
    .eq("id", user.id)
    // PostgREST returns no error when an UPDATE matches zero rows (e.g. the
    // profile row is missing for user.id). Without checking affected rows the
    // coupon use would be burned with no plan granted and no rollback (since
    // profileError is null). Select the touched row so a zero-row update is
    // treated as a failure and routed through the rollback below.
    .select("id");

  if (profileError || !updatedProfiles || updatedProfiles.length === 0) {
    // P1-B 補強: profile update が失敗したら current_uses を decrement で
    // best-effort rollback。完璧ではない (race / DB error の二段失敗もある)
    // が、follow-up issue で 1-RPC transaction 化するまでの暫定。
    // (review-loop 2 P1): rollback の affected row 数も見る。0 行なら別 worker
    // がこの間に increment しているため burn-without-credit 確定。
    console.error(
      "[coupon/redeem] profile update failed:",
      profileError?.message ?? "0 rows updated (profile row missing for user)"
    );
    // rollback も admin client (service_role) で実行。migration 016 で coupons の
    // UPDATE policy は不在 (RLS deny) のため user client では rollback も無効
    // → 常に burn-without-credit に陥る (#72 PR #100 Codex review-loop 2 指摘)。
    const { data: rolledBack, error: rollbackError } = await admin
      .from("coupons")
      .update({ current_uses: coupon.current_uses })
      .eq("id", coupon.id)
      .eq("current_uses", coupon.current_uses + 1)
      .select("id");
    if (rollbackError) {
      console.error(
        "[coupon/redeem] BURN-WITHOUT-CREDIT: rollback DB error for coupon",
        coupon.id,
        "user",
        user.id,
        "error:",
        rollbackError.message
      );
    } else if (!rolledBack || rolledBack.length === 0) {
      console.error(
        "[coupon/redeem] BURN-WITHOUT-CREDIT: rollback no-op (concurrent redeem moved counter past N+1) for coupon",
        coupon.id,
        "user",
        user.id
      );
    }
    return NextResponse.json({ error: "Failed to update profile" }, { status: 500 });
  }

  return NextResponse.json({
    success: true,
    tier: coupon.tier,
    expires_at: expiresAt,
  });
}
