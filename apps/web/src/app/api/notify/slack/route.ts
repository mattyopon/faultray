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
  const { error } = await requireAuth();
  if (error) return error;

  // API-08: レート制限 — 10 requests / minute per IP
  const limited = applyRateLimit(request, { limit: 10, windowMs: 60_000 });
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
  if (typeof score !== "number") {
    return NextResponse.json({ error: "score is required" }, { status: 400 });
  }

  const criticalCount = typeof critical === "number" ? critical : 0;

  // Validate webhook URL format (must be a Slack incoming webhook)
  if (!webhookUrl.startsWith("https://hooks.slack.com/")) {
    return NextResponse.json({ error: "webhookUrl must be a Slack incoming webhook URL" }, { status: 400 });
  }

  const scoreEmoji = score >= 90 ? ":white_check_mark:" : score >= 70 ? ":warning:" : ":red_circle:";
  const criticalText = criticalCount > 0 ? `:rotating_light: *${criticalCount} CRITICAL* issue${criticalCount !== 1 ? "s" : ""}` : ":white_check_mark: No critical issues";
  const sourceText = source ? ` (${source})` : "";

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
      ...(topRecommendation
        ? [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: `:bulb: *Top Recommendation:* ${topRecommendation}`,
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

  try {
    const res = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
    console.error("[notify/slack] Error reaching webhook:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Failed to reach Slack webhook" }, { status: 502 });
  }
}
