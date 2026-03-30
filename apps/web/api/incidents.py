"""FaultRay incident replay endpoint.

GET /api/incidents

Returns simulated incident timelines from past simulations.
"""

from http.server import BaseHTTPRequestHandler
import json


DEMO_DATA = {
    "incidents": [
        {
            "id": "INC-001",
            "title": "Cascading Database Failure",
            "severity": "critical",
            "start_time": "2026-03-28T14:23:00Z",
            "end_time": "2026-03-28T14:35:00Z",
            "duration_minutes": 12,
            "affected_components": ["db_primary", "api", "worker"],
            "root_cause": "Primary database disk I/O saturation",
            "timeline": [
                {"time": "T+0:00", "event": "Database disk I/O reaches 100%", "component": "db_primary", "type": "trigger"},
                {"time": "T+0:30", "event": "Query latency exceeds 5s threshold", "component": "db_primary", "type": "degradation"},
                {"time": "T+1:00", "event": "Connection pool exhausted (200/200)", "component": "db_primary", "type": "failure"},
                {"time": "T+1:15", "event": "API server health check fails", "component": "api", "type": "cascade"},
                {"time": "T+1:30", "event": "Background workers queue backlog", "component": "worker", "type": "cascade"},
                {"time": "T+2:00", "event": "Load balancer marks API servers unhealthy", "component": "gateway", "type": "cascade"},
                {"time": "T+5:00", "event": "Alert fired, on-call engineer paged", "component": "monitor", "type": "detection"},
                {"time": "T+8:00", "event": "Manual failover to replica initiated", "component": "db_replica", "type": "recovery"},
                {"time": "T+10:00", "event": "Replica promoted to primary", "component": "db_replica", "type": "recovery"},
                {"time": "T+12:00", "event": "All services recovered", "component": "all", "type": "resolved"},
            ],
        },
        {
            "id": "INC-002",
            "title": "Cache Cluster Network Partition",
            "severity": "high",
            "start_time": "2026-03-27T09:15:00Z",
            "end_time": "2026-03-27T09:28:00Z",
            "duration_minutes": 13,
            "affected_components": ["cache", "api"],
            "root_cause": "Network partition between cache nodes in different AZs",
            "timeline": [
                {"time": "T+0:00", "event": "Network partition between AZ-1a and AZ-1b", "component": "network", "type": "trigger"},
                {"time": "T+0:15", "event": "Cache cluster split-brain detected", "component": "cache", "type": "failure"},
                {"time": "T+0:30", "event": "Cache hit rate drops from 95% to 40%", "component": "cache", "type": "degradation"},
                {"time": "T+1:00", "event": "Database query load increases 3x", "component": "db_primary", "type": "cascade"},
                {"time": "T+2:00", "event": "API response time increases to 2.5s", "component": "api", "type": "degradation"},
                {"time": "T+5:00", "event": "Network partition resolved", "component": "network", "type": "recovery"},
                {"time": "T+8:00", "event": "Cache re-sync initiated", "component": "cache", "type": "recovery"},
                {"time": "T+13:00", "event": "Cache hit rate returns to 95%", "component": "cache", "type": "resolved"},
            ],
        },
        {
            "id": "INC-003",
            "title": "DNS Resolution Failure",
            "severity": "high",
            "start_time": "2026-03-25T22:10:00Z",
            "end_time": "2026-03-25T22:18:00Z",
            "duration_minutes": 8,
            "affected_components": ["dns", "cdn", "gateway"],
            "root_cause": "DNS provider TTL expiry during maintenance window",
            "timeline": [
                {"time": "T+0:00", "event": "DNS provider begins maintenance", "component": "dns", "type": "trigger"},
                {"time": "T+0:30", "event": "DNS TTL expires, resolution fails", "component": "dns", "type": "failure"},
                {"time": "T+1:00", "event": "CDN unable to resolve origin", "component": "cdn", "type": "cascade"},
                {"time": "T+1:30", "event": "New connections fail, existing connections unaffected", "component": "gateway", "type": "degradation"},
                {"time": "T+3:00", "event": "Secondary DNS takes over", "component": "dns", "type": "recovery"},
                {"time": "T+5:00", "event": "DNS propagation complete", "component": "dns", "type": "recovery"},
                {"time": "T+8:00", "event": "All traffic flowing normally", "component": "all", "type": "resolved"},
            ],
        },
    ],
    "summary": {
        "total_incidents": 3,
        "critical": 1,
        "high": 2,
        "medium": 0,
        "average_duration_minutes": 11,
        "most_affected_component": "db_primary",
    },
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._send_json(200, DEMO_DATA)
        except Exception as e:
            self._send_error(500, f"Incidents error: {e}")

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
