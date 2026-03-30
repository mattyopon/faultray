"""FaultRay industry benchmark endpoint.

GET /api/benchmark/fintech
GET /api/benchmark/healthcare
GET /api/benchmark/ecommerce
GET /api/benchmark/saas

Returns industry benchmark comparison data.
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse


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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            parts = parsed.path.rstrip("/").split("/")

            # Extract industry from path: /api/benchmark/fintech
            industry = parts[-1] if len(parts) >= 3 and parts[-1] in BENCHMARKS else "saas"

            data = BENCHMARKS.get(industry, BENCHMARKS["saas"])
            self._send_json(200, data)
        except Exception as e:
            self._send_error(500, f"Benchmark error: {e}")

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
