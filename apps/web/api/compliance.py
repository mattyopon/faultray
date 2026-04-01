"""FaultRay compliance + governance endpoint (merged).

POST /api/compliance   Body: { "framework": "dora" } → compliance report
GET  /api/governance?action=dora         → DORA data (rewritten to /api/compliance)
GET  /api/governance?action=ai-governance → AI governance data
GET  /api/governance?action=sla          → SLA/SLO data
"""

from http.server import BaseHTTPRequestHandler
import json


SUPPORTED_FRAMEWORKS = [
    "dora",
    "soc2",
    "iso27001",
    "pci_dss",
    "hipaa",
    "gdpr",
]


def _run_compliance(framework: str, evidence_data: dict | None = None) -> dict:
    """Run compliance assessment against a framework."""
    from faultray.simulator.compliance_frameworks import (
        ComplianceFramework,
        ComplianceFrameworksEngine,
        InfrastructureEvidence,
    )

    fw = ComplianceFramework(framework)

    if evidence_data:
        # Filter to only valid fields
        valid_fields = {
            k: v
            for k, v in evidence_data.items()
            if hasattr(InfrastructureEvidence, k)
        }
        evidence = InfrastructureEvidence(**valid_fields)
    else:
        evidence = InfrastructureEvidence()

    engine = ComplianceFrameworksEngine(evidence)
    report = engine.assess(fw)

    # Build controls list
    controls = []
    if hasattr(report, "controls") and report.controls:
        for ctrl in report.controls:
            status = getattr(ctrl, "status", "unknown")
            # Convert enum to string if needed
            if hasattr(status, "value"):
                status = status.value
            controls.append(
                {
                    "id": getattr(ctrl, "control_id", ""),
                    "name": getattr(ctrl, "title", str(ctrl)),
                    "status": status,
                    "description": getattr(ctrl, "description", ""),
                    "remediation": getattr(ctrl, "remediation", ""),
                }
            )

    return {
        "framework": report.framework.value,
        "score": report.overall_score,
        "compliant_count": report.compliant_count,
        "non_compliant_count": report.non_compliant_count,
        "controls": controls,
        "findings": report.critical_gaps,
        "recommendations": report.recommendations,
    }


# ---------------------------------------------------------------------------
# Governance demo data (merged from governance.py)
# ---------------------------------------------------------------------------

DORA_DEMO_DATA = {"assessed_at": "2026-04-01T09:00:00Z", "overall_score": 72, "pillars": [{"id": "P1", "name": "ICT Risk Management", "articles": "5-16", "score": 68, "status": "partial", "controls_total": 15, "controls_passed": 8}, {"id": "P2", "name": "Incident Management", "articles": "17-23", "score": 75, "status": "partial", "controls_total": 10, "controls_passed": 7}, {"id": "P3", "name": "Resilience Testing", "articles": "24-27", "score": 82, "status": "partial", "controls_total": 8, "controls_passed": 6}, {"id": "P4", "name": "Third-Party Risk", "articles": "28-30", "score": 55, "status": "non_compliant", "controls_total": 12, "controls_passed": 5}, {"id": "P5", "name": "Information Sharing", "articles": "45", "score": 90, "status": "compliant", "controls_total": 7, "controls_passed": 6}], "dora_metrics": {"deployment_frequency": {"value": "4.2/week", "trend": "up", "benchmark": "Daily"}, "lead_time": {"value": "3.5 days", "trend": "down", "benchmark": "< 1 day"}, "change_failure_rate": {"value": "8.5%", "trend": "stable", "benchmark": "< 5%"}, "mttr": {"value": "2.1 hours", "trend": "down", "benchmark": "< 1 hour"}}}

AI_GOVERNANCE_DEMO_DATA = {"maturity_level": 2, "maturity_label": "Basic", "overall_score": 1.8, "categories": [{"id": "C01", "name": "Human-Centric", "score": 2.1}, {"id": "C02", "name": "Safety", "score": 1.5}, {"id": "C03", "name": "Fairness", "score": 1.2}, {"id": "C04", "name": "Privacy", "score": 2.5}, {"id": "C05", "name": "Security", "score": 2.0}, {"id": "C06", "name": "Transparency", "score": 1.3}, {"id": "C07", "name": "Accountability", "score": 2.2}, {"id": "C08", "name": "Education", "score": 1.8}, {"id": "C09", "name": "Fair Competition", "score": 2.0}, {"id": "C10", "name": "Innovation", "score": 1.6}], "frameworks": {"meti": {"score": 54, "total": 28, "compliant": 6, "partial": 12, "non_compliant": 10}, "iso42001": {"score": 48, "total": 25, "compliant": 4, "partial": 11, "non_compliant": 10}, "ai_act": {"score": 60, "total": 15, "compliant": 5, "partial": 6, "non_compliant": 4}}, "gaps": [{"req_id": "C03-R01", "title": "Bias evaluation", "status": "non_compliant", "priority": "high", "actions": ["Implement fairness metrics", "Conduct bias audit"]}, {"req_id": "C06-R01", "title": "AI usage disclosure", "status": "non_compliant", "priority": "high", "actions": ["Publish AI usage policy", "Add disclosure to interfaces"]}, {"req_id": "C02-R01", "title": "Risk assessment", "status": "non_compliant", "priority": "high", "actions": ["Conduct AI risk assessment", "Document risk mitigation"]}], "policies": [{"type": "ai_usage", "title": "AI Usage Policy"}, {"type": "risk_management", "title": "Risk Management Policy"}, {"type": "ethics", "title": "Ethics Policy"}, {"type": "data_management", "title": "Data Management Policy"}, {"type": "incident_response", "title": "Incident Response Policy"}], "ai_systems": [{"name": "Customer Support Bot", "risk_level": "limited", "department": "Support", "status": "production"}, {"name": "Fraud Detection Model", "risk_level": "high", "department": "Risk", "status": "production"}, {"name": "HR Resume Screener", "risk_level": "high", "department": "HR", "status": "testing"}]}

SLA_DEMO_DATA = {"sla_target": 99.95, "current_availability": 99.97, "error_budget_total": 0.05, "error_budget_used": 40, "error_budget_remaining": 60, "slos": [{"name": "Availability", "target": "99.95%", "current": "99.97%", "status": "met"}, {"name": "Latency P50", "target": "< 200ms", "current": "145ms", "status": "met"}, {"name": "Latency P99", "target": "< 1000ms", "current": "850ms", "status": "met"}, {"name": "Error Rate", "target": "< 0.1%", "current": "0.08%", "status": "met"}, {"name": "Throughput", "target": "> 10K rps", "current": "12.5K rps", "status": "met"}], "validation": {"can_meet_sla": True, "bottleneck": "Software layer", "layers": {"hardware": 5.91, "software": 4.0, "theoretical": 6.65}}, "contracts": [{"provider": "AWS", "sla": "99.99%", "penalty": "10% credit per 0.01% below", "expiry": "2027-03-31"}, {"provider": "Cloudflare", "sla": "100%", "penalty": "25x credit", "expiry": "2026-12-31"}]}


def _dispatch_governance(action: str):
    """Route governance GET requests."""
    if action == "dora":
        return DORA_DEMO_DATA
    elif action == "ai-governance":
        return AI_GOVERNANCE_DEMO_DATA
    elif action == "sla":
        return SLA_DEMO_DATA
    return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle governance GET requests (rewritten from /api/governance)."""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action = params.get("action", [""])[0]

            if action:
                data = _dispatch_governance(action)
                if data:
                    self._send_json(200, data)
                else:
                    self._send_error(400, f"Unknown action '{action}'")
            else:
                self._send_json(200, {"supported_actions": ["dora", "ai-governance", "sla"]})
        except Exception as e:
            self._send_error(500, f"Governance error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            framework = data.get("framework", "").lower()

            if not framework:
                self._send_error(
                    400,
                    "Missing 'framework' in request body. "
                    f"Supported: {SUPPORTED_FRAMEWORKS}",
                )
                return

            if framework not in SUPPORTED_FRAMEWORKS:
                self._send_error(
                    400,
                    f"Unsupported framework '{framework}'. "
                    f"Supported: {SUPPORTED_FRAMEWORKS}",
                )
                return

            evidence = data.get("evidence")
            result = _run_compliance(framework, evidence)
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            error_type = type(e).__name__
            self._send_error(500, f"Compliance error ({error_type}): {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header(
            "Access-Control-Allow-Methods", "POST, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
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
