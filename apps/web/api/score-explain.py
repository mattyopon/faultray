"""FaultRay score explanation endpoint.

GET /api/score-explain

Returns breakdown of the resilience score by layer.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_DATA = {
    "overall_score": 85.2,
    "layers": [
        {
            "name": "Hardware",
            "score": 92.5,
            "weight": 0.20,
            "weighted_score": 18.5,
            "factors": [
                {"name": "Server redundancy", "score": 95, "impact": "positive"},
                {"name": "Disk RAID configuration", "score": 90, "impact": "positive"},
                {"name": "Power supply redundancy", "score": 88, "impact": "neutral"},
                {"name": "Network interface bonding", "score": 97, "impact": "positive"},
            ],
        },
        {
            "name": "Software",
            "score": 78.3,
            "weight": 0.25,
            "weighted_score": 19.6,
            "factors": [
                {"name": "Application replicas", "score": 85, "impact": "positive"},
                {"name": "Health check coverage", "score": 72, "impact": "negative"},
                {"name": "Circuit breaker patterns", "score": 60, "impact": "negative"},
                {"name": "Graceful degradation", "score": 80, "impact": "neutral"},
                {"name": "Auto-scaling policies", "score": 94, "impact": "positive"},
            ],
        },
        {
            "name": "Theoretical",
            "score": 95.0,
            "weight": 0.15,
            "weighted_score": 14.25,
            "factors": [
                {"name": "Markov chain steady state", "score": 97, "impact": "positive"},
                {"name": "MTBF/MTTR ratio", "score": 93, "impact": "positive"},
                {"name": "Reliability block diagram", "score": 95, "impact": "positive"},
            ],
        },
        {
            "name": "Operational",
            "score": 80.0,
            "weight": 0.25,
            "weighted_score": 20.0,
            "factors": [
                {"name": "Runbook coverage", "score": 65, "impact": "negative"},
                {"name": "On-call response time", "score": 82, "impact": "neutral"},
                {"name": "Deployment rollback capability", "score": 90, "impact": "positive"},
                {"name": "Monitoring & alerting", "score": 85, "impact": "positive"},
                {"name": "Incident post-mortem process", "score": 78, "impact": "neutral"},
            ],
        },
        {
            "name": "External SLA",
            "score": 85.6,
            "weight": 0.15,
            "weighted_score": 12.84,
            "factors": [
                {"name": "Cloud provider SLA", "score": 99, "impact": "positive"},
                {"name": "Third-party API reliability", "score": 72, "impact": "negative"},
                {"name": "DNS provider SLA", "score": 99, "impact": "positive"},
                {"name": "CDN availability", "score": 95, "impact": "positive"},
            ],
        },
    ],
    "top_detractors": [
        {"factor": "Circuit breaker patterns", "layer": "Software", "score": 60, "potential_gain": 3.2},
        {"factor": "Runbook coverage", "layer": "Operational", "score": 65, "potential_gain": 2.8},
        {"factor": "Third-party API reliability", "layer": "External SLA", "score": 72, "potential_gain": 1.5},
        {"factor": "Health check coverage", "layer": "Software", "score": 72, "potential_gain": 1.2},
    ],
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._send_json(200, DEMO_DATA)
        except Exception as e:
            self._send_error(500, f"Score explain error: {e}")

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
