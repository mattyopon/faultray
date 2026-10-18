/**
 * GET /api/status — live health for external consumers + /status page (#37).
 * Thin wrapper over lib/health-probes (shared with the /status SSR page).
 *
 * #86 (P3-1): unauthenticated callers receive only the overall status to
 *   avoid leaking per-vendor latency / config presence (used for dependency
 *   mapping and timing abuse). `?detailed=true` requires an authenticated
 *   session to return per-service details. The /status SSR page reads the
 *   detailed shape directly from probeAll() with the SSR cookie context, so
 *   the user-facing dashboard is unaffected.
 */
import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { probeAll } from "@/lib/health-probes";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const wantsDetailed = url.searchParams.get("detailed") === "true";

  // (review-loop 1, P2): auth check を probe より前に置く。さもないと unauth
  // caller でも全 vendor probe が triggered され、overall response の latency
  // から per-vendor timing を推定できてしまう (本 PR の info-disclosure 対策が
  // 形骸化)。upstream services への load も軽減。
  if (wantsDetailed) {
    // (review-loop 5, P2 — Codex 2026-05-06): Supabase env が unset / 壊れた
    // 環境で createClient() は throw する。route 全体が 500 になり、しかも
    // ?detailed=true の query 一発で誰でも error path を踏める。config 不在は
    // 「detailed view は今出せない」という controlled response (503) で返す。
    let supabase;
    try {
      supabase = await createClient();
    } catch {
      return NextResponse.json(
        { error: "Detailed status temporarily unavailable." },
        { status: 503 }
      );
    }
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json(
        { error: "Authentication required for detailed status." },
        { status: 401 }
      );
    }
    return NextResponse.json(await probeAll());
  }

  // 未認証 (公開): 既存 contract (overall / services[ServiceProbe] / checked_at)
  // を完全に維持。ただし dependency mapping / timing abuse の核となる
  // latency_ms / note は **null に置き換え** て隠す。`s.latency_ms` を読む
  // 既存 monitor は型 (number | null) のまま動作し、null check で問題なく
  // skip できる。`s.note` も同様。
  // (review-loop 2 → 3, P2): shape そのものを縮めると外部 monitor が即破綻するため
  // 値だけを null 化する compatible-strip 方式に再修正。
  const result = await probeAll();
  return NextResponse.json({
    overall: result.overall,
    services: result.services.map((s) => ({
      name: s.name,
      status: s.status,
      latency_ms: null,
      note: null,
    })),
    checked_at: result.checked_at,
  });
}
