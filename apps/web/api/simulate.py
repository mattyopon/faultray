"""FaultRay simulation endpoint.

POST /api/simulate
  Body: { "topology_yaml": "<yaml string>" }
     or { "sample": "web-saas" | "microservices" | "data-pipeline" | "multi-region" }

Returns resilience analysis results.
"""

from http.server import BaseHTTPRequestHandler
import json
import tempfile
import os

# Built-in sample topologies matching the frontend UI options.
SAMPLE_TOPOLOGIES = {
    "web-saas": """
schema_version: "3.0"
components:
  - id: cdn
    name: CDN / Edge
    type: load_balancer
    replicas: 3
    capacity:
      max_connections: 50000
      max_rps: 100000
  - id: gateway
    name: API Gateway
    type: load_balancer
    replicas: 2
    capacity:
      max_connections: 20000
      max_rps: 30000
  - id: auth
    name: Auth Service
    type: app_server
    replicas: 2
  - id: api
    name: API Server
    type: app_server
    replicas: 3
  - id: worker
    name: Background Worker
    type: app_server
    replicas: 2
  - id: db_primary
    name: PostgreSQL Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_replica
    name: PostgreSQL Replica
    type: database
    replicas: 2
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 3
dependencies:
  - source: cdn
    target: gateway
  - source: gateway
    target: auth
  - source: gateway
    target: api
  - source: api
    target: db_primary
  - source: api
    target: cache
  - source: api
    target: worker
  - source: worker
    target: db_primary
  - source: db_primary
    target: db_replica
""",
    "microservices": """
schema_version: "3.0"
components:
  - id: lb
    name: Load Balancer
    type: load_balancer
    replicas: 2
  - id: gateway
    name: API Gateway
    type: load_balancer
    replicas: 2
  - id: svc_user
    name: User Service
    type: app_server
    replicas: 3
  - id: svc_order
    name: Order Service
    type: app_server
    replicas: 3
  - id: svc_payment
    name: Payment Service
    type: app_server
    replicas: 2
  - id: svc_notification
    name: Notification Service
    type: app_server
    replicas: 2
  - id: svc_inventory
    name: Inventory Service
    type: app_server
    replicas: 2
  - id: mq
    name: Message Queue (Kafka)
    type: queue
    replicas: 3
  - id: db_user
    name: User DB
    type: database
    replicas: 2
  - id: db_order
    name: Order DB
    type: database
    replicas: 2
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 3
  - id: mesh
    name: Service Mesh (Istio)
    type: custom
    replicas: 3
dependencies:
  - source: lb
    target: gateway
  - source: gateway
    target: svc_user
  - source: gateway
    target: svc_order
  - source: gateway
    target: svc_payment
  - source: svc_order
    target: mq
  - source: mq
    target: svc_notification
  - source: mq
    target: svc_inventory
  - source: svc_user
    target: db_user
  - source: svc_order
    target: db_order
  - source: svc_user
    target: cache
  - source: svc_order
    target: cache
""",
    "multi-region": """
schema_version: "3.0"
components:
  - id: dns
    name: Global DNS
    type: dns
    replicas: 3
  - id: cdn
    name: CDN Edge
    type: load_balancer
    replicas: 4
  - id: lb_us
    name: US Load Balancer
    type: load_balancer
    replicas: 2
  - id: lb_eu
    name: EU Load Balancer
    type: load_balancer
    replicas: 2
  - id: app_us
    name: US App Cluster
    type: app_server
    replicas: 3
  - id: app_eu
    name: EU App Cluster
    type: app_server
    replicas: 3
  - id: db_us
    name: US Database Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_eu
    name: EU Database Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_replica_us
    name: US Database Replica
    type: database
    replicas: 2
  - id: db_replica_eu
    name: EU Database Replica
    type: database
    replicas: 2
  - id: cache_us
    name: US Redis Cluster
    type: cache
    replicas: 3
  - id: cache_eu
    name: EU Redis Cluster
    type: cache
    replicas: 3
  - id: queue_us
    name: US Message Queue
    type: queue
    replicas: 2
  - id: queue_eu
    name: EU Message Queue
    type: queue
    replicas: 2
  - id: storage
    name: Global Object Storage
    type: storage
    replicas: 3
dependencies:
  - source: dns
    target: cdn
  - source: cdn
    target: lb_us
  - source: cdn
    target: lb_eu
  - source: lb_us
    target: app_us
  - source: lb_eu
    target: app_eu
  - source: app_us
    target: db_us
  - source: app_eu
    target: db_eu
  - source: app_us
    target: cache_us
  - source: app_eu
    target: cache_eu
  - source: app_us
    target: queue_us
  - source: app_eu
    target: queue_eu
  - source: db_us
    target: db_replica_us
  - source: db_eu
    target: db_replica_eu
  - source: db_us
    target: db_eu
  - source: app_us
    target: storage
  - source: app_eu
    target: storage
""",
    "data-pipeline": """
schema_version: "3.0"
components:
  - id: ingestion
    name: Data Ingestion API
    type: app_server
    replicas: 3
  - id: stream
    name: Stream Processor (Kafka)
    type: queue
    replicas: 3
  - id: batch
    name: Batch Processor
    type: app_server
    replicas: 2
  - id: transform
    name: Transform Engine
    type: app_server
    replicas: 3
  - id: warehouse
    name: Data Warehouse
    type: database
    replicas: 2
  - id: lake
    name: Data Lake (S3)
    type: storage
    replicas: 3
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 2
  - id: scheduler
    name: Job Scheduler
    type: app_server
    replicas: 2
  - id: monitor
    name: Pipeline Monitor
    type: app_server
    replicas: 2
  - id: api
    name: Query API
    type: app_server
    replicas: 2
dependencies:
  - source: ingestion
    target: stream
  - source: stream
    target: transform
  - source: scheduler
    target: batch
  - source: batch
    target: lake
  - source: transform
    target: warehouse
  - source: transform
    target: lake
  - source: api
    target: warehouse
  - source: api
    target: cache
  - source: monitor
    target: stream
  - source: monitor
    target: batch
""",
}


def _run_simulation(topology_yaml: str) -> dict:
    """Run FaultRay simulation on the given YAML topology."""
    from faultray.model.loader import load_yaml
    from faultray.simulator.engine import SimulationEngine

    # Write YAML to temp file (load_yaml expects a file path)
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(topology_yaml)

        graph = load_yaml(tmp_path)
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

        # Format availability estimate
        if nines >= 4.0:
            avail = "99.99%"
        elif nines >= 3.0:
            avail = "99.9%"
        elif nines >= 2.0:
            avail = "99%"
        else:
            avail = f"{score:.1f}%"

        # Build critical failures list
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

        # Build suggestions from warnings
        suggestions = []
        seen = set()
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
    finally:
        os.unlink(tmp_path)


def _save_run_to_supabase(data: dict) -> dict:
    """Persist a simulation run to the Supabase simulation_runs table."""
    import urllib.request as _urllib_req

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        return {"ok": True, "id": "demo", "demo": True}

    record = {
        "overall_score": data.get("overall_score", 0),
        "availability_estimate": data.get("availability_estimate", ""),
        "nines": data.get("nines"),
        "engine_type": data.get("engine_type", "static"),
        "scenarios_passed": data.get("scenarios_passed", 0),
        "scenarios_failed": data.get("scenarios_failed", 0),
        "total_scenarios": data.get("total_scenarios", 0),
        "result_data": json.dumps(data.get("result_data") or {}),
    }
    if data.get("project_id"):
        record["project_id"] = data["project_id"]

    body = json.dumps(record).encode()
    req = _urllib_req.Request(
        f"{supabase_url}/rest/v1/simulation_runs",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "return=representation",
        },
    )
    try:
        resp = _urllib_req.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        run_id = result[0]["id"] if isinstance(result, list) and result else "saved"
        return {"ok": True, "id": run_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            # Route: save-run (persist simulation result to Supabase)
            if data.get("action") == "save-run":
                result = _save_run_to_supabase(data)
                self._send_json(200, result)
                return

            # Route: run simulation
            topology_yaml = data.get("topology_yaml") or data.get("topology")
            sample = data.get("sample")

            if sample and sample in SAMPLE_TOPOLOGIES:
                topology_yaml = SAMPLE_TOPOLOGIES[sample]
            elif not topology_yaml:
                self._send_error(
                    400,
                    "Missing 'topology_yaml' or 'sample' in request body. "
                    f"Available samples: {list(SAMPLE_TOPOLOGIES.keys())}",
                )
                return

            result = _run_simulation(topology_yaml)

            # Auto-save to Supabase if project_id provided
            project_id = data.get("project_id")
            if project_id:
                _save_run_to_supabase({
                    **result,
                    "project_id": project_id,
                    "result_data": result,
                })

            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            error_type = type(e).__name__
            self._send_error(500, f"Simulation error ({error_type}): {e}")

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
