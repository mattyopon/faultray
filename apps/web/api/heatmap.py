"""FaultRay risk heatmap endpoint.

POST /api/heatmap
  Body: { "topology_yaml": "<yaml>" } or {}

Returns component-level risk scores for heatmap visualization.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_DATA = {
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
            return DEMO_DATA
    except Exception:
        return DEMO_DATA


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            topology_yaml = data.get("topology_yaml")
            result = _run_heatmap(topology_yaml)
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Heatmap error: {e}")

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
