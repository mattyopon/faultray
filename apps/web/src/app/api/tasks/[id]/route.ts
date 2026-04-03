import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

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
  const limited = applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

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

  // タスクが自分の組織のものか確認
  const { data: existing } = await supabase
    .from("tasks")
    .select("id, org_id")
    .eq("id", id)
    .single();

  if (!existing) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  const { data: membership } = await supabase
    .from("org_members")
    .select("id")
    .eq("org_id", existing.org_id)
    .eq("user_id", user.id)
    .eq("status", "active")
    .single();

  const { data: orgOwner } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", existing.org_id)
    .single();

  if (!membership && orgOwner?.owner_id !== user.id) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
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
  const limited = applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  const { id } = await params;

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

  // タスクが自分の組織のものか確認
  const { data: existing } = await supabase
    .from("tasks")
    .select("id, org_id")
    .eq("id", id)
    .single();

  if (!existing) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  const { data: membership } = await supabase
    .from("org_members")
    .select("id")
    .eq("org_id", existing.org_id)
    .eq("user_id", user.id)
    .eq("status", "active")
    .single();

  const { data: orgOwner } = await supabase
    .from("organizations")
    .select("owner_id")
    .eq("id", existing.org_id)
    .single();

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
