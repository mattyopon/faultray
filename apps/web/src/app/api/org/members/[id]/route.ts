import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";

export const dynamic = "force-dynamic";

/**
 * PATCH /api/org/members/[id] — change a member's role (#119).
 *
 * The teams page has offered an inline role selector since FLOW-08, but this
 * route never existed: every change 404'd while the UI optimistically showed
 * success. Same trust rules as /api/org/invite: caller must be the org owner
 * or an active admin, and 'owner' can be neither assigned nor taken away here
 * (owner promotion stays a service-role concern).
 */

const VALID_ROLES = ["admin", "member", "viewer"] as const;

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate.
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

  const { id } = await params;

  let body: { role?: unknown };
  try {
    body = (await request.json()) as { role?: unknown };
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const role = body.role;
  if (
    typeof role !== "string" ||
    !VALID_ROLES.includes(role as (typeof VALID_ROLES)[number])
  ) {
    return NextResponse.json(
      { error: `role must be one of: ${VALID_ROLES.join(", ")}` },
      { status: 400 }
    );
  }

  // 対象メンバー行 → 所属 org の解決。DB エラーは 404 に潰さない (#122 と同様)。
  const { data: target, error: targetError } = await supabase
    .from("org_members")
    .select("id, org_id, role, status")
    .eq("id", id)
    .maybeSingle();

  if (targetError) {
    return NextResponse.json({ error: "Failed to look up member" }, { status: 500 });
  }
  if (!target) {
    return NextResponse.json({ error: "Member not found" }, { status: 404 });
  }
  if (target.role === "owner") {
    return NextResponse.json(
      { error: "The owner's role cannot be changed here" },
      { status: 403 }
    );
  }

  // 呼び出し元がその org の owner か active admin かを検証 (invite と同じ規則)。
  // 認可 lookup の DB error を握りつぶすと「権限なし」と「DB 障害」が区別できず、
  // 正当な admin/owner の操作が誤って 403 になる。genuine error は 500 にする。
  const { data: selfMember, error: selfMemberError } = await supabase
    .from("org_members")
    .select("role, status")
    .eq("org_id", target.org_id)
    .eq("user_id", user.id)
    .maybeSingle();

  const { data: orgOwner, error: orgOwnerError } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", target.org_id)
    .maybeSingle();

  if (selfMemberError || orgOwnerError) {
    console.error(
      "[org/members/[id]] Authorization lookup failed:",
      selfMemberError?.message ?? orgOwnerError?.message
    );
    return NextResponse.json({ error: "Failed to verify permissions" }, { status: 500 });
  }

  const isOwner = orgOwner?.owner_id === user.id;
  const isAdmin =
    selfMember?.status === "active" &&
    (selfMember?.role === "owner" || selfMember?.role === "admin");

  if (!isOwner && !isAdmin) {
    return NextResponse.json(
      { error: "Forbidden: admin or owner required" },
      { status: 403 }
    );
  }

  // Re-assert `role <> 'owner'` in the UPDATE predicate itself to close the
  // TOCTOU window: the `target.role === 'owner'` check above ran against an
  // earlier read, so a member promoted to owner between that read and this write
  // could otherwise have their owner role overwritten despite the prohibition.
  const { data: updated, error: updateError } = await supabase
    .from("org_members")
    .update({ role })
    .eq("id", id)
    .neq("role", "owner")
    .select("id, org_id, email, role, status, invited_at, joined_at")
    .maybeSingle();

  if (updateError) {
    return NextResponse.json({ error: "Failed to update role" }, { status: 500 });
  }
  if (!updated) {
    // No row matched the `id AND role <> 'owner'` predicate: the member became
    // an owner concurrently (or was removed). Refuse rather than silently no-op.
    return NextResponse.json(
      { error: "The owner's role cannot be changed here" },
      { status: 409 }
    );
  }

  return NextResponse.json({ success: true, member: updated });
}
