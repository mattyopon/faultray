import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

interface CreateTaskBody {
  title: string;
  description?: string;
  priority?: string;
  assignee_id?: string;
  due_date?: string;
  source?: string;
  source_id?: string;
}

const VALID_PRIORITIES = ["critical", "high", "medium", "low"] as const;

async function getOrgId(
  supabase: Awaited<ReturnType<typeof import("@/lib/supabase/server").createClient>>,
  userId: string
): Promise<string | null> {
  const { data: memberships } = await supabase
    .from("org_members")
    .select("org_id")
    .eq("user_id", userId)
    .eq("status", "active")
    .limit(1);

  if (memberships && memberships.length > 0) {
    return memberships[0].org_id as string;
  }

  const { data: ownedOrgs } = await supabase
    .from("organizations")
    .select("id")
    .eq("owner_id", userId)
    .limit(1);

  if (ownedOrgs && ownedOrgs.length > 0) {
    return ownedOrgs[0].id as string;
  }

  return null;
}

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

  const orgId = await getOrgId(supabase, user.id);
  if (!orgId) {
    return NextResponse.json({ tasks: [] });
  }

  const { data: tasks, error: tasksError } = await supabase
    .from("tasks")
    .select(
      "id, org_id, title, description, status, priority, assignee_id, created_by, due_date, source, source_id, created_at, updated_at"
    )
    .eq("org_id", orgId)
    .order("created_at", { ascending: false });

  if (tasksError) {
    return NextResponse.json({ error: "Failed to fetch tasks" }, { status: 500 });
  }

  return NextResponse.json({ tasks: tasks ?? [] });
}

export async function POST(request: Request) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  let body: Partial<CreateTaskBody>;
  try {
    body = (await request.json()) as Partial<CreateTaskBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { title, description, priority, assignee_id, due_date, source, source_id } = body;
  if (!title || typeof title !== "string" || title.trim() === "") {
    return NextResponse.json({ error: "title is required" }, { status: 400 });
  }

  const normalizedPriority = (priority ?? "medium") as string;
  if (!VALID_PRIORITIES.includes(normalizedPriority as (typeof VALID_PRIORITIES)[number])) {
    return NextResponse.json(
      { error: `priority must be one of: ${VALID_PRIORITIES.join(", ")}` },
      { status: 400 }
    );
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

  const orgId = await getOrgId(supabase, user.id);
  if (!orgId) {
    return NextResponse.json(
      { error: "No organization found. Create an organization first." },
      { status: 400 }
    );
  }

  const insertPayload: Record<string, unknown> = {
    org_id: orgId,
    title: title.trim(),
    description: description ?? "",
    priority: normalizedPriority,
    created_by: user.id,
    source: source ?? "",
    source_id: source_id ?? "",
  };
  if (assignee_id) insertPayload.assignee_id = assignee_id;
  if (due_date) insertPayload.due_date = due_date;

  const { data: task, error: insertError } = await supabase
    .from("tasks")
    .insert(insertPayload)
    .select(
      "id, org_id, title, description, status, priority, assignee_id, created_by, due_date, source, source_id, created_at, updated_at"
    )
    .single();

  if (insertError || !task) {
    return NextResponse.json({ error: "Failed to create task" }, { status: 500 });
  }

  return NextResponse.json({ success: true, task }, { status: 201 });
}
