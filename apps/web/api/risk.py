"""FaultRay risk analysis endpoint.

GET /api/risk?action=attack-surface
GET /api/risk?action=fmea
POST /api/risk  Body: { "action": "attack-surface" | "fmea" }

Dispatches to attack-surface or fmea handler based on 'action' field.
"""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


# --- Attack surface data ---

ATTACK_SURFACE_DEMO_DATA = {
    "summary": {
        "total_components": 12,
        "external_facing": 4,
        "internal_only": 8,
        "risk_level": "medium",
        "attack_vectors": 7,
    },
    "external_components": [
        {
            "id": "cdn",
            "name": "CDN / Edge",
            "exposure": "public",
            "ports": [80, 443],
            "protocols": ["HTTP", "HTTPS"],
            "risk_score": 35,
            "vulnerabilities": [
                {"type": "DDoS", "severity": "medium", "mitigation": "Rate limiting configured"},
                {"type": "Cache poisoning", "severity": "low", "mitigation": "Cache-Control headers set"},
            ],
        },
        {
            "id": "gateway",
            "name": "API Gateway",
            "exposure": "public",
            "ports": [443],
            "protocols": ["HTTPS"],
            "risk_score": 45,
            "vulnerabilities": [
                {"type": "Injection attacks", "severity": "high", "mitigation": "Input validation in place"},
                {"type": "Authentication bypass", "severity": "high", "mitigation": "OAuth2 + PKCE configured"},
                {"type": "Rate limit exhaustion", "severity": "medium", "mitigation": "Per-user rate limits"},
            ],
        },
        {
            "id": "auth",
            "name": "Auth Service",
            "exposure": "semi-public",
            "ports": [443],
            "protocols": ["HTTPS"],
            "risk_score": 55,
            "vulnerabilities": [
                {"type": "Brute force", "severity": "medium", "mitigation": "Account lockout after 5 attempts"},
                {"type": "Session hijacking", "severity": "high", "mitigation": "Secure cookie flags set"},
            ],
        },
        {
            "id": "dns",
            "name": "DNS",
            "exposure": "public",
            "ports": [53],
            "protocols": ["DNS", "DNSSEC"],
            "risk_score": 25,
            "vulnerabilities": [
                {"type": "DNS spoofing", "severity": "medium", "mitigation": "DNSSEC enabled"},
            ],
        },
    ],
    "internal_components": [
        {"id": "api", "name": "API Server", "risk_score": 30},
        {"id": "worker", "name": "Background Worker", "risk_score": 15},
        {"id": "db_primary", "name": "PostgreSQL Primary", "risk_score": 60},
        {"id": "db_replica", "name": "PostgreSQL Replica", "risk_score": 25},
        {"id": "cache", "name": "Redis Cache", "risk_score": 40},
        {"id": "queue", "name": "Message Queue", "risk_score": 20},
        {"id": "storage", "name": "Object Storage", "risk_score": 15},
        {"id": "monitor", "name": "Monitoring", "risk_score": 10},
    ],
    "recommendations": [
        "Implement WAF (Web Application Firewall) before API Gateway",
        "Enable mutual TLS for internal service communication",
        "Add network segmentation between data and application tiers",
        "Implement egress filtering to prevent data exfiltration",
        "Deploy intrusion detection system (IDS) for database tier",
    ],
}


# --- FMEA data ---

FMEA_DEMO_DATA = {
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
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            action = params.get("action", ["attack-surface"])[0]
            if action == "attack-surface":
                self._send_json(200, ATTACK_SURFACE_DEMO_DATA)
            elif action == "fmea":
                self._send_json(200, FMEA_DEMO_DATA)
            else:
                self._send_error(400, f"Unknown action '{action}'. Use 'attack-surface' or 'fmea'.")
        except Exception as e:
            self._send_error(500, f"Risk error: {e}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            action = data.get("action", "")

            if action == "attack-surface":
                self._send_json(200, ATTACK_SURFACE_DEMO_DATA)
            elif action == "fmea":
                self._send_json(200, FMEA_DEMO_DATA)
            else:
                self._send_error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'attack-surface' or 'fmea'.",
                )

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Risk error: {e}")

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
