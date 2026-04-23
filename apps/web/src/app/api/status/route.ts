/**
 * GET /api/status — live health for external consumers + /status page (#37).
 * Thin wrapper over lib/health-probes (shared with the /status SSR page).
 */
import { NextResponse } from "next/server";

import { probeAll } from "@/lib/health-probes";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const result = await probeAll();
  return NextResponse.json(result);
}
