import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

/**
 * POST /api/contact — public contact-form submissions (#118).
 *
 * The form previously wrote to contact_requests directly from the browser
 * with the anon key, so nothing enforced validation or rate limits and the
 * table was scriptable from anywhere. Migration 020 revokes that path; this
 * route is now the only write surface: payloads are validated server-side,
 * rate-limited per IP, and inserted with the service-role client.
 *
 * No auth on purpose — it is a public form. CSRF is not a concern for this
 * endpoint (no session is used and the action is not privileged), so it does
 * not go through requireAuth.
 */

const FIELD_LIMITS: Record<string, number> = {
  company: 200,
  name: 200,
  email: 320,
  company_size: 50,
  message: 5000,
};

function sanitizeField(value: unknown, field: string): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed.length > FIELD_LIMITS[field]) return null;
  return trimmed;
}

export async function POST(request: Request) {
  // Public + unauthenticated → keep the window tight.
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const company = sanitizeField(body.company, "company");
  const name = sanitizeField(body.name, "name");
  const email = sanitizeField(body.email, "email");
  const companySize = sanitizeField(body.company_size, "company_size");
  const message = sanitizeField(body.message, "message");

  if (!company || !name || !email || !companySize || !message) {
    return NextResponse.json(
      { error: "All fields are required and must be within length limits" },
      { status: 400 }
    );
  }
  // Light shape check only — the field is operator-facing, not used for auth.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: "Invalid email address" }, { status: 400 });
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !serviceRoleKey) {
    return NextResponse.json(
      { error: "Contact form is temporarily unavailable" },
      { status: 503 }
    );
  }

  const { createClient } = await import("@supabase/supabase-js");
  const supabase = createClient(url, serviceRoleKey);

  const { error: insertError } = await supabase.from("contact_requests").insert({
    company,
    name,
    email,
    company_size: companySize,
    message,
  });

  if (insertError) {
    console.error("[contact] Insert error:", insertError.message);
    return NextResponse.json(
      { error: "Submission failed. Please try again." },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true }, { status: 201 });
}
