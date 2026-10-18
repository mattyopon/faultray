/**
 * Shared Zod schemas for API route validation (#33).
 *
 * Each POST/PUT route imports the matching schema from here instead
 * of hand-rolling type guards. Centralises validation + error shape.
 *
 * Usage:
 *   import { orgCreateSchema, formatZodError } from "@/lib/schemas";
 *
 *   const parsed = orgCreateSchema.safeParse(await req.json());
 *   if (!parsed.success) {
 *     return NextResponse.json(formatZodError(parsed.error), { status: 400 });
 *   }
 *   const { name } = parsed.data;
 */

import { z } from "zod";

const _trimmedNonEmptyString = (max: number) =>
  z
    .string()
    .transform((s) => s.trim())
    .pipe(z.string().min(1).max(max));

export const orgCreateSchema = z.object({
  name: _trimmedNonEmptyString(120),
});
export type OrgCreateInput = z.infer<typeof orgCreateSchema>;

export const orgInviteSchema = z.object({
  org_id: z.string().uuid(),
  email: z.string().email().max(320),
  role: z.enum(["admin", "member", "viewer"]).default("member"),
});
export type OrgInviteInput = z.infer<typeof orgInviteSchema>;

export const taskCreateSchema = z.object({
  title: _trimmedNonEmptyString(200),
  description: z.string().max(5000).optional(),
  source: z.enum(["api", "ui", "webhook"]).default("api"),
  source_id: z
    .string()
    .regex(/^[a-z0-9][a-z0-9-]*$/i, "source_id must be alphanumeric + hyphen")
    .max(64)
    .optional(),
});
export type TaskCreateInput = z.infer<typeof taskCreateSchema>;

export function formatZodError(err: z.ZodError): {
  error: string;
  details: Array<{ path: string; message: string }>;
} {
  return {
    error: "Validation failed",
    details: err.issues.map((i) => ({
      path: i.path.join("."),
      message: i.message,
    })),
  };
}
