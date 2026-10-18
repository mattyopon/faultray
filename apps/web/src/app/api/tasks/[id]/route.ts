import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";

export const dynamic = "force-dynamic";

interface PatchTaskBody {
  status?: string;
  assignee_id?: string | null;
  title?: string;
  description?: string;
  priority?: string;
  due_date?: string | null;
}

const VALID_STATUSES = ["open", "in_progress", "done", "blocked"] as const;
const VALID_PRIORITIES = ["critical", "high", "medium", "low"] as const;

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2).
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

  const { id } = await params;

  let body: Partial<PatchTaskBody>;
  try {
    body = (await request.json()) as Partial<PatchTaskBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (body.status !== undefined) {
    if (!VALID_STATUSES.includes(body.status as (typeof VALID_STATUSES)[number])) {
      return NextResponse.json(
        { error: `status must be one of: ${VALID_STATUSES.join(", ")}` },
        { status: 400 }
      );
    }
  }
  if (body.priority !== undefined) {
    if (!VALID_PRIORITIES.includes(body.priority as (typeof VALID_PRIORITIES)[number])) {
      return NextResponse.json(
        { error: `priority must be one of: ${VALID_PRIORITIES.join(", ")}` },
        { status: 400 }
      );
    }
  }
  // title comes from untrusted JSON: a non-string value (e.g. {"title":123})
  // would throw on .trim() below and surface as a 500. Reject with 400.
  if (body.title !== undefined && typeof body.title !== "string") {
    return NextResponse.json({ error: "title must be a string" }, { status: 400 });
  }

  // タスクが自分の組織のものか確認。#122: real な query error と「行なし」を
  // 区別する。maybeSingle は 0 行で {data:null, error:null} を返すので、error は
  // DB 障害時のみ立つ。これを 404 に潰すと outage が「タスク無し」に偽装され、
  // 監視・自動リトライが効かなくなる。
  const { data: existing, error: existingError } = await supabase
    .from("tasks")
    .select("id, org_id")
    .eq("id", id)
    .maybeSingle();

  if (existingError) {
    return NextResponse.json({ error: "Failed to look up task" }, { status: 500 });
  }
  if (!existing) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  // 認可 lookup は maybeSingle() で「行なし (= 非メンバー)」と「DB 障害」を区別する。
  // .single() だと両者が同じ error になり、transient な DB 障害が 403 に化けて
  // 監視・リトライを誤らせる。genuine error は 500 にする。
  const { data: membership, error: membershipError } = await supabase
    .from("org_members")
    .select("id")
    .eq("org_id", existing.org_id)
    .eq("user_id", user.id)
    .eq("status", "active")
    .maybeSingle();

  const { data: orgOwner, error: orgOwnerError } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", existing.org_id)
    .maybeSingle();

  if (membershipError || orgOwnerError) {
    return NextResponse.json({ error: "Failed to verify permissions" }, { status: 500 });
  }

  if (!membership && orgOwner?.owner_id !== user.id) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // #80: assignee_id が cross-tenant でないことを app side で reject (DB 側の RLS
  // WITH CHECK は migration 018 で hardening 済の double-defense)。NULL 化は許可、
  // それ以外は task の existing.org_id に属する active member のみ。
  if (body.assignee_id !== undefined && body.assignee_id !== null) {
    const { data: assigneeMember, error: assigneeErr } = await supabase
      .from("org_members")
      .select("id")
      .eq("id", body.assignee_id)
      .eq("org_id", existing.org_id)
      .eq("status", "active")
      .maybeSingle();
    if (assigneeErr || !assigneeMember) {
      return NextResponse.json(
        { error: "assignee_id must be an active member of the same organization" },
        { status: 400 }
      );
    }
  }

  // 更新フィールドを構築
  const updatePayload: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };
  if (body.status !== undefined) updatePayload.status = body.status;
  if (body.assignee_id !== undefined) updatePayload.assignee_id = body.assignee_id;
  if (body.title !== undefined && body.title.trim() !== "")
    updatePayload.title = body.title.trim();
  if (body.description !== undefined) updatePayload.description = body.description;
  if (body.priority !== undefined) updatePayload.priority = body.priority;
  if (body.due_date !== undefined) updatePayload.due_date = body.due_date;

  const { data: task, error: updateError } = await supabase
    .from("tasks")
    .update(updatePayload)
    .eq("id", id)
    .select(
      "id, org_id, title, description, status, priority, assignee_id, created_by, due_date, source, source_id, created_at, updated_at"
    )
    .single();

  if (updateError || !task) {
    return NextResponse.json({ error: "Failed to update task" }, { status: 500 });
  }

  return NextResponse.json({ success: true, task });
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2). Critical for DELETE — CSRF would let a malicious
  // origin trigger task deletion in a logged-in user's tab.
  const { user, supabase, error: authError } = await requireAuth(request);
  if (authError) return authError;

  const { id } = await params;

  // タスクが自分の組織のものか確認。#122: real な query error と「行なし」を
  // 区別する。maybeSingle は 0 行で {data:null, error:null} を返すので、error は
  // DB 障害時のみ立つ。これを 404 に潰すと outage が「タスク無し」に偽装され、
  // 監視・自動リトライが効かなくなる。
  const { data: existing, error: existingError } = await supabase
    .from("tasks")
    .select("id, org_id")
    .eq("id", id)
    .maybeSingle();

  if (existingError) {
    return NextResponse.json({ error: "Failed to look up task" }, { status: 500 });
  }
  if (!existing) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  // 認可 lookup は maybeSingle() で「行なし (= 非メンバー)」と「DB 障害」を区別する
  // (PATCH と同じ理由)。genuine error は 500 にする。
  const { data: membership, error: membershipError } = await supabase
    .from("org_members")
    .select("id")
    .eq("org_id", existing.org_id)
    .eq("user_id", user.id)
    .eq("status", "active")
    .maybeSingle();

  const { data: orgOwner, error: orgOwnerError } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", existing.org_id)
    .maybeSingle();

  if (membershipError || orgOwnerError) {
    return NextResponse.json({ error: "Failed to verify permissions" }, { status: 500 });
  }

  if (!membership && orgOwner?.owner_id !== user.id) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { error: deleteError } = await supabase
    .from("tasks")
    .delete()
    .eq("id", id);

  if (deleteError) {
    return NextResponse.json({ error: "Failed to delete task" }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
