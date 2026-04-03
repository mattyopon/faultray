import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

interface CreateOrgBody {
  name: string;
}

export async function POST(request: Request) {
  const limited = applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  let body: Partial<CreateOrgBody>;
  try {
    body = (await request.json()) as Partial<CreateOrgBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { name } = body;
  if (!name || typeof name !== "string" || name.trim() === "") {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }

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

  // 組織を作成
  const { data: org, error: orgError } = await supabase
    .from("organizations")
    .insert({ name: name.trim(), owner_id: user.id })
    .select("id, name, owner_id, plan, created_at")
    .single();

  if (orgError || !org) {
    return NextResponse.json({ error: "Failed to create organization" }, { status: 500 });
  }

  // 自分をownerとしてorg_membersに追加
  const { error: memberError } = await supabase
    .from("org_members")
    .insert({
      org_id: org.id,
      user_id: user.id,
      email: user.email ?? "",
      role: "owner",
      status: "active",
      joined_at: new Date().toISOString(),
    });

  if (memberError) {
    // 組織は作成できたがメンバー追加に失敗した場合はログに留める
    console.error("Failed to add owner as member:", memberError);
  }

  return NextResponse.json({ success: true, org }, { status: 201 });
}
