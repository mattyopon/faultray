"""FaultRay reports + risk endpoint (merged to stay within Vercel Hobby function limit).

GET /api/reports?action=report&format=json
GET /api/reports?action=report&format=html
GET /api/reports?action=incidents
GET /api/risk?action=attack-surface  (rewritten to /api/reports by vercel.json)
GET /api/risk?action=fmea

POST /api/reports  Body: { "action": "report" | "incidents" | "attack-surface" | "fmea" }
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


# --- Executive report data ---

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


# --- Incidents data ---

INCIDENTS_DEMO_DATA = {
    "incidents": [
        {
            "id": "INC-001",
            "title": "Cascading Database Failure",
            "severity": "critical",
            "start_time": "2026-03-28T14:23:00Z",
            "end_time": "2026-03-28T14:35:00Z",
            "duration_minutes": 12,
            "affected_components": ["db_primary", "api", "worker"],
            "root_cause": "Primary database disk I/O saturation",
            "timeline": [
                {"time": "T+0:00", "event": "Database disk I/O reaches 100%", "component": "db_primary", "type": "trigger"},
                {"time": "T+0:30", "event": "Query latency exceeds 5s threshold", "component": "db_primary", "type": "degradation"},
                {"time": "T+1:00", "event": "Connection pool exhausted (200/200)", "component": "db_primary", "type": "failure"},
                {"time": "T+1:15", "event": "API server health check fails", "component": "api", "type": "cascade"},
                {"time": "T+1:30", "event": "Background workers queue backlog", "component": "worker", "type": "cascade"},
                {"time": "T+2:00", "event": "Load balancer marks API servers unhealthy", "component": "gateway", "type": "cascade"},
                {"time": "T+5:00", "event": "Alert fired, on-call engineer paged", "component": "monitor", "type": "detection"},
                {"time": "T+8:00", "event": "Manual failover to replica initiated", "component": "db_replica", "type": "recovery"},
                {"time": "T+10:00", "event": "Replica promoted to primary", "component": "db_replica", "type": "recovery"},
                {"time": "T+12:00", "event": "All services recovered", "component": "all", "type": "resolved"},
            ],
        },
        {
            "id": "INC-002",
            "title": "Cache Cluster Network Partition",
            "severity": "high",
            "start_time": "2026-03-27T09:15:00Z",
            "end_time": "2026-03-27T09:28:00Z",
            "duration_minutes": 13,
            "affected_components": ["cache", "api"],
            "root_cause": "Network partition between cache nodes in different AZs",
            "timeline": [
                {"time": "T+0:00", "event": "Network partition between AZ-1a and AZ-1b", "component": "network", "type": "trigger"},
                {"time": "T+0:15", "event": "Cache cluster split-brain detected", "component": "cache", "type": "failure"},
                {"time": "T+0:30", "event": "Cache hit rate drops from 95% to 40%", "component": "cache", "type": "degradation"},
                {"time": "T+1:00", "event": "Database query load increases 3x", "component": "db_primary", "type": "cascade"},
                {"time": "T+2:00", "event": "API response time increases to 2.5s", "component": "api", "type": "degradation"},
                {"time": "T+5:00", "event": "Network partition resolved", "component": "network", "type": "recovery"},
                {"time": "T+8:00", "event": "Cache re-sync initiated", "component": "cache", "type": "recovery"},
                {"time": "T+13:00", "event": "Cache hit rate returns to 95%", "component": "cache", "type": "resolved"},
            ],
        },
        {
            "id": "INC-003",
            "title": "DNS Resolution Failure",
            "severity": "high",
            "start_time": "2026-03-25T22:10:00Z",
            "end_time": "2026-03-25T22:18:00Z",
            "duration_minutes": 8,
            "affected_components": ["dns", "cdn", "gateway"],
            "root_cause": "DNS provider TTL expiry during maintenance window",
            "timeline": [
                {"time": "T+0:00", "event": "DNS provider begins maintenance", "component": "dns", "type": "trigger"},
                {"time": "T+0:30", "event": "DNS TTL expires, resolution fails", "component": "dns", "type": "failure"},
                {"time": "T+1:00", "event": "CDN unable to resolve origin", "component": "cdn", "type": "cascade"},
                {"time": "T+1:30", "event": "New connections fail, existing connections unaffected", "component": "gateway", "type": "degradation"},
                {"time": "T+3:00", "event": "Secondary DNS takes over", "component": "dns", "type": "recovery"},
                {"time": "T+5:00", "event": "DNS propagation complete", "component": "dns", "type": "recovery"},
                {"time": "T+8:00", "event": "All traffic flowing normally", "component": "all", "type": "resolved"},
            ],
        },
    ],
    "summary": {
        "total_incidents": 3,
        "critical": 1,
        "high": 2,
        "medium": 0,
        "average_duration_minutes": 11,
        "most_affected_component": "db_primary",
    },
}


# --- Attack surface data (merged from risk.py) ---

ATTACK_SURFACE_DEMO_DATA = {
    "summary": {
        "total_components": 12,
        "external_facing": 4,
        "internal_only": 8,
        "risk_level": "medium",
        "attack_vectors": 7,
    },
    "external_components": [
        {
            "id": "cdn", "name": "CDN / Edge", "exposure": "public",
            "ports": [80, 443], "protocols": ["HTTP", "HTTPS"], "risk_score": 35,
            "vulnerabilities": [
                {"type": "DDoS", "severity": "medium", "mitigation": "Rate limiting configured"},
                {"type": "Cache poisoning", "severity": "low", "mitigation": "Cache-Control headers set"},
            ],
        },
        {
            "id": "gateway", "name": "API Gateway", "exposure": "public",
            "ports": [443], "protocols": ["HTTPS"], "risk_score": 45,
            "vulnerabilities": [
                {"type": "Injection attacks", "severity": "high", "mitigation": "Input validation in place"},
                {"type": "Authentication bypass", "severity": "high", "mitigation": "OAuth2 + PKCE configured"},
                {"type": "Rate limit exhaustion", "severity": "medium", "mitigation": "Per-user rate limits"},
            ],
        },
        {
            "id": "auth", "name": "Auth Service", "exposure": "semi-public",
            "ports": [443], "protocols": ["HTTPS"], "risk_score": 55,
            "vulnerabilities": [
                {"type": "Brute force", "severity": "medium", "mitigation": "Account lockout after 5 attempts"},
                {"type": "Session hijacking", "severity": "high", "mitigation": "Secure cookie flags set"},
            ],
        },
        {
            "id": "dns", "name": "DNS", "exposure": "public",
            "ports": [53], "protocols": ["DNS", "DNSSEC"], "risk_score": 25,
            "vulnerabilities": [
                {"type": "DNS spoofing", "severity": "medium", "mitigation": "DNSSEC enabled"},
            ],
        },
    ],
    "internal_components": [
        {"id": "api", "name": "API Server", "risk_score": 30},
        {"id": "worker", "name": "Background Worker", "risk_score": 15},
        {"id": "db_primary", "name": "PostgreSQL Primary", "risk_score": 60},
        {"id": "db_replica", "name": "PostgreSQL Replica", "risk_score": 25},
        {"id": "cache", "name": "Redis Cache", "risk_score": 40},
        {"id": "queue", "name": "Message Queue", "risk_score": 20},
        {"id": "storage", "name": "Object Storage", "risk_score": 15},
        {"id": "monitor", "name": "Monitoring", "risk_score": 10},
    ],
    "recommendations": [
        "Implement WAF (Web Application Firewall) before API Gateway",
        "Enable mutual TLS for internal service communication",
        "Add network segmentation between data and application tiers",
        "Implement egress filtering to prevent data exfiltration",
        "Deploy intrusion detection system (IDS) for database tier",
    ],
}

# --- FMEA data (merged from risk.py) ---

FMEA_DEMO_DATA = {
    "analysis_date": "2026-03-30",
    "total_failure_modes": 18,
    "critical_rpn_threshold": 200,
    "high_rpn_count": 4,
    "failure_modes": [
        {"id": "FM-001", "component": "PostgreSQL Primary", "failure_mode": "Complete database crash", "effect": "All write operations fail, data loss risk", "severity": 9, "occurrence": 3, "detection": 8, "rpn": 216, "recommended_action": "Implement automated failover with < 30s switchover", "status": "open"},
        {"id": "FM-002", "component": "Redis Cache", "failure_mode": "Memory exhaustion", "effect": "Cache eviction storm, database overload", "severity": 7, "occurrence": 5, "detection": 6, "rpn": 210, "recommended_action": "Set memory limits, implement eviction policies", "status": "open"},
        {"id": "FM-003", "component": "API Gateway", "failure_mode": "Certificate expiry", "effect": "All HTTPS connections rejected", "severity": 10, "occurrence": 2, "detection": 9, "rpn": 180, "recommended_action": "Automate cert renewal with Let's Encrypt", "status": "mitigated"},
        {"id": "FM-004", "component": "API Server", "failure_mode": "Thread pool exhaustion", "effect": "Requests queued, timeouts for users", "severity": 6, "occurrence": 6, "detection": 4, "rpn": 144, "recommended_action": "Implement connection limits and auto-scaling", "status": "open"},
        {"id": "FM-005", "component": "DNS", "failure_mode": "DNS resolution failure", "effect": "Service unreachable for all users", "severity": 10, "occurrence": 1, "detection": 7, "rpn": 70, "recommended_action": "Multi-provider DNS with health checks", "status": "mitigated"},
        {"id": "FM-006", "component": "CDN / Edge", "failure_mode": "Origin pull failure", "effect": "Stale content served, dynamic requests fail", "severity": 5, "occurrence": 3, "detection": 3, "rpn": 45, "recommended_action": "Configure fallback origins", "status": "mitigated"},
        {"id": "FM-007", "component": "Auth Service", "failure_mode": "Token validation failure", "effect": "Users unable to authenticate", "severity": 8, "occurrence": 2, "detection": 5, "rpn": 80, "recommended_action": "Implement token caching and offline validation", "status": "open"},
        {"id": "FM-008", "component": "Background Worker", "failure_mode": "Job queue backlog", "effect": "Delayed processing, stale data", "severity": 4, "occurrence": 5, "detection": 3, "rpn": 60, "recommended_action": "Implement dead letter queue and monitoring", "status": "open"},
        {"id": "FM-009", "component": "PostgreSQL Primary", "failure_mode": "Replication lag", "effect": "Read replicas serve stale data", "severity": 5, "occurrence": 4, "detection": 4, "rpn": 80, "recommended_action": "Monitor replication lag, implement read-after-write consistency", "status": "open"},
        {"id": "FM-010", "component": "API Gateway", "failure_mode": "Rate limit misconfiguration", "effect": "Legitimate traffic blocked during peaks", "severity": 7, "occurrence": 3, "detection": 5, "rpn": 105, "recommended_action": "Implement adaptive rate limiting based on traffic patterns", "status": "open"},
    ],
    "rpn_distribution": {"critical": 2, "high": 2, "medium": 4, "low": 2},
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _dispatch(action: str, params: dict, body: dict | None = None):
    """Route to the correct handler based on action."""
    if action == "report":
        fmt = params.get("format", ["json"])[0] if isinstance(params.get("format"), list) else (body or {}).get("format", "json")
        if fmt == "html":
            return "html", DEMO_REPORT
        return "json", DEMO_REPORT
    elif action == "incidents":
        return "json", INCIDENTS_DEMO_DATA
    elif action == "attack-surface":
        return "json", ATTACK_SURFACE_DEMO_DATA
    elif action == "fmea":
        return "json", FMEA_DEMO_DATA
    else:
        return "error", f"Unknown action '{action}'. Use 'report', 'incidents', 'attack-surface', or 'fmea'."


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action = params.get("action", ["report"])[0]
            content_type, data = _dispatch(action, params)

            if content_type == "error":
                self._send_error(400, data)
            elif content_type == "html":
                html = _generate_html(data)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self._send_json(200, data)
        except Exception as e:
            self._send_error(500, f"Reports error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
            action = body.get("action", "")
            if not action:
                self._send_error(400, "Missing 'action' field.")
                return

            content_type, data = _dispatch(action, {}, body)

            if content_type == "error":
                self._send_error(400, data)
            elif content_type == "html":
                html = _generate_html(data)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self._send_json(200, data)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Reports error: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
