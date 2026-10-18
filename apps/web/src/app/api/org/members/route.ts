import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const limited = await applyRateLimit(request, { limit: 30, windowMs: 60_000 });
  if (limited) return limited;

  let supabase: Awaited<ReturnType<typeof import("@/lib/supabase/server").createClient>>;
  try {
    const { createClient } = await import("@/lib/supabase/server");
    supabase = await createClient();
  } catch {
    return NextResponse.json({ error: "Supabase not configured" }, { status: 503 });
  }

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // 自分が所属するアクティブな組織IDを取得
  const { data: myMemberships } = await supabase
    .from("org_members")
    .select("org_id")
    .eq("user_id", user.id)
    .eq("status", "active")
    .order("invited_at", { ascending: true });

  // ownerとして作成した組織も含める
  const { data: ownedOrgs } = await supabase
    .from("organizations")
    .select("id")
    .eq("owner_id", user.id)
    .order("created_at", { ascending: true });

  const orgIds = Array.from(
    new Set([
      ...(myMemberships ?? []).map((m) => m.org_id),
      ...(ownedOrgs ?? []).map((o) => o.id),
    ])
  );

  if (orgIds.length === 0) {
    return NextResponse.json({ members: [], org: null });
  }

  // 最初の組織の情報とメンバーを返す（将来的に複数組織対応可能）
  const orgId = orgIds[0];

  // .single() は 0 行でも error を返すため、stale/deleted な orgId や transient
  // な DB 障害を「org: null」に潰してしまう。maybeSingle() に変更し、genuine な
  // query error は 500 にして missing org (null) と区別する。
  const { data: org, error: orgError } = await supabase
    .from("organizations")
    .select("id, name, plan, created_at")
    .eq("id", orgId)
    .maybeSingle();

  if (orgError) {
    return NextResponse.json({ error: "Failed to fetch organization" }, { status: 500 });
  }

  const { data: members, error: membersError } = await supabase
    .from("org_members")
    .select("id, org_id, user_id, email, role, status, invited_at, joined_at")
    .eq("org_id", orgId)
    .order("invited_at", { ascending: true });

  if (membersError) {
    return NextResponse.json({ error: "Failed to fetch members" }, { status: 500 });
  }

  return NextResponse.json({ members: members ?? [], org });
}
