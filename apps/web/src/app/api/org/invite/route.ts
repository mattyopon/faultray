import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";

export const dynamic = "force-dynamic";

interface InviteBody {
  org_id: string;
  email: string;
  role: string;
}

// P1-7: 'owner' は招待経由で付与不可。owner promotion は service_role RPC のみ。
// migration 013 の "Admins can invite" policy で role IN ('member','admin') を強制。
const VALID_ROLES = ["admin", "member", "viewer"] as const;

export async function POST(request: Request) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2).
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

  let body: Partial<InviteBody>;
  try {
    body = (await request.json()) as Partial<InviteBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { org_id, email, role } = body;
  if (!org_id || typeof org_id !== "string") {
    return NextResponse.json({ error: "org_id is required" }, { status: 400 });
  }
  if (!email || typeof email !== "string" || !email.includes("@")) {
    return NextResponse.json({ error: "Valid email is required" }, { status: 400 });
  }
  const normalizedRole = (role ?? "member") as string;
  if (!VALID_ROLES.includes(normalizedRole as (typeof VALID_ROLES)[number])) {
    return NextResponse.json(
      { error: `role must be one of: ${VALID_ROLES.join(", ")}` },
      { status: 400 }
    );
  }

  // 自分がowner/adminかチェック
  const { data: selfMember } = await supabase
    .from("org_members")
    .select("role, status")
    .eq("org_id", org_id)
    .eq("user_id", user.id)
    .single();

  const { data: orgOwner } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", org_id)
    .single();

  const isOwner = orgOwner?.owner_id === user.id;
  const isAdmin =
    selfMember?.status === "active" &&
    (selfMember?.role === "owner" || selfMember?.role === "admin");

  if (!isOwner && !isAdmin) {
    return NextResponse.json({ error: "Forbidden: admin or owner required" }, { status: 403 });
  }

  // 既存招待チェック
  const { data: existing } = await supabase
    .from("org_members")
    .select("id, status")
    .eq("org_id", org_id)
    .eq("email", email.toLowerCase())
    .single();

  if (existing && existing.status !== "removed") {
    return NextResponse.json(
      { error: "This email is already invited or a member" },
      { status: 409 }
    );
  }

  // 招待レコード作成（pending）
  const { data: member, error: insertError } = await supabase
    .from("org_members")
    .insert({
      org_id,
      email: email.toLowerCase().trim(),
      role: normalizedRole,
      status: "pending",
    })
    .select("id, org_id, email, role, status, invited_at")
    .single();

  if (insertError || !member) {
    return NextResponse.json({ error: "Failed to create invitation" }, { status: 500 });
  }

  return NextResponse.json({ success: true, member }, { status: 201 });
}
