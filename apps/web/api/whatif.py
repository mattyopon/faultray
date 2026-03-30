"""FaultRay what-if analysis endpoint.

POST /api/whatif
  Body: { "component_id": "...", "parameter": "replicas", "value": 5 }

Returns score impact of parameter changes.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_BASELINE = {
    "overall_score": 85.2,
    "availability_estimate": "99.99%",
    "nines": 4.0,
}

PARAMETER_IMPACTS = {
    "replicas": {"score_per_unit": 2.5, "max_effect": 12.0, "baseline": 2},
    "capacity": {"score_per_unit": 0.01, "max_effect": 8.0, "baseline": 5000},
    "failover_time": {"score_per_unit": -0.3, "max_effect": 10.0, "baseline": 30},
    "health_check_interval": {"score_per_unit": -0.5, "max_effect": 5.0, "baseline": 10},
    "retry_count": {"score_per_unit": 1.0, "max_effect": 5.0, "baseline": 3},
    "timeout": {"score_per_unit": -0.1, "max_effect": 3.0, "baseline": 30},
}


def _run_whatif(component_id: str, parameter: str, value: float) -> dict:
    """Calculate what-if scenario impact."""
    try:
        # If engine available, run actual simulation
        # For now use impact model
        raise ImportError("Use demo")
    except Exception:
        impact_config = PARAMETER_IMPACTS.get(parameter, {"score_per_unit": 1.0, "max_effect": 5.0, "baseline": 1})
        baseline = impact_config["baseline"]
        delta = value - baseline
        raw_impact = delta * impact_config["score_per_unit"]
        clamped = max(-impact_config["max_effect"], min(impact_config["max_effect"], raw_impact))
        new_score = max(0, min(100, DEMO_BASELINE["overall_score"] + clamped))

        if new_score >= 99.999:
            new_nines = 5.0
        elif new_score >= 99.0:
            new_nines = 4.0 + (new_score - 99.0) / 0.99
        elif new_score >= 90.0:
            new_nines = 3.0 + (new_score - 90.0) / 9.0
        else:
            new_nines = 2.0 + (new_score - 80.0) / 10.0

        return {
            "baseline": DEMO_BASELINE,
            "modified": {
                "overall_score": round(new_score, 1),
                "nines": round(max(1.0, new_nines), 2),
            },
            "delta": {
                "score": round(clamped, 1),
                "direction": "improvement" if clamped > 0 else "degradation" if clamped < 0 else "neutral",
            },
            "component_id": component_id,
            "parameter": parameter,
            "original_value": baseline,
            "new_value": value,
            "available_parameters": list(PARAMETER_IMPACTS.keys()),
        }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            component_id = data.get("component_id", "api")
            parameter = data.get("parameter", "replicas")
            value = data.get("value", 3)

            result = _run_whatif(component_id, parameter, float(value))
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            self._send_error(500, f"What-if error: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
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
