import { NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-auth";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

interface SlackNotifyRequest {
  webhookUrl: string;
  score: number;
  critical: number;
  topRecommendation?: string;
  source?: string;
}

export async function POST(request: Request) {
  // API-01: 認証チェック
  const { error } = await requireAuth(request);
  if (error) return error;

  // API-08: レート制限 — 10 requests / minute per IP
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  let body: Partial<SlackNotifyRequest>;
  try {
    body = (await request.json()) as Partial<SlackNotifyRequest>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { webhookUrl, score, critical, topRecommendation, source } = body;

  if (!webhookUrl || typeof webhookUrl !== "string") {
    return NextResponse.json({ error: "webhookUrl is required" }, { status: 400 });
  }
  if (typeof score !== "number" || !Number.isFinite(score)) {
    // SEC (U16): reject NaN/Infinity (e.g. JSON `1e999` parses to Infinity),
    // which would render as "Infinity/100" in the Slack message.
    return NextResponse.json({ error: "score must be a finite number" }, { status: 400 });
  }

  const criticalCount = typeof critical === "number" ? critical : 0;

  // Validate webhook URL format (must be a Slack incoming webhook)
  // Use URL parser to prevent SSRF via https://hooks.slack.com.evil.com style bypasses
  let parsedWebhookUrl: URL;
  try {
    parsedWebhookUrl = new URL(webhookUrl);
  } catch {
    return NextResponse.json({ error: "webhookUrl must be a Slack incoming webhook URL" }, { status: 400 });
  }
  // SEC (U25): pin https + exact host. The host check already defeats
  // `hooks.slack.com.evil.com` / userinfo (`@evil.com`) bypasses; also require
  // https so the webhook (which embeds a secret token in its path) is never
  // sent in cleartext.
  if (parsedWebhookUrl.protocol !== "https:" || parsedWebhookUrl.hostname !== "hooks.slack.com") {
    return NextResponse.json({ error: "webhookUrl must be an https Slack incoming webhook URL" }, { status: 400 });
  }

  // Escape Slack mrkdwn metacharacters and cap length so user-controlled fields
  // cannot inject links (`<http://evil|click>`), control tokens, or oversized
  // content into the rendered alert.
  const escapeMrkdwn = (value: string, maxLen = 500): string =>
    value
      .slice(0, maxLen)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  const safeSource =
    typeof source === "string" ? escapeMrkdwn(source, 100) : "";
  const safeTopRecommendation =
    typeof topRecommendation === "string"
      ? escapeMrkdwn(topRecommendation, 500)
      : "";

  const scoreEmoji = score >= 90 ? ":white_check_mark:" : score >= 70 ? ":warning:" : ":red_circle:";
  const criticalText = criticalCount > 0 ? `:rotating_light: *${criticalCount} CRITICAL* issue${criticalCount !== 1 ? "s" : ""}` : ":white_check_mark: No critical issues";
  const sourceText = safeSource ? ` (${safeSource})` : "";

  const payload = {
    text: "FaultRay Simulation Complete",
    blocks: [
      {
        type: "header",
        text: {
          type: "plain_text",
          text: "FaultRay Simulation Complete",
          emoji: true,
        },
      },
      {
        type: "section",
        fields: [
          {
            type: "mrkdwn",
            text: `${scoreEmoji} *Score:* ${score.toFixed(1)}/100${sourceText}`,
          },
          {
            type: "mrkdwn",
            text: criticalText,
          },
        ],
      },
      ...(safeTopRecommendation
        ? [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: `:bulb: *Top Recommendation:* ${safeTopRecommendation}`,
              },
            },
          ]
        : []),
      {
        type: "actions",
        elements: [
          {
            type: "button",
            text: { type: "plain_text", text: "View Results", emoji: true },
            url: "https://app.faultray.com/simulate",
            action_id: "view_results",
          },
        ],
      },
    ],
  };

  // Bound the outbound call: a slow/stalled Slack endpoint would otherwise hold
  // this request handler (and its socket) open until the platform-level timeout,
  // which can exhaust resources under load. This is the only outbound call and
  // is user-triggerable.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `Slack webhook returned ${res.status}`, detail: text },
        { status: 502 }
      );
    }

    return NextResponse.json({ ok: true });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      console.error("[notify/slack] Webhook request timed out");
      return NextResponse.json(
        { error: "Slack webhook timed out" },
        { status: 504 }
      );
    }
    console.error("[notify/slack] Error reaching webhook:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Failed to reach Slack webhook" }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
