function baseLayout(content: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FaultRay</title>
</head>
<body style="margin:0;padding:0;background:#0a0e1a;font-family:sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0e1a;min-height:100vh;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1e293b;">
          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;border-bottom:1px solid #1e293b;">
              <span style="font-size:22px;font-weight:700;color:#FFD700;letter-spacing:-0.5px;">FaultRay</span>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px 40px;">
              ${content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;border-top:1px solid #1e293b;background:#0d1117;">
              <p style="margin:0;font-size:12px;color:#64748b;line-height:1.6;">
                You received this email because you have an account with FaultRay.<br />
                <a href="https://faultray.com/settings" style="color:#FFD700;text-decoration:none;">Manage email preferences</a>
                &nbsp;&middot;&nbsp;
                <a href="https://faultray.com/unsubscribe" style="color:#64748b;text-decoration:none;">Unsubscribe</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}

function ctaButton(href: string, label: string): string {
  return `<a href="${href}" style="display:inline-block;padding:12px 28px;background:#FFD700;color:#0a0e1a;font-weight:700;font-size:14px;border-radius:8px;text-decoration:none;margin-top:24px;">${label}</a>`;
}

export function welcomeEmail(name: string): { subject: string; html: string } {
  const subject = "Welcome to FaultRay — Let's estimate your system's resilience";
  const html = baseLayout(`
    <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;color:#f1f5f9;">Welcome, ${name}!</h1>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#94a3b8;">
      Your 7-day Business trial is now active. FaultRay lets you simulate 2,000+ failure scenarios
      — without touching production.
    </p>
    <h2 style="margin:24px 0 12px;font-size:16px;font-weight:600;color:#e2e8f0;">Quick Start Guide</h2>
    <ol style="margin:0 0 16px;padding-left:20px;font-size:14px;line-height:1.9;color:#94a3b8;">
      <li>Go to <strong style="color:#e2e8f0;">Dashboard</strong> and create your first project</li>
      <li>Add your infrastructure topology (nodes, dependencies)</li>
      <li>Run a simulation — pick from 2,000+ fault scenarios</li>
      <li>Review your resilience score and critical failure paths</li>
      <li>Generate a compliance-ready report (SOC2, ISO 27001)</li>
    </ol>
    ${ctaButton("https://faultray.com/dashboard", "Go to Dashboard")}
  `);
  return { subject, html };
}

export function trialReminderEmail(
  name: string,
  daysLeft: number
): { subject: string; html: string } {
  const subject = `Your FaultRay trial ends in ${daysLeft} day${daysLeft === 1 ? "" : "s"}`;
  const urgencyColor = daysLeft <= 2 ? "#ef4444" : "#FFD700";
  const html = baseLayout(`
    <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;color:#f1f5f9;">Hi ${name},</h1>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#94a3b8;">
      Your FaultRay Business trial expires in
      <strong style="color:${urgencyColor};">${daysLeft} day${daysLeft === 1 ? "" : "s"}</strong>.
      Don't lose access to your simulations and reports.
    </p>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.7;color:#94a3b8;">
      Upgrade now to keep your resilience data, scheduled simulations, and compliance reports.
    </p>
    ${ctaButton("https://faultray.com/pricing", "Upgrade Now")}
    <p style="margin:24px 0 0;font-size:13px;color:#64748b;">
      Questions? Reply to this email and we'll help you find the right plan.
    </p>
  `);
  return { subject, html };
}

export function simulationCompleteEmail(
  name: string,
  score: number,
  criticalCount: number
): { subject: string; html: string } {
  const scoreColor = score >= 80 ? "#22c55e" : score >= 60 ? "#FFD700" : "#ef4444";
  const subject = `Simulation complete — Resilience score: ${score}/100`;
  const html = baseLayout(`
    <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;color:#f1f5f9;">Hi ${name},</h1>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.7;color:#94a3b8;">
      Your FaultRay simulation has finished. Here's a summary of your results:
    </p>
    <table cellpadding="0" cellspacing="0" style="width:100%;background:#0d1117;border-radius:8px;border:1px solid #1e293b;margin-bottom:24px;">
      <tr>
        <td style="padding:20px 24px;border-bottom:1px solid #1e293b;">
          <p style="margin:0 0 4px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">Resilience Score</p>
          <p style="margin:0;font-size:36px;font-weight:700;color:${scoreColor};">${score}<span style="font-size:18px;color:#94a3b8;">/100</span></p>
        </td>
        <td style="padding:20px 24px;border-bottom:1px solid #1e293b;">
          <p style="margin:0 0 4px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">Critical Failures</p>
          <p style="margin:0;font-size:36px;font-weight:700;color:${criticalCount > 0 ? "#ef4444" : "#22c55e"};">${criticalCount}</p>
        </td>
      </tr>
    </table>
    ${ctaButton("https://faultray.com/results", "View Full Report")}
  `);
  return { subject, html };
}
