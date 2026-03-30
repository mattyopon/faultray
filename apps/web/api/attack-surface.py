"""FaultRay attack surface analysis endpoint.

GET /api/attack-surface

Returns external-facing components and vulnerability points.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_DATA = {
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._send_json(200, DEMO_DATA)
        except Exception as e:
            self._send_error(500, f"Attack surface error: {e}")

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
