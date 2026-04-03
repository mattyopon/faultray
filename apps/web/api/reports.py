"""FaultRay reports + risk + finance + billing endpoint (merged).

Routes:
  GET  /api/reports?action=report&format=json
  GET  /api/reports?action=report&format=html
  GET  /api/reports?action=incidents
  GET  /api/risk?action=attack-surface   (rewritten to /api/reports by vercel.json)
  GET  /api/risk?action=fmea
  POST /api/reports  Body: { "action": "report" | "incidents" | "attack-surface" | "fmea" }

  GET  /api/finance?action=benchmark&industry=fintech
  POST /api/finance  Body: { "action": "cost", "revenue_per_hour": 10000, "industry": "fintech" }
  POST /api/finance  Body: { "action": "benchmark", "industry": "saas" }

  POST /api/billing  Body: { "action": "checkout", "plan": "pro" | "business" }
  POST /api/billing  (Stripe webhook — detected by Stripe-Signature header)

Path routing uses the request path to determine which handler to call.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import urlparse, parse_qs


# ===========================================================================
# REPORTS — data and helpers
# ===========================================================================

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
    # REPORT-GEN-03: html.escape() でXSSを防止 — ユーザーデータを直接HTML埋め込みしない
    def esc(val: object) -> str:
        return html.escape(str(val), quote=True)

    findings_html = ""
    for f in report["key_findings"]:
        sev = esc(f.get("severity", ""))
        color = "#ef4444" if sev == "CRITICAL" else "#f59e0b" if sev == "HIGH" else "#3b82f6"
        findings_html += f"""
        <div style="border-left: 4px solid {color}; padding: 12px 16px; margin: 12px 0; background: #111827; border-radius: 0 8px 8px 0;">
            <strong style="color: {color};">[{sev}]</strong> {esc(f.get("finding", ""))}<br/>
            <small style="color: #94a3b8;">Impact: {esc(f.get("impact", ""))}</small><br/>
            <small style="color: #10b981;">Recommendation: {esc(f.get("recommendation", ""))}</small>
        </div>"""

    roadmap_rows = "".join(
        f'<tr style="border-bottom: 1px solid #1e293b/50;"><td style="padding: 8px;">{esc(r.get("priority",""))}</td><td style="padding: 8px;">{esc(r.get("action",""))}</td><td style="padding: 8px; color: #10b981;">{esc(r.get("impact",""))}</td><td style="padding: 8px;">{esc(r.get("timeline",""))}</td></tr>'
        for r in report.get("improvement_roadmap", [])
    )

    return f"""<!DOCTYPE html>
<html><head><title>{esc(report.get("title", "FaultRay Report"))}</title>
<style>
body {{ font-family: -apple-system, "Yu Gothic", "Hiragino Sans", "Meiryo", "Noto Sans CJK JP", sans-serif; background: #0a0e1a; color: #e2e8f0; max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
h1 {{ color: #FFD700; border-bottom: 2px solid #1e293b; padding-bottom: 16px; }}
h2 {{ color: #94a3b8; margin-top: 32px; }}
.score {{ font-size: 48px; font-weight: bold; color: #FFD700; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 16px 0; }}
.stat {{ background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 16px; text-align: center; }}
.stat-value {{ font-size: 24px; font-weight: bold; font-family: monospace; }}
.stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }}
</style></head><body>
<h1>{esc(report.get("title", "FaultRay Report"))}</h1>
<p style="color: #64748b;">Generated: {esc(report.get("generated_at", ""))}</p>
<h2>Executive Summary</h2>
<div class="grid">
<div class="stat"><div class="stat-value" style="color: #FFD700;">{esc(report.get("executive_summary", {}).get("overall_score", ""))}</div><div class="stat-label">Resilience Score</div></div>
<div class="stat"><div class="stat-value" style="color: #10b981;">{esc(report.get("executive_summary", {}).get("availability_estimate", ""))}</div><div class="stat-label">Availability</div></div>
<div class="stat"><div class="stat-value" style="color: #ef4444;">{esc(report.get("executive_summary", {}).get("critical_issues", ""))}</div><div class="stat-label">Critical Issues</div></div>
</div>
<h2>Key Findings</h2>
{findings_html}
<h2>Improvement Roadmap</h2>
<table style="width: 100%; border-collapse: collapse;">
<tr style="border-bottom: 1px solid #1e293b;"><th style="text-align: left; padding: 8px; color: #64748b;">Priority</th><th style="text-align: left; padding: 8px; color: #64748b;">Action</th><th style="text-align: left; padding: 8px; color: #64748b;">Impact</th><th style="text-align: left; padding: 8px; color: #64748b;">Timeline</th></tr>
{roadmap_rows}
</table>
</body></html>"""


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


def _dispatch_reports(action: str, params: dict, body=None):
    """Route to the correct reports handler based on action."""
    body = body or {}
    if action == "report":
        fmt = params.get("format", ["json"])[0] if isinstance(params.get("format"), list) else body.get("format", "json")
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


# ===========================================================================
# FINANCE — data and helpers
# ===========================================================================

INDUSTRY_DEFAULTS = {
    "fintech": {"revenue_per_hour": 50000, "penalty_multiplier": 2.5, "reputation_factor": 1.8},
    "healthcare": {"revenue_per_hour": 30000, "penalty_multiplier": 3.0, "reputation_factor": 2.0},
    "ecommerce": {"revenue_per_hour": 25000, "penalty_multiplier": 1.2, "reputation_factor": 1.5},
    "saas": {"revenue_per_hour": 15000, "penalty_multiplier": 1.5, "reputation_factor": 1.3},
    "media": {"revenue_per_hour": 20000, "penalty_multiplier": 1.0, "reputation_factor": 1.6},
}


def _analyze_cost(revenue_per_hour: float, industry: str) -> dict:
    """Calculate downtime costs and improvement ROI."""
    defaults = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["saas"])
    if revenue_per_hour <= 0:
        revenue_per_hour = defaults["revenue_per_hour"]

    current_nines = 3.5
    target_nines = 4.0
    current_downtime_hours = 365.25 * 24 * (1 - (1 - 10 ** (-current_nines)))
    target_downtime_hours = 365.25 * 24 * (1 - (1 - 10 ** (-target_nines)))

    current_annual_cost = current_downtime_hours * revenue_per_hour * defaults["penalty_multiplier"]
    target_annual_cost = target_downtime_hours * revenue_per_hour * defaults["penalty_multiplier"]
    savings = current_annual_cost - target_annual_cost

    improvements = [
        {
            "action": "Add database read replica",
            "cost": 2400,
            "score_gain": 5.0,
            "nines_gain": 0.3,
            "annual_savings": savings * 0.3,
            "roi_percent": round((savings * 0.3 / 2400) * 100, 0),
            "payback_days": round(2400 / (savings * 0.3 / 365), 0) if savings > 0 else 999,
        },
        {
            "action": "Implement circuit breaker",
            "cost": 800,
            "score_gain": 3.2,
            "nines_gain": 0.15,
            "annual_savings": savings * 0.15,
            "roi_percent": round((savings * 0.15 / 800) * 100, 0),
            "payback_days": round(800 / (savings * 0.15 / 365), 0) if savings > 0 else 999,
        },
        {
            "action": "Multi-region deployment",
            "cost": 18000,
            "score_gain": 8.5,
            "nines_gain": 0.5,
            "annual_savings": savings * 0.5,
            "roi_percent": round((savings * 0.5 / 18000) * 100, 0),
            "payback_days": round(18000 / (savings * 0.5 / 365), 0) if savings > 0 else 999,
        },
        {
            "action": "Auto-scaling configuration",
            "cost": 1200,
            "score_gain": 2.8,
            "nines_gain": 0.1,
            "annual_savings": savings * 0.1,
            "roi_percent": round((savings * 0.1 / 1200) * 100, 0),
            "payback_days": round(1200 / (savings * 0.1 / 365), 0) if savings > 0 else 999,
        },
    ]

    return {
        "current": {
            "nines": current_nines,
            "downtime_hours_per_year": round(current_downtime_hours, 2),
            "annual_cost": round(current_annual_cost, 0),
        },
        "target": {
            "nines": target_nines,
            "downtime_hours_per_year": round(target_downtime_hours, 2),
            "annual_cost": round(target_annual_cost, 0),
        },
        "potential_savings": round(savings, 0),
        "revenue_per_hour": revenue_per_hour,
        "industry": industry,
        "improvements": improvements,
    }


BENCHMARKS = {
    "fintech": {
        "industry": "Financial Technology",
        "industry_id": "fintech",
        "your_score": 85.2,
        "industry_average": 82.5,
        "industry_top_10": 95.3,
        "industry_bottom_10": 62.1,
        "percentile": 65,
        "categories": [
            {"name": "Availability", "your_score": 88, "industry_avg": 90, "top_10": 99},
            {"name": "Redundancy", "your_score": 82, "industry_avg": 85, "top_10": 96},
            {"name": "Failover Speed", "your_score": 78, "industry_avg": 80, "top_10": 95},
            {"name": "Data Protection", "your_score": 90, "industry_avg": 88, "top_10": 98},
            {"name": "Monitoring", "your_score": 85, "industry_avg": 78, "top_10": 95},
            {"name": "Compliance", "your_score": 72, "industry_avg": 85, "top_10": 99},
        ],
        "regulatory_requirements": ["PCI-DSS", "SOC2", "SOX"],
        "typical_sla": "99.99%",
    },
    "healthcare": {
        "industry": "Healthcare",
        "industry_id": "healthcare",
        "your_score": 85.2,
        "industry_average": 78.0,
        "industry_top_10": 93.5,
        "industry_bottom_10": 55.0,
        "percentile": 75,
        "categories": [
            {"name": "Availability", "your_score": 88, "industry_avg": 82, "top_10": 97},
            {"name": "Redundancy", "your_score": 82, "industry_avg": 75, "top_10": 94},
            {"name": "Failover Speed", "your_score": 78, "industry_avg": 70, "top_10": 92},
            {"name": "Data Protection", "your_score": 90, "industry_avg": 90, "top_10": 99},
            {"name": "Monitoring", "your_score": 85, "industry_avg": 72, "top_10": 93},
            {"name": "Compliance", "your_score": 72, "industry_avg": 80, "top_10": 98},
        ],
        "regulatory_requirements": ["HIPAA", "HITRUST", "FDA 21 CFR Part 11"],
        "typical_sla": "99.95%",
    },
    "ecommerce": {
        "industry": "E-Commerce",
        "industry_id": "ecommerce",
        "your_score": 85.2,
        "industry_average": 75.0,
        "industry_top_10": 92.0,
        "industry_bottom_10": 50.0,
        "percentile": 80,
        "categories": [
            {"name": "Availability", "your_score": 88, "industry_avg": 80, "top_10": 96},
            {"name": "Redundancy", "your_score": 82, "industry_avg": 72, "top_10": 93},
            {"name": "Failover Speed", "your_score": 78, "industry_avg": 68, "top_10": 90},
            {"name": "Data Protection", "your_score": 90, "industry_avg": 78, "top_10": 95},
            {"name": "Monitoring", "your_score": 85, "industry_avg": 70, "top_10": 92},
            {"name": "Compliance", "your_score": 72, "industry_avg": 60, "top_10": 88},
        ],
        "regulatory_requirements": ["PCI-DSS", "GDPR"],
        "typical_sla": "99.9%",
    },
    "saas": {
        "industry": "SaaS",
        "industry_id": "saas",
        "your_score": 85.2,
        "industry_average": 80.0,
        "industry_top_10": 94.0,
        "industry_bottom_10": 58.0,
        "percentile": 70,
        "categories": [
            {"name": "Availability", "your_score": 88, "industry_avg": 85, "top_10": 99},
            {"name": "Redundancy", "your_score": 82, "industry_avg": 80, "top_10": 95},
            {"name": "Failover Speed", "your_score": 78, "industry_avg": 75, "top_10": 93},
            {"name": "Data Protection", "your_score": 90, "industry_avg": 82, "top_10": 96},
            {"name": "Monitoring", "your_score": 85, "industry_avg": 78, "top_10": 95},
            {"name": "Compliance", "your_score": 72, "industry_avg": 70, "top_10": 92},
        ],
        "regulatory_requirements": ["SOC2", "ISO27001", "GDPR"],
        "typical_sla": "99.9%",
    },
}


# ===========================================================================
# BILLING — helpers
# ===========================================================================

PRICE_IDS = {
    "pro": os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    "business": os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
}


def _billing_checkout(raw_body: bytes, origin: str) -> tuple:
    """Handle Stripe checkout session creation. Returns (status, data)."""
    try:
        import stripe
    except ImportError:
        return 500, {"error": "stripe package not installed"}

    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        return 500, {"error": "STRIPE_SECRET_KEY not configured"}
    stripe.api_key = stripe_key

    try:
        body = json.loads(raw_body) if raw_body else {}
    except (json.JSONDecodeError, ValueError):
        return 400, {"error": "Invalid JSON"}

    plan = body.get("plan", "")
    if plan not in ("pro", "business"):
        return 400, {"error": "Invalid plan. Must be 'pro' or 'business'"}

    price_id = PRICE_IDS.get(plan)
    if not price_id:
        return 500, {"error": f"Price ID not configured for plan: {plan}"}

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{origin}/dashboard?checkout=success&plan={plan}",
            cancel_url=f"{origin}/pricing?checkout=cancelled",
            metadata={"plan": plan},
        )
        return 200, {"url": session.url}
    except Exception as e:
        return 400, {"error": str(e)}


def _billing_webhook(payload: bytes, sig_header: str) -> tuple:
    """Handle Stripe webhook. Returns (status, data)."""
    try:
        import stripe
    except ImportError:
        return 500, {"error": "stripe package not installed"}

    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not stripe_key or not webhook_secret:
        return 500, {"error": "Stripe not configured"}
    stripe.api_key = stripe_key

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as e:
        return 400, {"error": f"Webhook verification failed: {e}"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        plan = session.get("metadata", {}).get("plan", "pro")
        email = session.get("customer_details", {}).get("email")
        _billing_update_supabase(email, {"plan": plan, "stripe_customer_id": customer_id})

    elif event["type"] == "customer.subscription.deleted":
        customer_id = event["data"]["object"].get("customer")
        _billing_update_supabase_by_customer(customer_id, {"plan": "free"})

    return 200, {"received": True}


def _billing_update_supabase(email, data):
    if not email:
        return
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/profiles?email=eq.{email}",
            data=json.dumps(data).encode(),
            method="PATCH",
            headers={
                "Content-Type": "application/json",
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req)
    except Exception:
        pass


def _billing_update_supabase_by_customer(customer_id, data):
    if not customer_id:
        return
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
            data=json.dumps(data).encode(),
            method="PATCH",
            headers={
                "Content-Type": "application/json",
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req)
    except Exception:
        pass


# ===========================================================================
# Handler — routes by path
# ===========================================================================

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Stripe-Signature")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            params = parse_qs(parsed.query)

            if "/finance" in path:
                self._handle_finance_get(path, params)
            else:
                # Default: reports / risk
                action = params.get("action", ["report"])[0]
                content_type, data = _dispatch_reports(action, params)
                self._send_reports_response(content_type, data)

        except Exception as e:
            self._error(500, f"Reports GET error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
        except Exception:
            raw_body = b""

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if "/finance" in path:
            self._handle_finance_post(raw_body)
        elif "/billing" in path:
            self._handle_billing_post(raw_body)
        else:
            # Default: reports / risk
            self._handle_reports_post(raw_body)

    # -----------------------------------------------------------------------
    # Reports
    # -----------------------------------------------------------------------

    def _handle_reports_post(self, raw_body: bytes):
        try:
            body = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON in request body")
            return
        action = body.get("action", "")
        if not action:
            self._error(400, "Missing 'action' field.")
            return
        content_type, data = _dispatch_reports(action, {}, body)
        self._send_reports_response(content_type, data)

    def _send_reports_response(self, content_type: str, data):
        if content_type == "error":
            self._error(400, data)
        elif content_type == "html":
            html = _generate_html(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self._json(200, data)

    # -----------------------------------------------------------------------
    # Finance
    # -----------------------------------------------------------------------

    def _handle_finance_get(self, path: str, params: dict):
        action = params.get("action", ["benchmark"])[0]
        if action == "benchmark":
            industry_list = params.get("industry", ["saas"])
            industry = industry_list[0] if industry_list else "saas"
            # Also support path-based: /api/finance/benchmark/fintech
            parts = path.rstrip("/").split("/")
            if len(parts) >= 2 and parts[-1] in BENCHMARKS:
                industry = parts[-1]
            self._json(200, BENCHMARKS.get(industry, BENCHMARKS["saas"]))
        else:
            self._error(400, f"Unknown action '{action}' for GET.")

    def _handle_finance_post(self, raw_body: bytes):
        try:
            data = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON")
            return

        action = data.get("action", "")

        if action == "cost":
            revenue = data.get("revenue_per_hour", 15000)
            industry = data.get("industry", "saas")
            self._json(200, _analyze_cost(float(revenue), industry))
        elif action == "benchmark":
            industry = data.get("industry", "saas")
            self._json(200, BENCHMARKS.get(industry, BENCHMARKS["saas"]))
        else:
            self._error(400, "Missing or invalid 'action' field. Must be 'cost' or 'benchmark'.")

    # -----------------------------------------------------------------------
    # Billing
    # -----------------------------------------------------------------------

    def _handle_billing_post(self, raw_body: bytes):
        sig_header = self.headers.get("Stripe-Signature", "")
        origin = self.headers.get("Origin", "https://faultray.com")
        if sig_header:
            status, data = _billing_webhook(raw_body, sig_header)
        else:
            status, data = _billing_checkout(raw_body, origin)
        self._json(status, data)

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    def _json(self, status: int, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str):
        self._json(status, {"error": {"message": message}})

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
