"""FaultRay APM (Application Performance Monitoring) backend.

Routes (all via /api/apm/*):
  GET  /api/apm/agents              -> list all agents
  GET  /api/apm/agents/{id}/metrics -> metrics for an agent
  GET  /api/apm/alerts              -> list alerts (optional ?severity= filter)
  GET  /api/apm/stats               -> aggregate stats
  POST /api/apm/metrics             -> ingest metrics batch
  POST /api/apm/agents/register     -> register new agent
  POST /api/apm/agents/{id}/heartbeat -> update heartbeat
  POST /api/apm/purge               -> purge old data
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Demo data (used when Supabase is not configured)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _get_demo_agents():
    return [
        {
            "agent_id": "agent-001",
            "hostname": "web-server-01",
            "ip_address": "10.0.1.10",
            "status": "running",
            "os_info": "Ubuntu 22.04",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 7),
            "last_seen": _ago(15),
            "cpu_percent": 34.2,
            "memory_percent": 61.8,
            "disk_percent": 45.0,
        },
        {
            "agent_id": "agent-002",
            "hostname": "api-server-02",
            "ip_address": "10.0.1.11",
            "status": "running",
            "os_info": "Ubuntu 22.04",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 7),
            "last_seen": _ago(8),
            "cpu_percent": 72.5,
            "memory_percent": 85.3,
            "disk_percent": 62.1,
        },
        {
            "agent_id": "agent-003",
            "hostname": "db-server-01",
            "ip_address": "10.0.1.20",
            "status": "degraded",
            "os_info": "Debian 12",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 14),
            "last_seen": _ago(45),
            "cpu_percent": 91.3,
            "memory_percent": 78.2,
            "disk_percent": 88.7,
        },
        {
            "agent_id": "agent-004",
            "hostname": "cache-server-01",
            "ip_address": "10.0.1.30",
            "status": "offline",
            "os_info": "CentOS 8",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 30),
            "last_seen": _ago(600),
            "cpu_percent": None,
            "memory_percent": None,
            "disk_percent": None,
        },
    ]


def _get_demo_alerts(severity_filter=None):
    alerts = [
        {
            "id": "alert-001",
            "agent_id": "agent-003",
            "severity": "CRITICAL",
            "rule_name": "high_cpu",
            "metric_name": "cpu_percent",
            "metric_value": 91.3,
            "threshold": 90.0,
            "message": "CPU usage 91.3% exceeds critical threshold 90%",
            "fired_at": _ago(300),
            "resolved_at": None,
        },
        {
            "id": "alert-002",
            "agent_id": "agent-003",
            "severity": "WARNING",
            "rule_name": "high_disk",
            "metric_name": "disk_percent",
            "metric_value": 88.7,
            "threshold": 80.0,
            "message": "Disk usage 88.7% exceeds warning threshold 80%",
            "fired_at": _ago(1200),
            "resolved_at": None,
        },
        {
            "id": "alert-003",
            "agent_id": "agent-002",
            "severity": "WARNING",
            "rule_name": "high_memory",
            "metric_name": "memory_percent",
            "metric_value": 85.3,
            "threshold": 80.0,
            "message": "Memory usage 85.3% exceeds warning threshold 80%",
            "fired_at": _ago(600),
            "resolved_at": None,
        },
        {
            "id": "alert-004",
            "agent_id": "agent-004",
            "severity": "CRITICAL",
            "rule_name": "agent_offline",
            "metric_name": None,
            "metric_value": None,
            "threshold": None,
            "message": "Agent cache-server-01 has been offline for >5 minutes",
            "fired_at": _ago(540),
            "resolved_at": None,
        },
    ]
    if severity_filter:
        alerts = [a for a in alerts if a["severity"] == severity_filter]
    return alerts


def _get_demo_metrics(agent_id: str, metric_filter: str | None = None):
    import math
    now = datetime.now(timezone.utc)
    points = []
    metrics_config = {
        "cpu_percent": lambda i: round(50 + 20 * math.sin(i * 0.3) + (i % 3) * 2, 1),
        "memory_usage_percent": lambda i: round(60 + 10 * math.cos(i * 0.2), 1),
        "net_bytes_sent": lambda i: round(30 + 25 * math.sin(i * 0.15) + (i % 5) * 3, 1),
    }
    for name, fn in metrics_config.items():
        if metric_filter and name != metric_filter:
            continue
        for i in range(24):
            t = now - timedelta(minutes=i * 5)
            points.append({
                "metric_name": name,
                "value": fn(i),
                "sample_count": 1,
                "bucket_epoch": int(t.timestamp()),
            })
    return points


def _get_demo_stats():
    return {
        "total_agents": 4,
        "running": 2,
        "degraded": 1,
        "offline": 1,
        "total_alerts": 4,
        "critical_alerts": 2,
        "warning_alerts": 2,
        "info_alerts": 0,
        "avg_cpu_percent": 52.0,
        "avg_memory_percent": 61.0,
        "avg_disk_percent": 51.9,
        "metrics_last_hour": 240,
        "generated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_configured() -> bool:
    return bool(
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _supabase_request(method: str, table: str, params: str = "", body=None):
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        return None
    url = f"{supabase_url}/rest/v1/{table}{params}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "return=representation",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

def _validate_api_key(headers) -> bool:
    expected = os.environ.get("FAULTRAY_APM_API_KEY", "")
    if not expected:
        return True  # dev mode: allow all
    provided = headers.get("X-API-Key", "")
    return provided == expected


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_list_agents():
    if not _supabase_configured():
        return 200, _get_demo_agents()
    agents = _supabase_request("GET", "apm_agents", "?order=last_seen.desc")
    if agents is None:
        return 200, _get_demo_agents()
    return 200, agents


def _handle_agent_metrics(agent_id: str, query_params: dict):
    metric_name = query_params.get("metric_name", [None])[0]
    if not _supabase_configured():
        return 200, _get_demo_metrics(agent_id, metric_name)
    limit = query_params.get("limit", ["60"])[0]
    params = f"?agent_id=eq.{agent_id}&order=collected_at.desc&limit={limit}"
    if metric_name:
        params += f"&metric_name=eq.{metric_name}"
    metrics = _supabase_request("GET", "apm_metrics", params)
    if metrics is None:
        return 200, _get_demo_metrics(agent_id)
    return 200, metrics


def _handle_list_alerts(query_params: dict):
    severity = query_params.get("severity", [None])[0]
    if not _supabase_configured():
        return 200, _get_demo_alerts(severity)
    params = "?order=fired_at.desc&limit=100"
    if severity:
        params += f"&severity=eq.{severity}"
    alerts = _supabase_request("GET", "apm_alerts", params)
    if alerts is None:
        return 200, _get_demo_alerts(severity)
    return 200, alerts


def _handle_stats():
    if not _supabase_configured():
        return 200, _get_demo_stats()
    agents = _supabase_request("GET", "apm_agents", "")
    alerts = _supabase_request("GET", "apm_alerts", "?resolved_at=is.null")
    if agents is None:
        return 200, _get_demo_stats()
    total = len(agents)
    running = sum(1 for a in agents if a.get("status") == "running")
    degraded = sum(1 for a in agents if a.get("status") == "degraded")
    offline = sum(1 for a in agents if a.get("status") == "offline")
    critical_alerts = 0
    warning_alerts = 0
    info_alerts = 0
    if alerts:
        critical_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "CRITICAL")
        warning_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "WARNING")
        info_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "INFO")
    return 200, {
        "total_agents": total,
        "running": running,
        "degraded": degraded,
        "offline": offline,
        "total_alerts": len(alerts) if alerts else 0,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "info_alerts": info_alerts,
        "generated_at": _now_iso(),
    }


def _handle_ingest_metrics(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _supabase_configured():
        return 200, {"ok": True, "inserted": 0, "demo": True}
    metrics = body.get("metrics", [])
    if not isinstance(metrics, list):
        return 400, {"error": "'metrics' must be a list"}
    if not metrics:
        return 200, {"ok": True, "inserted": 0}
    result = _supabase_request("POST", "apm_metrics", "", metrics)
    inserted = len(result) if result else 0
    return 200, {"ok": True, "inserted": inserted}


def _handle_register_agent(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    agent_id = body.get("agent_id", "").strip()
    hostname = body.get("hostname", "").strip()
    if not agent_id or not hostname:
        return 400, {"error": "'agent_id' and 'hostname' are required"}
    if not _supabase_configured():
        return 200, {"ok": True, "agent_id": agent_id, "demo": True}
    record = {
        "agent_id": agent_id,
        "hostname": hostname,
        "ip_address": body.get("ip_address"),
        "os_info": body.get("os_info"),
        "version": body.get("version"),
        "labels": body.get("labels", {}),
        "status": "running",
        "last_seen": _now_iso(),
    }
    result = _supabase_request(
        "POST",
        "apm_agents",
        "?on_conflict=agent_id",
        record,
    )
    return 200, {"ok": True, "agent_id": agent_id}


def _handle_heartbeat(agent_id: str, body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _supabase_configured():
        return 200, {"ok": True, "agent_id": agent_id, "demo": True}
    patch = {"last_seen": _now_iso()}
    if "status" in body:
        patch["status"] = body["status"]
    # Attach optional inline metric snapshot fields
    for field in ("cpu_percent", "memory_percent", "disk_percent"):
        if field in body:
            patch[field] = body[field]
    _supabase_request(
        "PATCH",
        "apm_agents",
        f"?agent_id=eq.{agent_id}",
        patch,
    )
    return 200, {"ok": True, "agent_id": agent_id}


def _handle_purge(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _supabase_configured():
        return 200, {"ok": True, "demo": True}
    # Default: purge metrics older than 7 days
    days = int(body.get("older_than_days", 7))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    _supabase_request(
        "DELETE",
        "apm_metrics",
        f"?collected_at=lt.{cutoff}",
    )
    return 200, {"ok": True, "purged_before": cutoff}


# ---------------------------------------------------------------------------
# Handler class
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            query = parse_qs(parsed.query)

            # /api/apm/agents
            if path == "/api/apm/agents":
                status, data = _handle_list_agents()
                self._json(status, data)

            # /api/apm/agents/{id}/metrics
            elif "/metrics" in path and "/agents/" in path:
                # Extract agent_id between /agents/ and /metrics
                after_agents = path.split("/agents/", 1)[1]
                agent_id = after_agents.replace("/metrics", "")
                status, data = _handle_agent_metrics(agent_id, query)
                self._json(status, data)

            # /api/apm/alerts
            elif path == "/api/apm/alerts":
                status, data = _handle_list_alerts(query)
                self._json(status, data)

            # /api/apm/stats
            elif path == "/api/apm/stats":
                status, data = _handle_stats()
                self._json(status, data)

            else:
                self._json(404, {"error": f"Unknown APM endpoint: {path}"})

        except Exception as e:
            self._json(500, {"error": f"APM GET error: {e}"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return

        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            # POST /api/apm/metrics
            if path == "/api/apm/metrics":
                status, data = _handle_ingest_metrics(body, self.headers)
                self._json(status, data)

            # POST /api/apm/agents/register
            elif path == "/api/apm/agents/register":
                status, data = _handle_register_agent(body, self.headers)
                self._json(status, data)

            # POST /api/apm/agents/{id}/heartbeat
            elif "/heartbeat" in path and "/agents/" in path:
                after_agents = path.split("/agents/", 1)[1]
                agent_id = after_agents.replace("/heartbeat", "")
                status, data = _handle_heartbeat(agent_id, body, self.headers)
                self._json(status, data)

            # POST /api/apm/purge
            elif path == "/api/apm/purge":
                status, data = _handle_purge(body, self.headers)
                self._json(status, data)

            else:
                self._json(404, {"error": f"Unknown APM endpoint: {path}"})

        except Exception as e:
            self._json(500, {"error": f"APM POST error: {e}"})

    def _json(self, status: int, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
