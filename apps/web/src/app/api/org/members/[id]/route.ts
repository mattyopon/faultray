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
  const { data: selfMember } = await supabase
    .from("org_members")
    .select("role, status")
    .eq("org_id", target.org_id)
    .eq("user_id", user.id)
    .maybeSingle();

  const { data: orgOwner } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", target.org_id)
    .maybeSingle();

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

  const { data: updated, error: updateError } = await supabase
    .from("org_members")
    .update({ role })
    .eq("id", id)
    .select("id, org_id, email, role, status, invited_at, joined_at")
    .single();

  if (updateError || !updated) {
    return NextResponse.json({ error: "Failed to update role" }, { status: 500 });
  }

  return NextResponse.json({ success: true, member: updated });
}
