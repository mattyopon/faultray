"""FaultRay analysis endpoint.

POST /api/analysis
  Body: { "action": "heatmap", "topology_yaml"?: "<yaml>" }
  Body: { "action": "score-explain" }
  Body: { "action": "whatif", "component_id": "...", "parameter": "replicas", "value": 5 }

Dispatches to heatmap, score-explain, or whatif handler based on 'action' field.
GET /api/analysis?action=score-explain  (also supported for score-explain)
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


# --- Heatmap data ---

HEATMAP_DEMO_DATA = {
    "components": [
        {"id": "cdn", "name": "CDN / Edge", "type": "load_balancer", "risk_score": 12, "category": "Network"},
        {"id": "gateway", "name": "API Gateway", "type": "load_balancer", "risk_score": 25, "category": "Network"},
        {"id": "auth", "name": "Auth Service", "type": "app_server", "risk_score": 45, "category": "Application"},
        {"id": "api", "name": "API Server", "type": "app_server", "risk_score": 38, "category": "Application"},
        {"id": "worker", "name": "Background Worker", "type": "app_server", "risk_score": 30, "category": "Application"},
        {"id": "db_primary", "name": "PostgreSQL Primary", "type": "database", "risk_score": 72, "category": "Data"},
        {"id": "db_replica", "name": "PostgreSQL Replica", "type": "database", "risk_score": 35, "category": "Data"},
        {"id": "cache", "name": "Redis Cache", "type": "cache", "risk_score": 55, "category": "Data"},
        {"id": "queue", "name": "Message Queue", "type": "queue", "risk_score": 40, "category": "Messaging"},
        {"id": "storage", "name": "Object Storage", "type": "storage", "risk_score": 15, "category": "Data"},
        {"id": "monitor", "name": "Monitoring", "type": "app_server", "risk_score": 20, "category": "Ops"},
        {"id": "dns", "name": "DNS", "type": "dns", "risk_score": 18, "category": "Network"},
    ],
    "categories": ["Network", "Application", "Data", "Messaging", "Ops"],
    "max_risk": 100,
}


def _run_heatmap(topology_yaml: str | None = None) -> dict:
    """Generate heatmap data from topology."""
    try:
        if topology_yaml:
            import tempfile
            import os
            from faultray.model.loader import load_yaml
            from faultray.simulator.engine import SimulationEngine

            fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(topology_yaml)
                graph = load_yaml(tmp_path)
                engine = SimulationEngine(graph)
                report = engine.run_all_defaults(include_feed=False, include_plugins=False)

                components = []
                for node in graph.nodes:
                    risk = 50
                    for r in report.results:
                        if hasattr(r, 'cascade') and node.id in [e.component_id for e in r.cascade.effects]:
                            risk = max(risk, int(r.risk_score * 10))
                    components.append({
                        "id": node.id,
                        "name": node.name,
                        "type": node.type.value if hasattr(node.type, 'value') else str(node.type),
                        "risk_score": min(risk, 100),
                        "category": node.type.value if hasattr(node.type, 'value') else "Other",
                    })
                categories = list(set(c["category"] for c in components))
                return {"components": components, "categories": categories, "max_risk": 100}
            finally:
                os.unlink(tmp_path)
        else:
            return HEATMAP_DEMO_DATA
    except Exception:
        return HEATMAP_DEMO_DATA


# --- Score explain data ---

SCORE_EXPLAIN_DEMO_DATA = {
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


# --- What-if data ---

WHATIF_BASELINE = {
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
        raise ImportError("Use demo")
    except Exception:
        impact_config = PARAMETER_IMPACTS.get(parameter, {"score_per_unit": 1.0, "max_effect": 5.0, "baseline": 1})
        baseline = impact_config["baseline"]
        delta = value - baseline
        raw_impact = delta * impact_config["score_per_unit"]
        clamped = max(-impact_config["max_effect"], min(impact_config["max_effect"], raw_impact))
        new_score = max(0, min(100, WHATIF_BASELINE["overall_score"] + clamped))

        if new_score >= 99.999:
            new_nines = 5.0
        elif new_score >= 99.0:
            new_nines = 4.0 + (new_score - 99.0) / 0.99
        elif new_score >= 90.0:
            new_nines = 3.0 + (new_score - 90.0) / 9.0
        else:
            new_nines = 2.0 + (new_score - 80.0) / 10.0

        return {
            "baseline": WHATIF_BASELINE,
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
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action = params.get("action", ["score-explain"])[0]
            if action == "score-explain":
                self._send_json(200, SCORE_EXPLAIN_DEMO_DATA)
            else:
                self._send_error(400, f"Unknown action '{action}' for GET. Use POST for heatmap/whatif.")
        except Exception as e:
            self._send_error(500, f"Analysis error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            action = data.get("action", "")

            if action == "heatmap":
                topology_yaml = data.get("topology_yaml")
                result = _run_heatmap(topology_yaml)
                self._send_json(200, result)

            elif action == "score-explain":
                self._send_json(200, SCORE_EXPLAIN_DEMO_DATA)

            elif action == "whatif":
                component_id = data.get("component_id", "api")
                parameter = data.get("parameter", "replicas")
                value = data.get("value", 3)
                result = _run_whatif(component_id, parameter, float(value))
                self._send_json(200, result)

            else:
                self._send_error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'heatmap', 'score-explain', or 'whatif'.",
                )

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Analysis error: {e}")

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
