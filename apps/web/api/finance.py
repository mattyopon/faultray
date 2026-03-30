"""FaultRay finance endpoint.

POST /api/finance  Body: { "action": "cost", "revenue_per_hour": 10000, "industry": "fintech" }
GET  /api/finance?action=benchmark&industry=fintech

Dispatches to cost-analyze or benchmark handler based on 'action' field.
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


# --- Cost analysis ---

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


# --- Benchmark data ---

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
            params = parse_qs(parsed.query)
            action = params.get("action", ["benchmark"])[0]
            if action == "benchmark":
                industry_list = params.get("industry", ["saas"])
                industry = industry_list[0] if industry_list else "saas"
                # Also support path-based: /api/finance/benchmark/fintech
                parts = parsed.path.rstrip("/").split("/")
                if len(parts) >= 2 and parts[-1] in BENCHMARKS:
                    industry = parts[-1]
                data = BENCHMARKS.get(industry, BENCHMARKS["saas"])
                self._send_json(200, data)
            else:
                self._send_error(400, f"Unknown action '{action}' for GET.")
        except Exception as e:
            self._send_error(500, f"Finance error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            action = data.get("action", "")

            if action == "cost":
                revenue = data.get("revenue_per_hour", 15000)
                industry = data.get("industry", "saas")
                result = _analyze_cost(float(revenue), industry)
                self._send_json(200, result)

            elif action == "benchmark":
                industry = data.get("industry", "saas")
                result = BENCHMARKS.get(industry, BENCHMARKS["saas"])
                self._send_json(200, result)

            else:
                self._send_error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'cost' or 'benchmark'.",
                )

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            self._send_error(500, f"Finance error: {e}")

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
