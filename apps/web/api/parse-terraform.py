"""Terraform state parsing endpoint.

POST /api/parse-terraform
  Body: { "tfstate_json": "<json string>" }

Parses Terraform state into an InfraGraph and runs FaultRay simulation.
"""

from http.server import BaseHTTPRequestHandler
import json


def _run_terraform_parse(tfstate_json_str: str) -> dict:
    """Parse Terraform state and run simulation."""
    from faultray.discovery.terraform import parse_tf_state
    from faultray.simulator.engine import SimulationEngine

    state_dict = json.loads(tfstate_json_str)
    graph = parse_tf_state(state_dict)

    if len(graph.components) == 0:
        raise ValueError(
            "No infrastructure components found in the Terraform state. "
            "Ensure the state file contains resource definitions."
        )

    # Run simulation on parsed graph
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(
        include_feed=False, include_plugins=False
    )

    # Calculate availability nines from resilience score
    score = report.resilience_score
    if score >= 99.999:
        nines = 5.0
    elif score >= 99.99:
        nines = 4.0 + (score - 99.99) / 0.009
    elif score >= 99.9:
        nines = 3.0 + (score - 99.9) / 0.09
    elif score >= 99.0:
        nines = 2.0 + (score - 99.0) / 0.9
    elif score >= 90.0:
        nines = 1.0 + (score - 90.0) / 9.0
    else:
        nines = score / 90.0

    if nines >= 4.0:
        avail = "99.99%"
    elif nines >= 3.0:
        avail = "99.9%"
    elif nines >= 2.0:
        avail = "99%"
    else:
        avail = f"{score:.1f}%"

    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append(
            {
                "scenario": r.scenario.name,
                "impact": (
                    f"Risk score {r.risk_score:.1f}/10 - "
                    f"{len(r.cascade.effects)} components affected"
                ),
                "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
            }
        )

    suggestions = []
    seen: set[str] = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append(
                {
                    "title": title,
                    "description": (
                        f"Scenario risk score: {r.risk_score:.1f}. "
                        f"Consider adding redundancy or failover."
                    ),
                    "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                    "effort": (
                        "Low" if r.risk_score < 5.0 else "Medium"
                    ),
                }
            )

    return {
        "scan_summary": {
            "components_found": len(graph.components),
            "dependencies_inferred": len(graph.all_dependency_edges()),
        },
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            tfstate_json = data.get("tfstate_json")
            if not tfstate_json:
                self._send_error(
                    400,
                    "Missing 'tfstate_json' in request body. "
                    "Provide the output of 'terraform show -json' "
                    "or the contents of a .tfstate file.",
                )
                return

            result = _run_terraform_parse(tfstate_json)
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except ValueError as e:
            self._send_error(400, str(e))
        except Exception as e:
            error_type = type(e).__name__
            self._send_error(
                500, f"Terraform parse error ({error_type}): {e}"
            )

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
