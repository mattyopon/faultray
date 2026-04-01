"""FaultRay governance endpoint — DORA compliance, AI Governance, and SLA/SLO management.

GET /api/governance?action=dora        → DORA assessment data
GET /api/governance?action=ai-governance → AI governance data
GET /api/governance?action=sla         → SLA/SLO data

POST /api/governance  Body: { "action": "dora" | "ai-governance" | "sla" }
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# DORA Demo Data
# ---------------------------------------------------------------------------

DORA_DEMO_DATA = {
    "assessed_at": "2026-04-01T09:00:00Z",
    "organization": "FinTech Corp",
    "overall_score": 72,
    "pillars": [
        {
            "id": "pillar1",
            "name": "ICT Risk Management",
            "articles": "Articles 5-16",
            "score": 78,
            "status": "partial",
            "compliant": 6,
            "total": 10,
        },
        {
            "id": "pillar2",
            "name": "Incident Management",
            "articles": "Articles 17-23",
            "score": 62,
            "status": "partial",
            "compliant": 4,
            "total": 8,
        },
        {
            "id": "pillar3",
            "name": "Resilience Testing",
            "articles": "Articles 24-27",
            "score": 70,
            "status": "partial",
            "compliant": 5,
            "total": 7,
        },
        {
            "id": "pillar4",
            "name": "Third-Party Risk",
            "articles": "Articles 28-30",
            "score": 55,
            "status": "non_compliant",
            "compliant": 3,
            "total": 8,
        },
        {
            "id": "pillar5",
            "name": "Information Sharing",
            "articles": "Article 45",
            "score": 82,
            "status": "compliant",
            "compliant": 4,
            "total": 5,
        },
    ],
    "controls": [
        {"id": "P1-01", "pillar": "pillar1", "description": "ICT Risk Management Policy", "status": "compliant", "last_assessed": "2026-03-15", "evidence": "doc_001.pdf"},
        {"id": "P1-02", "pillar": "pillar1", "description": "Asset Management & Classification", "status": "compliant", "last_assessed": "2026-03-15", "evidence": "doc_002.pdf"},
        {"id": "P1-03", "pillar": "pillar1", "description": "Risk Assessment Process", "status": "partial", "last_assessed": "2026-02-28", "evidence": "doc_003.pdf"},
        {"id": "P1-04", "pillar": "pillar1", "description": "Protection & Prevention Controls", "status": "non_compliant", "last_assessed": "2026-02-01", "evidence": None},
        {"id": "P2-01", "pillar": "pillar2", "description": "Incident Detection & Classification", "status": "compliant", "last_assessed": "2026-03-20", "evidence": "doc_010.pdf"},
        {"id": "P2-02", "pillar": "pillar2", "description": "Major Incident Reporting (4h SLA)", "status": "non_compliant", "last_assessed": "2026-03-01", "evidence": None},
        {"id": "P2-03", "pillar": "pillar2", "description": "Incident Response Procedures", "status": "partial", "last_assessed": "2026-03-10", "evidence": "doc_012.pdf"},
        {"id": "P2-04", "pillar": "pillar2", "description": "Root Cause Analysis Process", "status": "compliant", "last_assessed": "2026-03-20", "evidence": "doc_013.pdf"},
        {"id": "P3-01", "pillar": "pillar3", "description": "Periodic ICT Tool Testing", "status": "compliant", "last_assessed": "2026-03-25", "evidence": "doc_020.pdf"},
        {"id": "P3-02", "pillar": "pillar3", "description": "Threat-Led Penetration Testing (TLPT)", "status": "non_compliant", "last_assessed": "2026-01-15", "evidence": None},
        {"id": "P3-03", "pillar": "pillar3", "description": "Test Result Remediation Tracking", "status": "compliant", "last_assessed": "2026-03-25", "evidence": "doc_022.pdf"},
        {"id": "P4-01", "pillar": "pillar4", "description": "Third-Party Identification & Classification", "status": "partial", "last_assessed": "2026-02-20", "evidence": "doc_030.pdf"},
        {"id": "P4-02", "pillar": "pillar4", "description": "DORA Contract Clause Standardization", "status": "non_compliant", "last_assessed": "2026-01-31", "evidence": None},
        {"id": "P4-03", "pillar": "pillar4", "description": "Cloud Concentration Risk Assessment", "status": "non_compliant", "last_assessed": "2026-01-31", "evidence": None},
        {"id": "P4-04", "pillar": "pillar4", "description": "Critical Third-Party Oversight Framework", "status": "partial", "last_assessed": "2026-02-28", "evidence": "doc_033.pdf"},
        {"id": "P5-01", "pillar": "pillar5", "description": "Cyber Threat Intelligence Sharing", "status": "compliant", "last_assessed": "2026-03-28", "evidence": "doc_040.pdf"},
        {"id": "P5-02", "pillar": "pillar5", "description": "Incident Information Exchange", "status": "compliant", "last_assessed": "2026-03-28", "evidence": "doc_041.pdf"},
        {"id": "P5-03", "pillar": "pillar5", "description": "Cross-Industry Collaboration", "status": "partial", "last_assessed": "2026-03-10", "evidence": "doc_042.pdf"},
    ],
    "gaps": [
        {"control_id": "P4-02", "severity": "critical", "description": "DORA-required contract clauses missing from 23 vendor agreements", "remediation": "Update all vendor contracts with DORA-required provisions", "deadline": "2026-06-30"},
        {"control_id": "P2-02", "severity": "critical", "description": "Incident reporting pipeline not automated within 4-hour regulatory window", "remediation": "Implement automated incident reporting with 4h SLA", "deadline": "2026-05-31"},
        {"control_id": "P4-03", "severity": "high", "description": "No concentration risk assessment for AWS/Azure cloud dependency", "remediation": "Perform concentration risk assessment, document multi-cloud strategy", "deadline": "2026-07-31"},
        {"control_id": "P3-02", "severity": "high", "description": "No TLPT program established; required for systemic institutions", "remediation": "Establish annual TLPT program with qualified external testers", "deadline": "2026-09-30"},
        {"control_id": "P1-04", "severity": "high", "description": "Insufficient network segmentation between critical systems", "remediation": "Implement zero-trust network segmentation", "deadline": "2026-06-30"},
    ],
    "dora_metrics": {
        "deployment_frequency": {"value": 12.3, "unit": "per week", "trend": "up", "benchmark": 15.0, "status": "good"},
        "lead_time": {"value": 4.2, "unit": "days", "trend": "down", "benchmark": 3.0, "status": "warning"},
        "change_failure_rate": {"value": 8.5, "unit": "%", "trend": "down", "benchmark": 5.0, "status": "warning"},
        "mttr": {"value": 47, "unit": "minutes", "trend": "down", "benchmark": 30, "status": "good"},
    },
    "evidence_packages": [
        {"pillar": "pillar1", "items": 6, "total_required": 10, "coverage": 60},
        {"pillar": "pillar2", "items": 4, "total_required": 8, "coverage": 50},
        {"pillar": "pillar3", "items": 4, "total_required": 7, "coverage": 57},
        {"pillar": "pillar4", "items": 2, "total_required": 8, "coverage": 25},
        {"pillar": "pillar5", "items": 4, "total_required": 5, "coverage": 80},
    ],
}


# ---------------------------------------------------------------------------
# AI Governance Demo Data
# ---------------------------------------------------------------------------

AI_GOVERNANCE_DEMO_DATA = {
    "assessed_at": "2026-04-01T09:00:00Z",
    "organization": "FinTech Corp",
    "maturity_level": 2,
    "overall_score": 48,
    "radar_scores": {
        "transparency": 55,
        "accountability": 60,
        "fairness": 40,
        "privacy": 70,
        "safety": 45,
        "security": 65,
        "human_oversight": 35,
        "data_governance": 60,
        "risk_management": 50,
        "stakeholder": 40,
    },
    "frameworks": {
        "meti": {
            "name": "METI AI Guidelines v1.1",
            "score": 52,
            "status": "partial",
            "total_requirements": 28,
            "compliant": 6,
            "partial": 12,
            "non_compliant": 10,
        },
        "iso42001": {
            "name": "ISO/IEC 42001:2023",
            "score": 44,
            "status": "partial",
            "total_requirements": 25,
            "compliant": 4,
            "partial": 9,
            "non_compliant": 12,
        },
        "ai_act": {
            "name": "AI推進法 (Draft)",
            "score": 47,
            "status": "partial",
            "total_requirements": 15,
            "compliant": 2,
            "partial": 9,
            "non_compliant": 4,
        },
    },
    "gaps": [
        {"id": "G-001", "framework": "meti", "requirement": "Human oversight mechanisms for high-risk AI decisions", "priority": "critical", "status": "non_compliant", "action": "Implement mandatory human review for AI decisions affecting >$10k"},
        {"id": "G-002", "framework": "iso42001", "requirement": "AI risk assessment documentation for all deployed models", "priority": "critical", "status": "non_compliant", "action": "Document risk assessments for 8 production AI systems"},
        {"id": "G-003", "framework": "ai_act", "requirement": "Explainability mechanisms for automated decisions", "priority": "high", "status": "non_compliant", "action": "Implement SHAP/LIME explanations for credit scoring model"},
        {"id": "G-004", "framework": "meti", "requirement": "Bias testing and fairness metrics", "priority": "high", "status": "partial", "action": "Extend bias testing to cover all protected attributes"},
        {"id": "G-005", "framework": "iso42001", "requirement": "AI incident response procedures", "priority": "high", "status": "non_compliant", "action": "Create AI-specific incident response runbook"},
        {"id": "G-006", "framework": "meti", "requirement": "Third-party AI vendor assessment", "priority": "medium", "status": "partial", "action": "Complete vendor assessments for 5 AI service providers"},
    ],
    "policy_templates": [
        {"id": "PT-001", "name": "AI Usage Policy", "description": "Acceptable use guidelines for AI tools across the organization", "status": "draft"},
        {"id": "PT-002", "name": "AI Risk Management Policy", "description": "Framework for identifying, assessing, and mitigating AI risks", "status": "not_started"},
        {"id": "PT-003", "name": "AI Ethics Guidelines", "description": "Ethical principles for AI development and deployment", "status": "draft"},
        {"id": "PT-004", "name": "AI Data Management Policy", "description": "Data governance requirements for AI training and inference", "status": "not_started"},
        {"id": "PT-005", "name": "AI Incident Response Plan", "description": "Procedures for detecting, reporting, and remediating AI incidents", "status": "not_started"},
    ],
    "ai_systems": [
        {"id": "AI-001", "name": "Credit Scoring Model", "department": "Risk", "risk_level": "high", "status": "active", "shadow_ai": False},
        {"id": "AI-002", "name": "Fraud Detection Engine", "department": "Security", "risk_level": "high", "status": "active", "shadow_ai": False},
        {"id": "AI-003", "name": "Customer Churn Predictor", "department": "Marketing", "risk_level": "medium", "status": "active", "shadow_ai": False},
        {"id": "AI-004", "name": "Document OCR Pipeline", "department": "Operations", "risk_level": "low", "status": "active", "shadow_ai": False},
        {"id": "AI-005", "name": "ChatGPT API Integration", "department": "Engineering", "risk_level": "medium", "status": "active", "shadow_ai": True},
        {"id": "AI-006", "name": "Automated Trading Bot", "department": "Finance", "risk_level": "high", "status": "review", "shadow_ai": False},
        {"id": "AI-007", "name": "HR Resume Screener", "department": "HR", "risk_level": "high", "status": "active", "shadow_ai": True},
        {"id": "AI-008", "name": "Sentiment Analysis API", "department": "Support", "risk_level": "low", "status": "active", "shadow_ai": False},
    ],
}


# ---------------------------------------------------------------------------
# SLA Demo Data
# ---------------------------------------------------------------------------

SLA_DEMO_DATA = {
    "assessed_at": "2026-04-01T09:00:00Z",
    "sla_overview": {
        "target": 99.95,
        "current": 99.97,
        "error_budget_total_minutes": 262.8,
        "error_budget_used_minutes": 104.5,
        "error_budget_remaining_pct": 60.2,
        "status": "healthy",
        "trend": "stable",
        "projected_breach_date": None,
    },
    "slo_breakdown": [
        {"name": "HTTP Success Rate", "target": 99.9, "current": 99.96, "unit": "%", "status": "compliant"},
        {"name": "Latency P50", "target": 100, "current": 68, "unit": "ms", "status": "compliant"},
        {"name": "Latency P95", "target": 300, "current": 245, "unit": "ms", "status": "compliant"},
        {"name": "Latency P99", "target": 1000, "current": 892, "unit": "ms", "status": "warning"},
        {"name": "Error Rate", "target": 0.1, "current": 0.04, "unit": "%", "status": "compliant"},
        {"name": "Throughput", "target": 500, "current": 1240, "unit": "req/s", "status": "compliant"},
        {"name": "DB Query Time P95", "target": 50, "current": 43, "unit": "ms", "status": "compliant"},
        {"name": "Cache Hit Rate", "target": 90, "current": 94.5, "unit": "%", "status": "compliant"},
    ],
    "error_budget_history": [
        {"day": 1, "budget_used_pct": 2.1},
        {"day": 2, "budget_used_pct": 4.5},
        {"day": 3, "budget_used_pct": 6.2},
        {"day": 4, "budget_used_pct": 8.9},
        {"day": 5, "budget_used_pct": 11.3},
        {"day": 6, "budget_used_pct": 14.8},
        {"day": 7, "budget_used_pct": 18.2},
        {"day": 8, "budget_used_pct": 19.5},
        {"day": 9, "budget_used_pct": 22.1},
        {"day": 10, "budget_used_pct": 25.6},
        {"day": 11, "budget_used_pct": 27.3},
        {"day": 12, "budget_used_pct": 29.8},
        {"day": 13, "budget_used_pct": 32.4},
        {"day": 14, "budget_used_pct": 33.1},
        {"day": 15, "budget_used_pct": 35.7},
        {"day": 16, "budget_used_pct": 37.2},
        {"day": 17, "budget_used_pct": 38.9},
        {"day": 18, "budget_used_pct": 39.8},
        {"day": 19, "budget_used_pct": 39.8},
        {"day": 20, "budget_used_pct": 39.8},
        {"day": 21, "budget_used_pct": 39.8},
        {"day": 22, "budget_used_pct": 39.8},
        {"day": 23, "budget_used_pct": 39.8},
        {"day": 24, "budget_used_pct": 39.8},
        {"day": 25, "budget_used_pct": 39.8},
        {"day": 26, "budget_used_pct": 39.8},
        {"day": 27, "budget_used_pct": 39.8},
        {"day": 28, "budget_used_pct": 39.8},
        {"day": 29, "budget_used_pct": 39.8},
        {"day": 30, "budget_used_pct": 39.8},
    ],
    "validation": {
        "can_meet_sla": True,
        "bottleneck_layer": "Software (P99 latency approaching limit)",
        "availability_by_layer": {
            "hardware": {"nines": 5.91, "availability": 99.99999},
            "software": {"nines": 4.0, "availability": 99.99},
            "theoretical": {"nines": 3.85, "availability": 99.986},
        },
        "limiting_factor": "software",
        "proof": "Current software layer availability (99.99%) exceeds SLA target (99.95%). P99 latency at 892ms is approaching 1000ms threshold — continued growth may cause SLO breach within 45 days.",
        "recommendations": [
            "Optimize P99 latency: add DB query caching for slow endpoints",
            "Set up burn-rate alerts at 5% and 10% hourly budget consumption",
            "Review and reduce error budget usage from deploy events",
        ],
    },
    "contracts": [
        {"id": "C-001", "provider": "AWS us-east-1", "target": 99.99, "penalty_terms": "10% credit per 0.01% below target", "expiry": "2027-03-31", "status": "active"},
        {"id": "C-002", "provider": "Cloudflare CDN", "target": 99.9, "penalty_terms": "Service credit up to 25% monthly fee", "expiry": "2026-12-31", "status": "active"},
        {"id": "C-003", "provider": "Stripe Payments API", "target": 99.99, "penalty_terms": "0.01% fee reduction per minute of downtime", "expiry": "2027-06-30", "status": "active"},
        {"id": "C-004", "provider": "Twilio SMS Gateway", "target": 99.95, "penalty_terms": "Pro-rata credit for downtime", "expiry": "2026-09-30", "status": "active"},
    ],
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _dispatch(action: str, _params: dict, _body: dict | None = None):
    """Route to the correct handler based on action."""
    if action == "dora":
        return "json", DORA_DEMO_DATA
    elif action == "ai-governance":
        return "json", AI_GOVERNANCE_DEMO_DATA
    elif action == "sla":
        return "json", SLA_DEMO_DATA
    else:
        return "error", f"Unknown action '{action}'. Use 'dora', 'ai-governance', or 'sla'."


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action = params.get("action", ["dora"])[0]
            content_type, data = _dispatch(action, params)

            if content_type == "error":
                self._send_error(400, data)
            else:
                self._send_json(200, data)
        except Exception as e:
            self._send_error(500, f"Governance error: {e}")

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
            else:
                self._send_json(200, data)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Governance error: {e}")

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
