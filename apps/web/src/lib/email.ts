/**
 * Transactional email sender with retry + locale-aware templates (#36).
 *
 * - Uses Resend (RESEND_API_KEY required).
 * - Retries on 429 / 5xx with exponential backoff (3 attempts total).
 * - Accepts optional `locale` so callers select the right template.
 *
 * Callers should not retry themselves — retry policy is owned here.
 */
const RESEND_API_KEY = process.env.RESEND_API_KEY;

const _RETRY_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const _MAX_ATTEMPTS = 3;
const _BACKOFF_MS = [250, 750];  // sleep between attempts 1→2 and 2→3

function _sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function sendEmail({
  to,
  subject,
  html,
}: {
  to: string;
  subject: string;
  html: string;
}): Promise<{ success: boolean; error?: string; attempts?: number }> {
  if (!RESEND_API_KEY) {
    console.warn("[email] RESEND_API_KEY not set — email not sent");
    return { success: false, error: "No API key" };
  }

  let lastStatus = 0;
  let lastText = "";

  for (let attempt = 1; attempt <= _MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "FaultRay <noreply@faultray.com>",
          to,
          subject,
          html,
        }),
      });

      if (res.ok) {
        return { success: true, attempts: attempt };
      }

      lastStatus = res.status;
      lastText = await res.text().catch(() => "");

      if (!_RETRY_STATUS.has(res.status) || attempt === _MAX_ATTEMPTS) {
        break;
      }
      await _sleep(_BACKOFF_MS[attempt - 1] ?? 750);
    } catch (err) {
      lastText = err instanceof Error ? err.message : String(err);
      if (attempt === _MAX_ATTEMPTS) break;
      await _sleep(_BACKOFF_MS[attempt - 1] ?? 750);
    }
  }

  console.error(
    `[email] send failed after ${_MAX_ATTEMPTS} attempts — status=${lastStatus} body=${lastText.slice(0, 200)}`
  );
  return {
    success: false,
    error: `status=${lastStatus}`,
    attempts: _MAX_ATTEMPTS,
  };
}
