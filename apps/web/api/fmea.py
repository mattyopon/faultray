"""FaultRay FMEA (Failure Mode and Effects Analysis) endpoint.

GET /api/fmea

Returns failure modes, effects, and RPN scores for each component.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_DATA = {
    "analysis_date": "2026-03-30",
    "total_failure_modes": 18,
    "critical_rpn_threshold": 200,
    "high_rpn_count": 4,
    "failure_modes": [
        {
            "id": "FM-001",
            "component": "PostgreSQL Primary",
            "failure_mode": "Complete database crash",
            "effect": "All write operations fail, data loss risk",
            "severity": 9,
            "occurrence": 3,
            "detection": 8,
            "rpn": 216,
            "recommended_action": "Implement automated failover with < 30s switchover",
            "status": "open",
        },
        {
            "id": "FM-002",
            "component": "Redis Cache",
            "failure_mode": "Memory exhaustion",
            "effect": "Cache eviction storm, database overload",
            "severity": 7,
            "occurrence": 5,
            "detection": 6,
            "rpn": 210,
            "recommended_action": "Set memory limits, implement eviction policies",
            "status": "open",
        },
        {
            "id": "FM-003",
            "component": "API Gateway",
            "failure_mode": "Certificate expiry",
            "effect": "All HTTPS connections rejected",
            "severity": 10,
            "occurrence": 2,
            "detection": 9,
            "rpn": 180,
            "recommended_action": "Automate cert renewal with Let's Encrypt",
            "status": "mitigated",
        },
        {
            "id": "FM-004",
            "component": "API Server",
            "failure_mode": "Thread pool exhaustion",
            "effect": "Requests queued, timeouts for users",
            "severity": 6,
            "occurrence": 6,
            "detection": 4,
            "rpn": 144,
            "recommended_action": "Implement connection limits and auto-scaling",
            "status": "open",
        },
        {
            "id": "FM-005",
            "component": "DNS",
            "failure_mode": "DNS resolution failure",
            "effect": "Service unreachable for all users",
            "severity": 10,
            "occurrence": 1,
            "detection": 7,
            "rpn": 70,
            "recommended_action": "Multi-provider DNS with health checks",
            "status": "mitigated",
        },
        {
            "id": "FM-006",
            "component": "CDN / Edge",
            "failure_mode": "Origin pull failure",
            "effect": "Stale content served, dynamic requests fail",
            "severity": 5,
            "occurrence": 3,
            "detection": 3,
            "rpn": 45,
            "recommended_action": "Configure fallback origins",
            "status": "mitigated",
        },
        {
            "id": "FM-007",
            "component": "Auth Service",
            "failure_mode": "Token validation failure",
            "effect": "Users unable to authenticate",
            "severity": 8,
            "occurrence": 2,
            "detection": 5,
            "rpn": 80,
            "recommended_action": "Implement token caching and offline validation",
            "status": "open",
        },
        {
            "id": "FM-008",
            "component": "Background Worker",
            "failure_mode": "Job queue backlog",
            "effect": "Delayed processing, stale data",
            "severity": 4,
            "occurrence": 5,
            "detection": 3,
            "rpn": 60,
            "recommended_action": "Implement dead letter queue and monitoring",
            "status": "open",
        },
        {
            "id": "FM-009",
            "component": "PostgreSQL Primary",
            "failure_mode": "Replication lag",
            "effect": "Read replicas serve stale data",
            "severity": 5,
            "occurrence": 4,
            "detection": 4,
            "rpn": 80,
            "recommended_action": "Monitor replication lag, implement read-after-write consistency",
            "status": "open",
        },
        {
            "id": "FM-010",
            "component": "API Gateway",
            "failure_mode": "Rate limit misconfiguration",
            "effect": "Legitimate traffic blocked during peaks",
            "severity": 7,
            "occurrence": 3,
            "detection": 5,
            "rpn": 105,
            "recommended_action": "Implement adaptive rate limiting based on traffic patterns",
            "status": "open",
        },
    ],
    "rpn_distribution": {
        "critical": 2,
        "high": 2,
        "medium": 4,
        "low": 2,
    },
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._send_json(200, DEMO_DATA)
        except Exception as e:
            self._send_error(500, f"FMEA error: {e}")

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
