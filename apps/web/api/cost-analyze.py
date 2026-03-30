"""FaultRay cost analysis endpoint.

POST /api/cost-analyze
  Body: { "revenue_per_hour": 10000, "industry": "fintech" }

Returns downtime cost estimates and ROI calculations.
"""

from http.server import BaseHTTPRequestHandler
import json


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


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            revenue = data.get("revenue_per_hour", 15000)
            industry = data.get("industry", "saas")

            result = _analyze_cost(float(revenue), industry)
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            self._send_error(500, f"Cost analysis error: {e}")

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
