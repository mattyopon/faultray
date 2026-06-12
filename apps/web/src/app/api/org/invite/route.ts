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

  // #117: 読み取りと挿入で正規化を揃える (旧コードは read 側だけ trim 無し)。
  const normalizedEmail = email.toLowerCase().trim();

  // 既存招待チェック。.single() は「複数行」も「0行」もエラーにするため、
  // 重複が一度できると error (無視されていた) → existing=null → さらに重複、
  // という増殖ループになっていた。maybeSingle + limit(1) + error の hard-fail
  // に変更。最終的な一意性は migration 021 の partial unique index が保証する。
  const { data: existing, error: existingError } = await supabase
    .from("org_members")
    .select("id, status")
    .eq("org_id", org_id)
    .eq("email", normalizedEmail)
    .neq("status", "removed")
    .limit(1)
    .maybeSingle();

  if (existingError) {
    return NextResponse.json(
      { error: "Failed to check existing invitations" },
      { status: 500 }
    );
  }
  if (existing) {
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
      email: normalizedEmail,
      role: normalizedRole,
      status: "pending",
    })
    .select("id, org_id, email, role, status, invited_at")
    .single();

  if (insertError || !member) {
    // 並行リクエストが pre-insert read をすり抜けた場合、migration 021 の
    // org_members_live_email_unique がここで 23505 を返す — レースの正しい
    // 結末として 409 にマップする。
    if (insertError?.code === "23505") {
      return NextResponse.json(
        { error: "This email is already invited or a member" },
        { status: 409 }
      );
    }
    return NextResponse.json({ error: "Failed to create invitation" }, { status: 500 });
  }

  return NextResponse.json({ success: true, member }, { status: 201 });
}
