"""FaultRay compliance assessment endpoint.

POST /api/compliance
  Body: { "topology_yaml": "<yaml>", "framework": "dora" }
     or { "framework": "dora" }  (uses default evidence)

Returns compliance report for the specified framework.
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


class handler(BaseHTTPRequestHandler):
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
