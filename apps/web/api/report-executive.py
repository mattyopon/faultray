"""FaultRay executive report endpoint.

GET /api/report-executive?format=json
GET /api/report-executive?format=html

Returns executive summary report.
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


DEMO_REPORT = {
    "title": "FaultRay Infrastructure Resilience Report",
    "generated_at": "2026-03-30T12:00:00Z",
    "executive_summary": {
        "overall_score": 85.2,
        "availability_estimate": "99.99%",
        "risk_level": "Medium",
        "total_components": 12,
        "total_scenarios_tested": 2048,
        "critical_issues": 3,
        "recommendations_count": 8,
    },
    "key_findings": [
        {
            "severity": "CRITICAL",
            "finding": "Single point of failure in primary database — no automatic failover configured",
            "impact": "Complete service outage during database failures",
            "recommendation": "Implement automated failover with promotion time < 30 seconds",
        },
        {
            "severity": "HIGH",
            "finding": "Cache cluster lacks partition tolerance",
            "impact": "30% latency increase during network partitions",
            "recommendation": "Deploy Redis Cluster with 3+ nodes across availability zones",
        },
        {
            "severity": "HIGH",
            "finding": "No circuit breaker pattern between API and downstream services",
            "impact": "Cascading failures propagate across all services",
            "recommendation": "Implement circuit breaker with fallback responses",
        },
        {
            "severity": "MEDIUM",
            "finding": "Health check intervals too long (60s)",
            "impact": "Slow failure detection delays recovery by up to 2 minutes",
            "recommendation": "Reduce health check interval to 10 seconds",
        },
    ],
    "availability_breakdown": {
        "hardware_nines": 5.91,
        "software_nines": 4.0,
        "theoretical_nines": 6.65,
        "bottleneck": "Software layer",
    },
    "compliance_status": {
        "dora": {"status": "partial", "score": 72},
        "soc2": {"status": "partial", "score": 68},
        "iso27001": {"status": "compliant", "score": 85},
    },
    "improvement_roadmap": [
        {"priority": 1, "action": "Database failover automation", "effort": "Medium", "impact": "+0.5 nines", "timeline": "2 weeks"},
        {"priority": 2, "action": "Circuit breaker implementation", "effort": "Low", "impact": "+0.3 nines", "timeline": "1 week"},
        {"priority": 3, "action": "Cache cluster upgrade", "effort": "Medium", "impact": "+0.2 nines", "timeline": "1 week"},
        {"priority": 4, "action": "Health check optimization", "effort": "Low", "impact": "+0.1 nines", "timeline": "1 day"},
    ],
}


def _generate_html(report: dict) -> str:
    """Generate HTML report from data."""
    findings_html = ""
    for f in report["key_findings"]:
        color = "#ef4444" if f["severity"] == "CRITICAL" else "#f59e0b" if f["severity"] == "HIGH" else "#3b82f6"
        findings_html += f"""
        <div style="border-left: 4px solid {color}; padding: 12px 16px; margin: 12px 0; background: #111827; border-radius: 0 8px 8px 0;">
            <strong style="color: {color};">[{f["severity"]}]</strong> {f["finding"]}<br/>
            <small style="color: #94a3b8;">Impact: {f["impact"]}</small><br/>
            <small style="color: #10b981;">Recommendation: {f["recommendation"]}</small>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><title>{report["title"]}</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0a0e1a; color: #e2e8f0; max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
h1 {{ color: #FFD700; border-bottom: 2px solid #1e293b; padding-bottom: 16px; }}
h2 {{ color: #94a3b8; margin-top: 32px; }}
.score {{ font-size: 48px; font-weight: bold; color: #FFD700; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 16px 0; }}
.stat {{ background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 16px; text-align: center; }}
.stat-value {{ font-size: 24px; font-weight: bold; font-family: monospace; }}
.stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }}
</style></head><body>
<h1>{report["title"]}</h1>
<p style="color: #64748b;">Generated: {report["generated_at"]}</p>
<h2>Executive Summary</h2>
<div class="grid">
<div class="stat"><div class="stat-value" style="color: #FFD700;">{report["executive_summary"]["overall_score"]}</div><div class="stat-label">Resilience Score</div></div>
<div class="stat"><div class="stat-value" style="color: #10b981;">{report["executive_summary"]["availability_estimate"]}</div><div class="stat-label">Availability</div></div>
<div class="stat"><div class="stat-value" style="color: #ef4444;">{report["executive_summary"]["critical_issues"]}</div><div class="stat-label">Critical Issues</div></div>
</div>
<h2>Key Findings</h2>
{findings_html}
<h2>Improvement Roadmap</h2>
<table style="width: 100%; border-collapse: collapse;">
<tr style="border-bottom: 1px solid #1e293b;"><th style="text-align: left; padding: 8px; color: #64748b;">Priority</th><th style="text-align: left; padding: 8px; color: #64748b;">Action</th><th style="text-align: left; padding: 8px; color: #64748b;">Impact</th><th style="text-align: left; padding: 8px; color: #64748b;">Timeline</th></tr>
{"".join(f'<tr style="border-bottom: 1px solid #1e293b/50;"><td style="padding: 8px;">{r["priority"]}</td><td style="padding: 8px;">{r["action"]}</td><td style="padding: 8px; color: #10b981;">{r["impact"]}</td><td style="padding: 8px;">{r["timeline"]}</td></tr>' for r in report["improvement_roadmap"])}
</table>
</body></html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            fmt = params.get("format", ["json"])[0]

            if fmt == "html":
                html = _generate_html(DEMO_REPORT)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self._send_json(200, DEMO_REPORT)
        except Exception as e:
            self._send_error(500, f"Report error: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": {"message": message}})

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
