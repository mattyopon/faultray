import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";
import { orgCreateSchema, formatZodError } from "@/lib/schemas";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2). Cross-origin org-creation requests are rejected.
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const parsed = orgCreateSchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(formatZodError(parsed.error), { status: 400 });
  }
  const { name } = parsed.data;

  // 組織を作成
  const { data: org, error: orgError } = await supabase
    .from("organizations")
    .insert({ name: name, owner_id: user.id })
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
    // メンバー追加失敗 — ownerなしの不整合な組織が残らないようにロールバック
    console.error("Failed to add owner as member, rolling back org creation:", memberError);
    await supabase.from("organizations").delete().eq("id", org.id);
    return NextResponse.json({ error: "Failed to initialize organization membership" }, { status: 500 });
  }

  return NextResponse.json({ success: true, org }, { status: 201 });
}
